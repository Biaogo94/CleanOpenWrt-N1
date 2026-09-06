"""Execute and lint the actual rootfs-release workflow shell block."""

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def release_script():
    lines = (ROOT / ".github/workflows/build-rootfs.yaml").read_text().splitlines()
    start = lines.index("      - name: Prepare rootfs release")
    run = lines.index("        run: |", start)
    body = []
    for line in lines[run + 1 :]:
        if line and not line.startswith("          "):
            break
        body.append(line[10:])
    return (
        "set -euo pipefail\n"
        + "\n".join(body).replace("${{ github.run_number }}", "123")
        + "\n"
    )


class ReleaseWorkflowTests(unittest.TestCase):
    @unittest.skipUnless(
        shutil.which("shellcheck"), "ShellCheck must be installed (required in CI)"
    )
    def test_release_block_passes_integrated_shellcheck(self):
        result = subprocess.run(
            ["shellcheck", "--shell=bash", "-"],
            input=release_script().encode(),
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_release_checksums_exclude_their_own_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "rootfs"
            artifacts.mkdir()
            files = {"image-rootfs.tar.gz": b"fixture", "BUILD INFO.txt": b"metadata"}
            for name, content in files.items():
                (artifacts / name).write_bytes(content)
            (artifacts / "SHA256SUMS").write_text("stale checksum file\n")
            output = root / "outputs"
            env = {**os.environ, "GITHUB_OUTPUT": output.as_posix()}
            result = subprocess.run(
                ["bash", "-c", release_script()],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            expected = "".join(
                f"{hashlib.sha256(files[name]).hexdigest()}  {name}\n"
                for name in sorted(files)
            )
            self.assertEqual(
                (artifacts / "SHA256SUMS").read_text().replace(" *", "  "), expected
            )
            self.assertEqual(
                output.read_text().splitlines(),
                [
                    "name=image-rootfs.tar.gz",
                    "sha256="
                    + hashlib.sha256(files["image-rootfs.tar.gz"]).hexdigest(),
                    "tag=ImmortalWrt-N1-rootfs-r123",
                ],
            )


if __name__ == "__main__":
    unittest.main()
