#!/usr/bin/env python3
"""Verify enabled Xray source declares a Go version supported by host toolchain."""

import hashlib
import http.client
import io
import json
import re
import tarfile
from pathlib import Path
from urllib.parse import urlsplit


def version(text):
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", text.strip())
    if match is None:
        raise ValueError("invalid Go version: " + text)
    major, minor, patch = match.groups()
    try:
        return int(major), int(minor), int(patch or 0)
    except (TypeError, ValueError) as error:
        raise ValueError("invalid Go version: " + text) from error


def download(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.fragment:
        raise ValueError("Xray source URL must be a safe HTTPS URL")
    connection = http.client.HTTPSConnection(parsed.netloc, timeout=60)
    try:
        connection.request(
            "GET",
            parsed.path + ("?" + parsed.query if parsed.query else ""),
            headers={"User-Agent": "CleanOpenWrt-N1"},
        )
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("Xray source download failed")
        payload = response.read(64 * 1024 * 1024 + 1)
        if len(payload) > 64 * 1024 * 1024:
            raise ValueError("Xray source is too large")
        return payload
    finally:
        connection.close()


def check(source, selected_go):
    makefile = Path(source) / "package/feeds/passwall_packages/xray-core/Makefile"
    text = makefile.read_text()
    if "github.com/XTLS/Xray-core" not in text:
        raise ValueError("Xray source layout is unsupported")
    package_version = re.search(r"^PKG_VERSION:=([^\s]+)$", text, re.MULTILINE)
    source_url = re.search(r"^PKG_SOURCE_URL:=([^\s]+)$", text, re.MULTILINE)
    source_hash = re.search(r"^PKG_HASH:=([0-9a-f]{64})$", text, re.MULTILINE)
    if package_version is None or source_url is None or source_hash is None:
        raise ValueError("Xray source metadata is incomplete")
    version_text = package_version.group(1)
    archive = Path(source) / "dl" / ("Xray-core-" + version_text + ".tar.gz")
    if archive.exists():
        payload = archive.read_bytes()
    else:
        url = source_url.group(1).replace("$(PKG_VERSION)", version_text)
        payload = download(url)
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(payload)
    expected_hash = source_hash.group(1)
    if hashlib.sha256(payload).hexdigest() != expected_hash:
        raise ValueError("Xray source SHA256 mismatch")
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
        go_mod = next(
            (
                m
                for m in tar.getmembers()
                if m.name.endswith("/go.mod") or m.name == "go.mod"
            ),
            None,
        )
        if go_mod is None:
            raise ValueError("Xray source go.mod is missing")
        go_file = tar.extractfile(go_mod)
        if go_file is None:
            raise ValueError("Xray source go.mod cannot be read")
        minimum = re.search(
            r"^go\s+([0-9]+\.[0-9]+(?:\.[0-9]+)?)\s*$",
            go_file.read().decode(),
            re.MULTILINE,
        )
    if minimum is None:
        raise ValueError("Xray go.mod has no supported Go requirement")
    minimum_go = minimum.group(1)
    if version(selected_go) < version(minimum_go):
        raise ValueError(f"Xray requires Go {minimum_go}; selected {selected_go}")
    return {
        "package_version": version_text,
        "minimum_go": minimum_go,
        "sha256": expected_hash,
    }


if __name__ == "__main__":
    import sys

    try:
        print(json.dumps(check(sys.argv[1], sys.argv[2]), sort_keys=True))
    except (OSError, ValueError, tarfile.TarError, UnicodeError) as error:
        print("Go consumer check failed: " + str(error), file=sys.stderr)
        sys.exit(1)
