#!/usr/bin/env python3
"""Verify one cache file using an independently known hash; optionally evict only it."""

import argparse
import hashlib
import re
import sys
from pathlib import Path


def verify(root, relative, expected, evict=False):
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
        raise ValueError("Expected a trusted SHA256")
    root = root.resolve(strict=True)
    name = Path(relative)
    if name.is_absolute() or ".." in name.parts:
        raise ValueError("Cache path must be relative without parent traversal")
    candidate = root / name
    # No symlinks, including ancestors: eviction must never affect external files.
    for parent in [candidate, *candidate.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError("Symlink cache paths cannot be evicted")
    candidate = candidate.resolve(strict=True)
    if root not in candidate.parents or not candidate.is_file():
        raise ValueError("Cache file must be inside cache root")
    digest = hashlib.sha256()
    with candidate.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    valid = digest.hexdigest() == expected.lower()
    if not valid and evict:
        candidate.unlink()
    return valid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("relative")
    parser.add_argument("sha256")
    parser.add_argument("--evict-corrupt", action="store_true")
    args = parser.parse_args()
    try:
        valid = verify(args.root, args.relative, args.sha256, args.evict_corrupt)
    except (ValueError, OSError) as error:
        sys.exit(str(error))
    print(
        "Cache hash valid"
        if valid
        else "Cache hash mismatch"
        + ("; specified file evicted" if args.evict_corrupt else "")
    )
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
