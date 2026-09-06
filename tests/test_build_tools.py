"""Offline contracts for real manifest, release, preflight and cache modules."""

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def module(name):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), SCRIPTS / (name + ".py")
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(name)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


inputs = module("build_inputs")
release = module("resolve-rootfs")
preflight = module("preflight")
cache = module("verify-cache")
rust = module("patch-rust")


def fixture_manifest():
    sources = {
        key: {"url": f"https://github.com/{repo}.git", "ref": "a" * 40}
        for key, (repo, _) in inputs.SOURCES.items()
    }
    feeds = inputs.parse_feeds(
        "src-git packages https://github.com/immortalwrt/packages.git;openwrt-25.12\nsrc-git luci https://github.com/immortalwrt/luci.git;openwrt-25.12",
        sources,
    )
    data = {
        "schema": 1,
        "project_ref": inputs.command("git", "rev-parse", "HEAD"),
        "input_hash": inputs.identity(),
        "builder": inputs.lock_values()["LOCK_BUILDER_IMAGE"] + "@sha256:" + "b" * 64,
        "sources": sources,
        "feeds": feeds,
        "easytier": {"version": "2.5.0", "sha256": "c" * 64},
    }
    data["source_set_id"] = inputs.checksum(inputs.canonical(data))
    return data


class InputTests(unittest.TestCase):
    def test_replay_does_not_resolve_remote(self):
        data = fixture_manifest()
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(inputs, "remote", side_effect=AssertionError("network")),
            patch.object(
                inputs, "resolve_ref", side_effect=AssertionError("resolution")
            ),
        ):
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps(data))
            self.assertEqual(inputs.load(path), data)

    def test_invalid_fields_and_integrity(self):
        data = fixture_manifest()
        for change in (
            {"schema": 9},
            {"builder": "image:latest"},
            {"extra": "oops"},
            {"source_set_id": "0" * 64},
            {"input_hash": "0" * 64},
            {"sources": {}},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                inputs.validate({**data, **change})

    def test_same_hash_different_project_rejected(self):
        data = fixture_manifest()
        data["project_ref"] = "0" * 40
        data["source_set_id"] = inputs.checksum(
            inputs.canonical({k: v for k, v in data.items() if k != "source_set_id"})
        )
        with self.assertRaisesRegex(ValueError, "original project"):
            inputs.validate(data)

    def test_all_feeds_frozen_without_re_resolving(self):
        data = fixture_manifest()
        text = "src-git routing https://github.com/openwrt/routing.git;openwrt-25.12"
        with patch.object(inputs, "resolve_ref", return_value="d" * 40) as resolver:
            feeds = inputs.parse_feeds(text, data["sources"])
            resolver.assert_called_once()
        with patch.object(
            inputs, "resolve_ref", side_effect=AssertionError("moving upstream")
        ):
            self.assertEqual(
                inputs.parse_feeds(
                    text, data["sources"], {f["name"]: f for f in feeds}
                ),
                feeds,
            )
            with self.assertRaisesRegex(ValueError, "omitted"):
                inputs.parse_feeds(text, data["sources"], {})

    def test_duplicate_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text('{"schema":1,"schema":1}')
            with self.assertRaises(ValueError):
                inputs.load(path)

    def test_injection_and_non_https_sources_rejected(self):
        for url in (
            "file:///etc/passwd",
            "https://github.com/o/r.git'; touch /tmp/evil",
            "https://user:pass@github.com/o/r",
        ):
            with self.assertRaises(ValueError):
                inputs.git_url(url)


class ReleaseTests(unittest.TestCase):
    def fixture(self):
        return {
            "id": 1,
            "tag_name": "r1",
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "id": index,
                    "name": name,
                    "state": "uploaded",
                    "browser_download_url": "https://github.com/o/r/releases/download/r1/"
                    + name,
                }
                for index, name in enumerate(("rootfs.tar.gz", "SHA256SUMS"))
            ],
        }

    def test_fixed_release_survives_latest_change(self):
        upstream = self.fixture()
        selected = release.select(upstream)
        upstream["tag_name"] = "r2"
        upstream["assets"][0]["browser_download_url"] = (
            "https://github.com/o/r/releases/download/r2/rootfs.tar.gz"
        )
        self.assertIn("/r1/", selected["assets"]["rootfs.tar.gz"]["url"])
        with self.assertRaises(ValueError):
            release.select(upstream)

    def test_duplicate_asset_and_checksum_rejected(self):
        upstream = self.fixture()
        upstream["assets"].append(copy.deepcopy(upstream["assets"][0]))
        with self.assertRaises(ValueError):
            release.select(upstream)
        line = "a" * 64 + "  rootfs.tar.gz\n"
        self.assertEqual(release.checksum(line), "a" * 64)
        for text in (line * 2, "bad  rootfs.tar.gz", "a" * 64 + " other-rootfs.tar.gz"):
            with self.assertRaises(ValueError):
                release.checksum(text)

    def test_urls_with_credentials_or_newlines_rejected(self):
        for url in (
            "http://example.com/x",
            "https://u:p@example.com/x",
            "https://example.com/x\nsha256=evil",
        ):
            with self.assertRaises(ValueError):
                release.safe_url(url)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / "feeds/packages/lang/golang/golang1.26"
        self.target.mkdir(parents=True)
        (self.target / "Makefile").write_text("host package")
        (self.target.parent / "golang-values.mk").write_text(
            "GO_DEFAULT_VERSION:=1.26\n"
        )
        installed = self.root / "package/feeds/packages"
        installed.mkdir(parents=True)
        try:
            (installed / "golang1.26").symlink_to(self.target, target_is_directory=True)
        except OSError:
            self.skipTest("OS does not permit symlinks")
        (installed / "golang").mkdir()
        self.dummy = installed / "golang/Makefile"
        self.dummy.write_text(
            "PKG_VERSION:=$(GO_DEFAULT_VERSION)\nHOST_BUILD_DEPENDS:=golang$(PKG_VERSION)/host\n"
        )
        (self.root / ".config").write_text(
            "\n".join(f"CONFIG_{s}=y" for s in preflight.REQUIRED)
        )

    def test_good_and_missing_effective_config(self):
        self.assertEqual(preflight.check(self.root), "1.26")
        (self.root / ".config").write_text("")
        with self.assertRaisesRegex(ValueError, "config"):
            preflight.check(self.root)

    def test_stale_target_and_dependency_rejected(self):
        self.dummy.write_text("HOST_BUILD_DEPENDS:=golang1.27/host\n")
        with self.assertRaisesRegex(ValueError, "dependency"):
            preflight.check(self.root)
        (self.target / "Makefile").unlink()
        with self.assertRaisesRegex(ValueError, "source missing"):
            preflight.check(self.root)

    def test_preflight_routing_never_compiles(self):
        fakebin = self.root / "bin"
        fakebin.mkdir()
        marker = self.root / "make-called"
        fake_make = fakebin / "make"
        fake_make.write_text('#!/bin/sh\nprintf called > "$MAKE_MARKER"\nexit 99\n')
        fake_make.chmod(0o755)
        env = {
            **os.environ,
            "PYTHON": sys.executable,
            "MAKE_MARKER": str(marker),
            "PATH": str(fakebin) + os.pathsep + os.environ["PATH"],
        }
        args = [
            "bash",
            str(SCRIPTS / "compile-rootfs.sh"),
            str(self.root),
            "preflight",
            str(self.root / "diagnostics"),
        ]
        result = subprocess.run(
            args, env=env, capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        (self.root / ".config").write_text("")
        args[3] = "full"
        result = subprocess.run(
            args, env=env, capture_output=True, text=True, check=False
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Preflight failed", result.stdout + result.stderr)
        self.assertFalse(marker.exists())

    def test_go_missing_default_does_not_fallback(self):
        (self.target.parent / "golang-values.mk").write_text(
            "GO_DEFAULT_VERSION:=1.27\n"
        )
        result = subprocess.run(
            [
                "bash",
                str(SCRIPTS / "normalize-golang-feed.sh"),
                str(self.target.parent),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing", result.stderr)
        self.assertIn("1.27", (self.target.parent / "golang-values.mk").read_text())

    def test_rust_patch_requires_known_context(self):
        self.assertIn("=false", rust.patch("--set=llvm.download-ci-llvm=true"))
        for text in ("unknown", "--set=llvm.download-ci-llvm=true " * 2):
            with self.assertRaises(ValueError):
                rust.patch(text)


class CacheAndDiagnosticsTests(unittest.TestCase):
    def test_small_cache_file_preserved_corruption_targeted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "small").write_bytes(b"x")
            (root / "bad").write_bytes(b"bad")
            expected = hashlib.sha256(b"x").hexdigest()
            self.assertTrue(cache.verify(root, "small", expected, evict=True))
            self.assertFalse(cache.verify(root, "bad", expected, evict=True))
            self.assertEqual((root / "small").read_bytes(), b"x")
            self.assertFalse((root / "bad").exists())
            with self.assertRaises(ValueError):
                cache.verify(root, "../outside", expected, evict=True)

    def test_easytier_bad_hash_stops_before_unzip(self):
        patcher = module("patch-easytier")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "easytier-1.zip").write_bytes(b"bad")
            marker = root / "unzip-called"
            text = "if true; then \\\n\tunzip -o -j $(PKG_BUILD_DIR)/easytier-$(PKG_VERSION).zip; \\\n\ttouch unexpected; \\\nfi\n"
            patched = (
                patcher.patch(text)
                .replace("$(PKG_BUILD_DIR)", ".")
                .replace("$(PKG_VERSION)", "1")
                .replace("$(EASYTIER_AARCH64_SHA256)", "0" * 64)
            )
            # A shell function is a test double for extraction, not for the checksum.
            command = "unzip() { touch unzip-called; };\n" + patched
            result = subprocess.run(
                ["bash", "-c", command],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())
            self.assertFalse((root / "unexpected").exists())

    def test_large_log_keeps_final_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = "import sys; [print('x' * 1024) for _ in range(2200)]; print('FINAL-FAILURE'); sys.exit(9)"
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPTS / "run-stage.py"),
                    tmp,
                    "large",
                    sys.executable,
                    "-c",
                    code,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 9)
            tail = Path(tmp) / "large-tail.log"
            self.assertIn("FINAL-FAILURE", tail.read_text())
            self.assertLessEqual(tail.stat().st_size, 1024 * 1024 + 16384)

    def test_failure_status_and_secrets_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            secret = os.urandom(24).hex()
            env = {**os.environ, "TEST_SECRET": secret}
            code = "import os,sys; print(os.environ['TEST_SECRET']); print('Authorization: Bearer something'); print('https://user:pass@example.com/?token=secret'); sys.exit(7)"
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPTS / "run-stage.py"),
                    tmp,
                    "fixture",
                    sys.executable,
                    "-c",
                    code,
                ],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 7, result.stderr)
            log = (Path(tmp) / "fixture.log").read_text()
            self.assertNotIn(secret, log + result.stdout)
            self.assertNotIn("user:pass", log)
            self.assertNotIn("Bearer something", log)
            status = json.loads((Path(tmp) / "fixture.json").read_text())
            self.assertEqual(status["status"], "failed")
            self.assertEqual(status["exit_code"], 7)


if __name__ == "__main__":
    unittest.main()
