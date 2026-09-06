#!/usr/bin/env bash
# Production seam: failed preflight never executes make download/world.
set -Eeuo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="${1:?source directory}"
BUILD_MODE="${2:?full or preflight}"
DIAGNOSTIC_DIR="${3:?diagnostic directory}"
[[ "$BUILD_MODE" == full || "$BUILD_MODE" == preflight ]] || exit 2
PYTHON="${PYTHON:-python3}"
mkdir -p "$DIAGNOSTIC_DIR"
printf 'preflight\n' >"$DIAGNOSTIC_DIR/current-stage.txt"
"$PYTHON" "$REPO_DIR/scripts/run-stage.py" "$DIAGNOSTIC_DIR" preflight "$PYTHON" "$REPO_DIR/scripts/preflight.py" "$SOURCE_DIR"
[[ "$BUILD_MODE" == full ]] || exit 0
cd "$SOURCE_DIR"
run_stage() {
  printf '%s\n' "$1" >"$DIAGNOSTIC_DIR/current-stage.txt"
  "$PYTHON" "$REPO_DIR/scripts/run-stage.py" "$DIAGNOSTIC_DIR" "$@"
}
# The OpenWrt downloader owns source checksum verification and targeted refetch.
# Command-line make variables override the upstream DL_DIR/go-mod-cache default.
make_cache=()
if [[ -n "${GO_MOD_CACHE_DIR:-}" ]]; then
  make_cache+=("GO_MOD_CACHE_DIR=$GO_MOD_CACHE_DIR")
fi
run_stage download make "${make_cache[@]}" download -j"$(nproc)" || run_stage download-retry make "${make_cache[@]}" download -j1 V=s
run_stage compile make "${make_cache[@]}" -j"$(nproc)" || run_stage compile-retry make "${make_cache[@]}" -j1 V=s
