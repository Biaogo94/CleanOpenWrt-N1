#!/usr/bin/env bash
set -Eeuo pipefail

readonly WORKSPACE="${WORKSPACE:-/workspace}"
readonly SOURCE_DIR="${SOURCE_DIR:-${WORKSPACE}/.build/immortalwrt}"
readonly CACHE_DIR="${CACHE_DIR:-/cache}"
readonly ARTIFACT_DIR="${ARTIFACT_DIR:-${WORKSPACE}/artifacts/rootfs}"
readonly IMMORTALWRT_BRANCH="${IMMORTALWRT_BRANCH:-openwrt-25.12}"
readonly IMMORTALWRT_REF="${IMMORTALWRT_REF:-3a0e732472ba6b0476bd974a01cdb7930e13f7fe}"
readonly IMMORTALWRT_PACKAGES_REF="${IMMORTALWRT_PACKAGES_REF:-a874f8aabbf21af382a6bab90d300e50ebccadb0}"
readonly IMMORTALWRT_LUCI_REF="${IMMORTALWRT_LUCI_REF:-5eb439f0f87e125cf0c2ffcbecffa79e4c7c441b}"
readonly PASSWALL_PACKAGES_REF="${PASSWALL_PACKAGES_REF:-f7f253de5d10f4aefa170c4006be926796c88d10}"
readonly PASSWALL_LUCI_REF="${PASSWALL_LUCI_REF:-cfab375650b69b79c52da681a713eaac2dd7bc73}"
readonly OPENCLASH_REF="${OPENCLASH_REF:-c3a33c1d3407956fdf8f0e0b7c1a4c52e6ad9593}"
readonly EASYTIER_OPENWRT_REF="${EASYTIER_OPENWRT_REF:-5a6040b44bcc516c85e9eb3f79e2ddeb8830bcf1}"
readonly AMLOGIC_REF="${AMLOGIC_REF:-8fe2b60b4d63e2d83fbe5eb12c37c77a892c0117}"

export CCACHE_DIR="${CCACHE_DIR:-${CACHE_DIR}/ccache}"
export CCACHE_MAXSIZE="${CCACHE_MAXSIZE:-3G}"

assert_workspace_child() {
  local candidate parent
  candidate="$(realpath -m "$1")"
  parent="$(realpath -m "$WORKSPACE")"
  if [[ "$candidate" == "$parent" || "$candidate" != "$parent"/* ]]; then
    echo "Refusing to delete path outside WORKSPACE: ${candidate}" >&2
    exit 1
  fi
}

assert_workspace_child "$SOURCE_DIR"
assert_workspace_child "$ARTIFACT_DIR"
rm -rf "$SOURCE_DIR" "$ARTIFACT_DIR"
mkdir -p "$(dirname "$SOURCE_DIR")" "$CACHE_DIR/dl" "$CCACHE_DIR" "$ARTIFACT_DIR"

clone_at() {
  local repo="$1" branch="$2" ref="$3" destination="$4"
  echo "Cloning ${repo} branch ${branch} at ${ref}"
  git clone --depth 1 --single-branch --branch "$branch" "$repo" "$destination"
  timeout 900 git -C "$destination" fetch --depth 1 origin "$ref"
  git -C "$destination" checkout -q --detach FETCH_HEAD
}

assert_repo_ref() {
  local repository="$1" expected="$2" actual
  actual="$(git -C "$repository" rev-parse HEAD)"
  [[ "$actual" == "$expected" ]] || {
    echo "Pinned ref mismatch in ${repository}: expected ${expected}, got ${actual}" >&2
    exit 1
  }
}

clone_at https://github.com/immortalwrt/immortalwrt.git "$IMMORTALWRT_BRANCH" "$IMMORTALWRT_REF" "$SOURCE_DIR"
assert_repo_ref "$SOURCE_DIR" "$IMMORTALWRT_REF"
readonly immortalwrt_ref="$IMMORTALWRT_REF"

cd "$SOURCE_DIR"
{
  echo "src-git passwall_packages https://github.com/Openwrt-Passwall/openwrt-passwall-packages.git"
  echo "src-git passwall_luci https://github.com/Openwrt-Passwall/openwrt-passwall.git"
  cat feeds.conf.default
} > feeds.conf
./scripts/feeds update -a
./scripts/feeds install -a

for feed_spec in \
  "feeds/packages:$IMMORTALWRT_PACKAGES_REF" \
  "feeds/luci:$IMMORTALWRT_LUCI_REF" \
  "feeds/passwall_packages:$PASSWALL_PACKAGES_REF" \
  "feeds/passwall_luci:$PASSWALL_LUCI_REF"; do
  feed_dir="${feed_spec%%:*}"
  feed_ref="${feed_spec#*:}"
  echo "Pinning ${feed_dir} at ${feed_ref}"
  timeout 900 git -C "$feed_dir" fetch --depth 1 origin "$feed_ref"
  git -C "$feed_dir" checkout -q --detach FETCH_HEAD
  assert_repo_ref "$feed_dir" "$feed_ref"
done

# The rolling packages feed may enable Rust's CI LLVM download. Those
# artifacts are routinely garbage-collected, which makes reproducible builds
# fail with a 404. Build LLVM locally instead.
rust_makefile="${SOURCE_DIR}/feeds/packages/lang/rust/Makefile"
if [[ -f "$rust_makefile" ]]; then
  sed -i \
    -e 's/--set=llvm\.download-ci-llvm=true/--set=llvm.download-ci-llvm=false/g' \
    -e 's/--set=llvm\.download-ci-llvm=1/--set=llvm.download-ci-llvm=false/g' \
    "$rust_makefile"
fi

assert_repo_ref feeds/passwall_packages "$PASSWALL_PACKAGES_REF"
assert_repo_ref feeds/passwall_luci "$PASSWALL_LUCI_REF"
readonly passwall_packages_ref="$PASSWALL_PACKAGES_REF"
readonly passwall_ref="$PASSWALL_LUCI_REF"

clone_at https://github.com/vernesong/OpenClash.git master "$OPENCLASH_REF" package/OpenClash
assert_repo_ref package/OpenClash "$OPENCLASH_REF"
readonly openclash_ref="$OPENCLASH_REF"
mv package/OpenClash/luci-app-openclash package/luci-app-openclash
rm -rf package/OpenClash

clone_at https://github.com/EasyTier/luci-app-easytier.git main "$EASYTIER_OPENWRT_REF" package/easytier-openwrt
assert_repo_ref package/easytier-openwrt "$EASYTIER_OPENWRT_REF"
readonly easytier_openwrt_ref="$EASYTIER_OPENWRT_REF"
readonly easytier_version="$(sed -n 's/^EASYTIER_VERSION=//p' package/easytier-openwrt/version.mk)"
readonly easytier_asset="easytier-linux-aarch64-v${easytier_version}.zip"

clone_at https://github.com/ophub/luci-app-amlogic.git main "$AMLOGIC_REF" package/luci-app-amlogic
assert_repo_ref package/luci-app-amlogic "$AMLOGIC_REF"
readonly amlogic_ref="$AMLOGIC_REF"

curl_args=(
  --fail --silent --show-error --location
  --header "Accept: application/vnd.github+json"
  --header "X-GitHub-Api-Version: 2022-11-28"
)
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  curl_args+=(--header "Authorization: Bearer ${GITHUB_TOKEN}")
fi
readonly easytier_digest="$(
  curl "${curl_args[@]}" \
    "https://api.github.com/repos/EasyTier/EasyTier/releases/tags/v${easytier_version}" \
    | jq -r --arg asset "$easytier_asset" \
      '.assets[] | select(.name == $asset) | .digest // empty'
)"
readonly easytier_sha256="${easytier_digest#sha256:}"
if [[ ! "$easytier_sha256" =~ ^[0-9a-fA-F]{64}$ ]]; then
  echo "Unable to resolve a SHA256 digest for ${easytier_asset}" >&2
  exit 1
fi
export EASYTIER_AARCH64_SHA256="$easytier_sha256"

python3 - <<'PY'
from pathlib import Path

path = Path("package/easytier-openwrt/easytier-noweb/Makefile")
lines = path.read_text(encoding="utf-8").splitlines()
matches = [
    index
    for index, line in enumerate(lines)
    if "unzip -o -j $(PKG_BUILD_DIR)/easytier-$(PKG_VERSION).zip" in line
]
if len(matches) != 1:
    raise SystemExit(f"Expected one EasyTier extraction command, found {len(matches)}")
lines.insert(
    matches[0],
    '\t\techo "$(EASYTIER_AARCH64_SHA256)  '
    '$(PKG_BUILD_DIR)/easytier-$(PKG_VERSION).zip" | sha256sum -c -; ' + "\\",
)
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

cat > .config <<'EOF'
CONFIG_TARGET_armsr=y
CONFIG_TARGET_armsr_armv8=y
CONFIG_TARGET_armsr_armv8_DEVICE_generic=y
CONFIG_TARGET_KERNEL_PARTSIZE=64
CONFIG_TARGET_ROOTFS_PARTSIZE=960
CONFIG_TARGET_ROOTFS_TARGZ=y
CONFIG_CCACHE=y

CONFIG_PACKAGE_luci=y
CONFIG_PACKAGE_luci-ssl-openssl=y
CONFIG_LUCI_LANG_zh_Hans=y

CONFIG_PACKAGE_luci-app-passwall=y
CONFIG_PACKAGE_luci-app-openclash=y
CONFIG_PACKAGE_luci-app-amlogic=y

CONFIG_PACKAGE_kmod-tun=y
CONFIG_PACKAGE_easytier-noweb=y
CONFIG_PACKAGE_luci-app-easytier=y
CONFIG_PACKAGE_luci-i18n-easytier-zh-cn=y

CONFIG_PACKAGE_kmod-brcmfmac=y
CONFIG_BRCMFMAC_SDIO=y
# CONFIG_BRCMFMAC_USB is not set
CONFIG_PACKAGE_cypress-firmware-43455-sdio=y
CONFIG_PACKAGE_iw=y
CONFIG_PACKAGE_iwinfo=y
CONFIG_PACKAGE_wireless-regdb=y
CONFIG_PACKAGE_wpad-basic-mbedtls=y

CONFIG_PACKAGE_travelmate=y
CONFIG_PACKAGE_luci-app-travelmate=y
CONFIG_PACKAGE_relayd=y
CONFIG_PACKAGE_luci-proto-relay=y
CONFIG_PACKAGE_iperf3=y
CONFIG_PACKAGE_irqbalance=y
EOF

make defconfig

required_symbols=(
  PACKAGE_luci-app-amlogic
  PACKAGE_luci-app-easytier
  PACKAGE_luci-app-openclash
  PACKAGE_luci-app-passwall
)
for symbol in "${required_symbols[@]}"; do
  grep -qx "CONFIG_${symbol}=y" .config || {
    echo "Required build option CONFIG_${symbol}=y is unavailable" >&2
    exit 1
  }
done

rm -rf dl
ln -s "$CACHE_DIR/dl" dl
ccache --max-size "$CCACHE_MAXSIZE"
ccache --zero-stats

make download -j"$(nproc)" || make download -j1 V=s
find -L dl -type f -size -1024c -print -delete
make download -j"$(nproc)"
make -j"$(nproc)" || make -j1 V=s
ccache --show-stats

shopt -s nullglob
rootfs_files=(bin/targets/armsr/armv8/*-generic-rootfs.tar.gz)
if (( ${#rootfs_files[@]} == 0 )); then
  echo "No armsr/armv8 rootfs archive was produced" >&2
  exit 1
fi
rootfs_archive="${rootfs_files[0]}"
archive_has() {
  tar -tzf "$rootfs_archive" | grep -Eq "(^|/)${1}$"
}
required_rootfs_paths=(
  lib/netifd/wireless/mac80211.sh
  lib/firmware/brcm/brcmfmac43455-sdio.bin
  lib/firmware/brcm/brcmfmac43455-sdio.clm_blob
  usr/share/passwall/clash_subconverter.lua
)
for required_path in "${required_rootfs_paths[@]}"; do
  archive_has "$required_path" || {
    echo "Required N1 rootfs path is missing: ${required_path}" >&2
    exit 1
  }
done
cp "$rootfs_archive" "$ARTIFACT_DIR/"

cat > "$ARTIFACT_DIR/BUILD_INFO.txt" <<EOF
ImmortalWrt branch=${IMMORTALWRT_BRANCH}
ImmortalWrt=${immortalwrt_ref}
ImmortalWrt packages=${IMMORTALWRT_PACKAGES_REF}
ImmortalWrt LuCI=${IMMORTALWRT_LUCI_REF}
PassWall packages=${passwall_packages_ref}
PassWall LuCI=${passwall_ref}
OpenClash=${openclash_ref}
EasyTier OpenWrt=${easytier_openwrt_ref}
EasyTier version=${easytier_version}
EasyTier aarch64 SHA256=${easytier_sha256}
Amlogic Treasure Box=${amlogic_ref}
Builder image=${BUILDER_IMAGE:-unknown}
Builder digest=${BUILDER_IMAGE_DIGEST:-unknown}
EOF

ls -lh "$ARTIFACT_DIR"
