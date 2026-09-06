#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
# actionlint silently skips integrated shell analysis if ShellCheck is absent.
# Require both tools in this process so local validation matches CI.
command -v shellcheck >/dev/null
command -v actionlint >/dev/null
"${PYTHON:-python3}" scripts/build_inputs.py lock
while IFS= read -r -d '' script; do
  bash -n "$script"
  shellcheck -x "$script"
done < <(find scripts -maxdepth 1 -name '*.sh' -print0)
while IFS= read -r -d '' script; do
  sh -n "$script"
  # OpenWrt sources /lib/functions.sh and defines runtime globals on device.
  shellcheck -s sh -e SC1091,SC2034 "$script"
done < <(find n1-overlay/etc/uci-defaults -type f -print0)
actionlint
