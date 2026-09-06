#!/usr/bin/env bash
# Compatibility entry: resolution now produces a complete manifest, not floating env only.
set -Eeuo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${BUILDER_IMAGE_DIGEST:?Resolve/pull Builder first and supply image@sha256 digest}"
manifest="${INPUT_MANIFEST:-${REPO_DIR}/build-inputs.json}"
python3 "$REPO_DIR/scripts/build_inputs.py" resolve --builder "$BUILDER_IMAGE_DIGEST" --manifest "$manifest"
python3 "$REPO_DIR/scripts/build_inputs.py" env --manifest "$manifest"
