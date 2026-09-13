"""Exercise the source-hash/Go-version gate, not a mocked version comparison."""

import hashlib
import importlib.util
import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "consumer", SCRIPTS / "check-go-consumer.py"
)
if spec is None or spec.loader is None:
    raise RuntimeError("unable to load consumer checker")
consumer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(consumer)


class ConsumerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / "package/feeds/passwall_packages/xray-core"
        self.package.mkdir(parents=True)
        (self.root / "dl").mkdir()
        self.archive = self.root / "dl/Xray-core-26.9.9.tar.gz"
        with tarfile.open(self.archive, "w:gz") as archive:
            payload = b"module github.com/xtls/xray-core\n\ngo 1.27\n"
            info = tarfile.TarInfo("Xray-core-26.9.9/go.mod")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        (self.package / "Makefile").write_text(
            "PKG_NAME:=Xray-core\nPKG_VERSION:=26.9.9\n"
            "PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz\n"
            "PKG_SOURCE_URL:=https://codeload.github.com/XTLS/Xray-core/tar.gz/v$(PKG_VERSION)?\n"
            f"PKG_HASH:={digest}\nPKG_BUILD_DEPENDS:=golang/host\n"
        )

    def test_original_mismatch_rejected_and_matching_toolchain_passes(self):
        with self.assertRaisesRegex(ValueError, "requires Go 1.27.*selected 1.26.8"):
            consumer.check(self.root, "1.26.8")
        self.assertEqual(consumer.check(self.root, "1.27.0")["minimum_go"], "1.27")

    def test_corrupt_cache_rejected_without_eviction(self):
        self.archive.write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            consumer.check(self.root, "1.27.0")
        self.assertEqual(self.archive.read_bytes(), b"corrupt")

    def test_missing_metadata_and_unknown_source_fail_closed(self):
        makefile = self.package / "Makefile"
        text = makefile.read_text()
        makefile.write_text(text.replace("XTLS/Xray-core", "elsewhere/unknown"))
        with self.assertRaisesRegex(ValueError, "source layout"):
            consumer.check(self.root, "1.27.0")
        makefile.unlink()
        with self.assertRaises(OSError):
            consumer.check(self.root, "1.27.0")

    def test_download_is_hash_verified_before_use(self):
        payload = self.archive.read_bytes()
        self.archive.unlink()
        with patch.object(consumer, "download", return_value=payload) as request:
            consumer.check(self.root, "1.27.0")
            self.assertIn("/v26.9.9", request.call_args.args[0])
        self.assertEqual(self.archive.read_bytes(), payload)

    def test_patch_versions_compared_numerically(self):
        self.assertGreater(consumer.version("1.27.10"), consumer.version("1.27.9"))
        self.assertEqual(consumer.version("1.27"), consumer.version("1.27.0"))
        with self.assertRaises(ValueError):
            consumer.version("1.27rc1")


if __name__ == "__main__":
    unittest.main()
