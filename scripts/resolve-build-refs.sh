#!/usr/bin/env bash
set -Eeuo pipefail

readonly REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
. "${REPO_DIR}/build-lock.env"
[[ "$LOCK_SCHEMA" == "2" ]] || { echo "Unsupported build lock schema" >&2; exit 1; }

resolve_ref() {
  local repository="$1" branch="$2" ref
  ref="$(git ls-remote "$repository" "refs/heads/$branch" | awk 'NR == 1 { print $1 }')"
  [[ "$ref" =~ ^[0-9a-f]{40}$ ]] || {
    echo "Unable to resolve ${repository} branch ${branch}" >&2
    exit 1
  }
  printf '%s' "$ref"
}

IMMORTALWRT_REF="$(resolve_ref https://github.com/immortalwrt/immortalwrt.git "$LOCK_IMMORTALWRT_BRANCH")"
IMMORTALWRT_PACKAGES_REF="$(resolve_ref https://github.com/immortalwrt/packages.git "$LOCK_IMMORTALWRT_PACKAGES_BRANCH")"
IMMORTALWRT_LUCI_REF="$(resolve_ref https://github.com/immortalwrt/luci.git "$LOCK_IMMORTALWRT_LUCI_BRANCH")"
PASSWALL_PACKAGES_REF="$(resolve_ref https://github.com/Openwrt-Passwall/openwrt-passwall-packages.git "$LOCK_PASSWALL_PACKAGES_BRANCH")"
PASSWALL_LUCI_REF="$(resolve_ref https://github.com/Openwrt-Passwall/openwrt-passwall.git "$LOCK_PASSWALL_LUCI_BRANCH")"
OPENCLASH_REF="$(resolve_ref https://github.com/vernesong/OpenClash.git "$LOCK_OPENCLASH_BRANCH")"
EASYTIER_OPENWRT_REF="$(resolve_ref https://github.com/EasyTier/luci-app-easytier.git "$LOCK_EASYTIER_OPENWRT_BRANCH")"
AMLOGIC_REF="$(resolve_ref https://github.com/ophub/luci-app-amlogic.git "$LOCK_AMLOGIC_BRANCH")"

SOURCE_SET_ID="$(printf '%s\n' \
  "$IMMORTALWRT_REF" \
  "$IMMORTALWRT_PACKAGES_REF" \
  "$IMMORTALWRT_LUCI_REF" \
  "$PASSWALL_PACKAGES_REF" \
  "$PASSWALL_LUCI_REF" \
  "$OPENCLASH_REF" \
  "$EASYTIER_OPENWRT_REF" \
  "$AMLOGIC_REF" \
  | sha256sum | awk '{print $1}')"

for name in \
  IMMORTALWRT_REF \
  IMMORTALWRT_PACKAGES_REF \
  IMMORTALWRT_LUCI_REF \
  PASSWALL_PACKAGES_REF \
  PASSWALL_LUCI_REF \
  OPENCLASH_REF \
  EASYTIER_OPENWRT_REF \
  AMLOGIC_REF \
  SOURCE_SET_ID; do
  printf '%s=%s\n' "$name" "${!name}"
done
