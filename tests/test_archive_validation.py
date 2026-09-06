"""Regression tests through the production archive validator CLI."""

import io
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/validate-rootfs.py"
REQUIRED = (
    "lib/netifd/wireless/mac80211.sh",
    "lib/firmware/brcm/brcmfmac43455-sdio.bin",
    "lib/firmware/brcm/brcmfmac43455-sdio.clm_blob",
    "usr/share/passwall/clash_subconverter.lua",
)


class ArchiveValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "rootfs.tar.gz"

    def make(self, prefix="./", missing=False, tail=0, link=None, duplicate=False):
        with tarfile.open(self.path, "w:gz") as archive:
            for name in REQUIRED[1:] if missing else REQUIRED:
                entry = tarfile.TarInfo(prefix + name)
                if link and name == REQUIRED[0]:
                    entry.type = tarfile.SYMTYPE
                    entry.linkname = link
                    archive.addfile(entry)
                else:
                    entry.size = 1
                    archive.addfile(entry, io.BytesIO(b"x"))
            for index in range(tail):
                entry = tarfile.TarInfo(f"usr/share/test/{index:05d}-" + "x" * 100)
                entry.size = 1
                archive.addfile(entry, io.BytesIO(b"x"))
            if duplicate:
                archive.addfile(tarfile.TarInfo(REQUIRED[0]))

    def check(self, code):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), str(self.path)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, code, result.stderr)

    def test_large_tail_and_normalized_paths(self):
        for prefix in ("./", ""):
            with self.subTest(prefix=prefix):
                self.make(prefix, tail=12000)
                self.check(0)

    def test_missing(self):
        self.make(missing=True)
        self.check(2)

    def test_trailer_truncation(self):
        self.make(tail=12000)
        self.path.write_bytes(self.path.read_bytes()[:-8])
        self.check(3)

    def test_bad_crc(self):
        self.make()
        data = bytearray(self.path.read_bytes())
        data[-8] ^= 1
        self.path.write_bytes(data)
        self.check(3)

    def test_duplicate(self):
        self.make(duplicate=True)
        self.check(3)

    def test_valid_absolute_rootfs_symlink(self):
        self.make(link="/" + REQUIRED[1])
        self.check(0)

    def test_dangling_and_cyclic_links(self):
        for link in ("missing", "mac80211.sh", "../../../../escape"):
            self.make(link=link)
            self.check(2)

    def test_unreadable(self):
        self.check(4)


if __name__ == "__main__":
    unittest.main()
