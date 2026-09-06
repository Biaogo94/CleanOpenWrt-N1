#!/usr/bin/env python3
"""Disable ephemeral Rust CI LLVM downloads, refusing unknown upstream layouts."""

import re
import sys
from pathlib import Path


def patch(text):
    pattern = r"--set=llvm\.download-ci-llvm=(true|false|1|0)\b"
    if len(re.findall(pattern, text)) != 1:
        raise ValueError("Expected exactly one Rust LLVM download setting")
    return re.sub(pattern, "--set=llvm.download-ci-llvm=false", text)


if __name__ == "__main__":
    try:
        path = Path(sys.argv[1])
        path.write_text(patch(path.read_text()))
    except (ValueError, OSError) as error:
        sys.exit(str(error))
