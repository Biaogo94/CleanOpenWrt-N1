#!/usr/bin/env python3
"""Require a manifest SHA256 match before EasyTier extraction can execute."""

import sys
from pathlib import Path


def patch(text):
    lines = text.splitlines()
    matches = [
        i
        for i, line in enumerate(lines)
        if "unzip -o -j $(PKG_BUILD_DIR)/easytier-$(PKG_VERSION).zip" in line
    ]
    if len(matches) != 1 or "EASYTIER_AARCH64_SHA256" in text:
        raise ValueError("Expected one unpatched EasyTier extraction command")
    lines.insert(
        matches[0],
        '\t\techo "$(EASYTIER_AARCH64_SHA256)  $(PKG_BUILD_DIR)/easytier-$(PKG_VERSION).zip" | sha256sum -c - || exit 1; '
        + "\\",
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    try:
        path = Path(sys.argv[1])
        path.write_text(patch(path.read_text()))
    except (ValueError, OSError) as error:
        sys.exit(str(error))
