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

available_version="$(
  find "$golang_dir" -mindepth 2 -maxdepth 2 -type f -path '*/golang1.*/Makefile' -printf '%h\n' \
    | xargs -r -n 1 basename \
    | sed 's/^golang//' \
    | sort -V \
    | tail -n 1
)"
[[ "$available_version" =~ ^[0-9]+\.[0-9]+$ ]] || {
  echo "No usable golang1.x package exists below ${golang_dir}" >&2
  exit 1
}

echo "Go feed default ${default_version} is unavailable; using ${available_version}" >&2
sed -i -E "s/^GO_DEFAULT_VERSION:=.*/GO_DEFAULT_VERSION:=${available_version}/" "$values_file"
printf '%s\n' "$available_version"
