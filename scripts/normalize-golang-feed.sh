#!/usr/bin/env bash
set -Eeuo pipefail

golang_dir="${1:?Usage: normalize-golang-feed.sh <golang-feed-directory>}"
values_file="${golang_dir}/golang-values.mk"
[[ -f "$values_file" ]] || {
  echo "Missing Go version metadata: ${values_file}" >&2
  exit 1
}

default_version="$(sed -n 's/^GO_DEFAULT_VERSION:=//p' "$values_file" | head -n 1)"
[[ "$default_version" =~ ^[0-9]+\.[0-9]+$ ]] || {
  echo "Unable to read a valid GO_DEFAULT_VERSION from ${values_file}" >&2
  exit 1
}

if [[ -f "${golang_dir}/golang${default_version}/Makefile" ]]; then
  echo "Go feed default ${default_version} is available" >&2
  printf '%s\n' "$default_version"
  exit 0
fi

echo "Go feed default ${default_version} is unavailable. Refusing an unverified downgrade; select a coherent source manifest." >&2
exit 1
