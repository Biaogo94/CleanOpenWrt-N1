#!/usr/bin/env bash
set -Eeuo pipefail

readonly WORKSPACE="${WORKSPACE:-/workspace}"
readonly SOURCE_DIR="${SOURCE_DIR:-${WORKSPACE}/.build/immortalwrt}"
readonly CACHE_DIR="${CACHE_DIR:-/cache}"
readonly ARTIFACT_DIR="${ARTIFACT_DIR:-${WORKSPACE}/artifacts/rootfs}"
readonly IMMORTALWRT_BRANCH="${IMMORTALWRT_BRANCH:-openwrt-25.12}"

export CCACHE_DIR="${CCACHE_DIR:-${CACHE_DIR}/ccache}"
export CCACHE_MAXSIZE="${CCACHE_MAXSIZE:-3G}"

rm -rf "$SOURCE_DIR" "$ARTIFACT_DIR"
mkdir -p "$(dirname "$SOURCE_DIR")" "$CACHE_DIR/dl" "$CCACHE_DIR" "$ARTIFACT_DIR"

git clone --depth 1 --branch "$IMMORTALWRT_BRANCH" --single-branch \
  https://github.com/immortalwrt/immortalwrt.git "$SOURCE_DIR"
readonly immortalwrt_ref="$(git -C "$SOURCE_DIR" rev-parse HEAD)"

cd "$SOURCE_DIR"
{
  echo "src-git passwall_packages https://github.com/Openwrt-Passwall/openwrt-passwall-packages.git"
  echo "src-git passwall_luci https://github.com/Openwrt-Passwall/openwrt-passwall.git"
  cat feeds.conf.default
} > feeds.conf
./scripts/feeds update -a
./scripts/feeds install -a

readonly passwall_packages_ref="$(git -C feeds/passwall_packages rev-parse HEAD)"
readonly passwall_ref="$(git -C feeds/passwall_luci rev-parse HEAD)"

git clone --depth 1 https://github.com/vernesong/OpenClash.git package/OpenClash
readonly openclash_ref="$(git -C package/OpenClash rev-parse HEAD)"
mv package/OpenClash/luci-app-openclash package/luci-app-openclash
rm -rf package/OpenClash

git clone --depth 1 https://github.com/EasyTier/luci-app-easytier.git package/easytier-openwrt
readonly easytier_openwrt_ref="$(git -C package/easytier-openwrt rev-parse HEAD)"
readonly easytier_version="$(sed -n 's/^EASYTIER_VERSION=//p' package/easytier-openwrt/version.mk)"
readonly easytier_asset="easytier-linux-aarch64-v${easytier_version}.zip"

git clone --depth 1 https://github.com/ophub/luci-app-amlogic.git package/luci-app-amlogic
readonly amlogic_ref="$(git -C package/luci-app-amlogic rev-parse HEAD)"

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
cp "${rootfs_files[@]}" "$ARTIFACT_DIR/"

cat > "$ARTIFACT_DIR/BUILD_INFO.txt" <<EOF
ImmortalWrt branch=${IMMORTALWRT_BRANCH}
ImmortalWrt=${immortalwrt_ref}
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
