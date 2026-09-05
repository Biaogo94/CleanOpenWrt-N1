"""Exercise the actual build-script archive_has function under pipefail."""
import io
import re
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build-immortalwrt.sh"
TARGET = "lib/netifd/wireless/mac80211.sh"


class ArchiveValidationTests(unittest.TestCase):
    def check_archive(self, archive):
        source = SCRIPT.read_text(encoding="utf-8")
        function = re.search(r"^archive_has\(\) \{\n.*?^\}", source, re.M | re.S)
        if function is None:
            self.fail("archive_has function not found in build script")
        return subprocess.run(
            ["bash", "-o", "pipefail", "-c",
             function.group() + '\nrootfs_archive="$1"\narchive_has "$2"',
             "test", archive.name, TARGET],
            cwd=archive.parent,
            capture_output=True, text=True, check=False,
        )

    def make_archive(self, path, prefix="./", include_target=True):
        with tarfile.open(path, "w:gz") as archive:
            names = ([TARGET] if include_target else []) + [
                f"usr/share/test/{i:05d}-" + "x" * 100 for i in range(12000)
            ]
            for name in names:
                entry = tarfile.TarInfo(prefix + name)
                entry.size = 1
                archive.addfile(entry, io.BytesIO(b"x"))

    def test_present_before_large_tail(self):
        for prefix in ("./", ""):
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp) / "rootfs.tar.gz"
                self.make_archive(archive, prefix)
                result = self.check_archive(archive)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_member_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "rootfs.tar.gz"
            self.make_archive(archive, include_target=False)
            self.assertNotEqual(self.check_archive(archive).returncode, 0)

    def test_truncated_archive_fails_even_when_member_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "rootfs.tar.gz"
            self.make_archive(archive)
            archive.write_bytes(archive.read_bytes()[:-32])
            self.assertNotEqual(self.check_archive(archive).returncode, 0)


if __name__ == "__main__":
    unittest.main()
