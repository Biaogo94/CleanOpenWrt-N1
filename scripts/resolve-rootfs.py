#!/usr/bin/env python3
"""Freeze the latest firmware release once before downloading rootfs and checksums."""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

# Python adds the script directory to sys.path for direct CLI invocation.
from build_inputs import remote, require  # pyright: ignore[reportMissingImports]


def safe_url(value):
    parsed = urlsplit(value)
    require(
        parsed.scheme == "https"
        and parsed.hostname
        and not parsed.username
        and not parsed.password
        and not re.search(r"[\s\x00-\x1f]", value),
        "Expected an HTTPS URL without credentials or whitespace",
    )
    return value


def select(release):
    require(
        isinstance(release, dict)
        and isinstance(release.get("draft"), bool)
        and not release["draft"]
        and isinstance(release.get("prerelease"), bool)
        and not release["prerelease"],
        "Expected a published firmware release",
    )
    selected = {}
    for name in ("rootfs.tar.gz", "SHA256SUMS"):
        assets = [
            a
            for a in release["assets"]
            if a["name"] == name and a.get("state") == "uploaded"
        ]
        require(len(assets) == 1, "Missing/ambiguous firmware asset")
        asset = assets[0]
        url = safe_url(asset["browser_download_url"])
        require(
            "/releases/download/" in url and "/latest/" not in url,
            "Asset URL must identify a concrete release",
        )
        selected[name] = {"url": url, "id": asset["id"]}
    prefixes = {item["url"].rsplit("/", 1)[0] for item in selected.values()}
    require(len(prefixes) == 1, "Assets do not belong to the same release")
    require(
        isinstance(release.get("id"), int) and isinstance(release.get("tag_name"), str),
        "Invalid release identity",
    )
    return {"release_id": release["id"], "tag": release["tag_name"], "assets": selected}


def checksum(text):
    hashes = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") in (
            "rootfs.tar.gz",
            "./rootfs.tar.gz",
        ):
            require(
                re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]), "Invalid rootfs checksum"
            )
            hashes.append(parts[0].lower())
    require(len(hashes) == 1, "Expected exactly one rootfs checksum")
    return hashes[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("resolve", "checksum"))
    parser.add_argument("--repository", default="Biaogo94/CleanOpenWrt-N1")
    parser.add_argument("--url", default="")
    parser.add_argument("--sha256", default="")
    parser.add_argument("--file")
    parser.add_argument("--provenance", default="rootfs-source.json")
    args = parser.parse_args()
    if args.operation == "checksum":
        print(checksum(Path(args.file).read_text()))
        return
    if args.url:
        safe_url(args.url)
        require(
            re.fullmatch(r"[0-9a-fA-F]{64}", args.sha256),
            "Explicit URL requires SHA256",
        )
        parsed = urlsplit(args.url)
        selected = {
            "override": True,
            "sha256": args.sha256.lower(),
            "url": args.url
            if parsed.hostname == "github.com"
            and "/releases/download/" in parsed.path
            and not parsed.query
            and not parsed.fragment
            else "<REDACTED>",
        }
        # Do not save potentially signed/query-bearing custom URLs in provenance.
        url, digest, sums = args.url, args.sha256.lower(), ""
    else:
        require(not args.sha256, "SHA256 without URL is ambiguous")
        require(
            re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository),
            "Invalid repository",
        )
        try:
            release = json.loads(
                remote(
                    f"https://api.github.com/repos/{args.repository}/releases/latest"
                )
            )
        except (ValueError, OSError) as error:
            raise ValueError("Cannot read latest firmware release") from error
        selected = select(release)
        url = selected["assets"]["rootfs.tar.gz"]["url"]
        sums = selected["assets"]["SHA256SUMS"]["url"]
        digest = ""
    Path(args.provenance).write_text(json.dumps(selected, indent=2) + "\n")
    print(f"url={url}\nsha256={digest}\nsha256_url={sums}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError):
        sys.exit(
            "Rootfs resolution failed: check published assets, explicit URL/checksum and network availability"
        )
