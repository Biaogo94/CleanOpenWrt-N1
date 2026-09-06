#!/usr/bin/env python3
"""Validate a rootfs without extracting it; read gzip to EOF (including its CRC)."""

import argparse
import gzip
import posixpath
import sys
import tarfile
import zlib
from pathlib import PurePosixPath

REQUIRED = (
    "lib/netifd/wireless/mac80211.sh",
    "lib/firmware/brcm/brcmfmac43455-sdio.bin",
    "lib/firmware/brcm/brcmfmac43455-sdio.clm_blob",
    "usr/share/passwall/clash_subconverter.lua",
)


class InvalidArchive(ValueError):
    pass


def member_name(name):
    if name.startswith("/") or ".." in PurePosixPath(name).parts:
        raise InvalidArchive("unsafe member path")
    return posixpath.normpath(name)


def resolves_to_file(name, members, seen=None):
    seen = set() if seen is None else seen
    if name in seen or len(seen) > 64:
        return False
    seen.add(name)
    # Resolve directory symlinks as well as a symlink at the leaf.
    parts = name.split("/")
    for index in range(1, len(parts) + 1):
        prefix = "/".join(parts[:index])
        entry = members.get(prefix)
        if entry and (entry.issym() or entry.islnk()):
            base = (
                ""
                if entry.islnk() or entry.linkname.startswith("/")
                else posixpath.dirname(prefix)
            )
            target = posixpath.normpath(
                posixpath.join(base, entry.linkname.lstrip("/"), *parts[index:])
            )
            if target == ".." or target.startswith("../"):
                return False
            return resolves_to_file(target, members, seen)
    entry = members.get(name)
    return entry is not None and entry.isfile()


def validate(path, required=REQUIRED):
    members = {}
    with gzip.GzipFile(filename=path, mode="rb") as stream:
        with tarfile.open(fileobj=stream, mode="r|") as archive:
            for entry in archive:
                name = member_name(entry.name)
                if name in members:
                    raise InvalidArchive("duplicate normalized member: " + name)
                members[name] = entry
        # tar stops at its end marker; gzip CRC/trailer may come later.
        while stream.read(1024 * 1024):
            pass
    return [name for name in required if not resolves_to_file(name, members)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    args = parser.parse_args()
    try:
        missing = validate(args.archive)
    except (
        gzip.BadGzipFile,
        EOFError,
        tarfile.TarError,
        InvalidArchive,
        zlib.error,
    ) as error:
        print("rootfs corrupt/unsafe: " + str(error), file=sys.stderr)
        return 3
    except OSError:
        print("rootfs read failed", file=sys.stderr)
        return 4
    if missing:
        print(
            "rootfs required files missing or unresolved: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 2
    print("rootfs validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
