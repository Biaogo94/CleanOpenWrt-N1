#!/usr/bin/env python3
"""Run one build stage; persist bounded, redacted logs and timing even on failure."""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import deque
from pathlib import Path


def redact(text):
    for key, value in os.environ.items():
        if re.search(r"TOKEN|PASSWORD|SECRET|CREDENTIAL", key, re.IGNORECASE) and value:
            text = text.replace(value, "<REDACTED>")
    text = re.sub(r"(?i)(authorization\s*[:=]\s*).*", r"\1<REDACTED>", text)
    text = re.sub(r"https?://\S+", "<URL>", text)
    text = re.sub(
        r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b", "<REDACTED>", text
    )
    return text


def run(directory, stage, command):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,40}", stage):
        raise ValueError("Invalid stage name")
    directory.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    status = {"stage": stage, "status": "running"}
    status_file = directory / (stage + ".json")
    status_file.write_text(json.dumps(status) + "\n")
    code = 1
    size = 0
    tail_size = 0
    tail = deque()
    limit = 1024 * 1024
    try:
        with (
            (directory / (stage + ".log")).open("w", encoding="utf-8") as log,
            subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
            ) as process,
        ):
            if process.stdout is None:
                raise RuntimeError("Stage stdout unavailable")
            for line in process.stdout:
                safe = redact(line)
                print(safe, end="", flush=True)
                bounded = safe[:16384]
                if size < limit:
                    log.write(bounded)
                    size += len(bounded.encode())
                tail.append(bounded)
                tail_size += len(bounded.encode())
                while tail_size > limit and len(tail) > 1:
                    tail_size -= len(tail.popleft().encode())
            code = process.wait()
    finally:
        # Preserve the error at the end of a multi-hour log, not just its setup.
        (directory / (stage + "-tail.log")).write_text("".join(tail), encoding="utf-8")
        status.update(
            status="success" if code == 0 else "failed",
            exit_code=code,
            seconds=round(time.monotonic() - started, 2),
            log_limit_bytes=2 * 1024 * 1024,
        )
        status_file.write_text(json.dumps(status, indent=2) + "\n")
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("stage")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.command:
        parser.error("command is required")
    return run(args.directory, args.stage, args.command)


if __name__ == "__main__":
    sys.exit(main())
