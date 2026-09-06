#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly REPO_DIR
readonly LOCK_FILE="${REPO_DIR}/build-lock.env"
[[ -f "$LOCK_FILE" ]] || {
  echo "Missing build lock: ${LOCK_FILE}" >&2
  exit 1
}
# shellcheck disable=SC1090
. "$LOCK_FILE"
[[ "${LOCK_SCHEMA:-}" == "2" ]] || {
  echo "Unsupported build lock schema" >&2
  exit 1
}

BUILD_MODE="${BUILD_MODE:-full}"
[[ "$BUILD_MODE" == full || "$BUILD_MODE" == preflight ]] || {
  echo 'BUILD_MODE must be full or preflight' >&2
  exit 1
}
readonly INPUT_MANIFEST="${INPUT_MANIFEST:-${REPO_DIR}/build-inputs.json}"
# JSON is validated by the same production interface used in CI; never eval inputs.
input_environment="$(python3 "${REPO_DIR}/scripts/build_inputs.py" env --manifest "$INPUT_MANIFEST")"
while IFS='=' read -r name value; do
  export "$name=$value"
done <<<"$input_environment"
: "${EASYTIER_VERSION:?validated manifest must supply EasyTier version}"

readonly WORKSPACE="${WORKSPACE:-/workspace}"
readonly SOURCE_DIR="${SOURCE_DIR:-${WORKSPACE}/.build/immortalwrt}"
readonly CACHE_DIR="${CACHE_DIR:-/cache}"
readonly ARTIFACT_DIR="${ARTIFACT_DIR:-${WORKSPACE}/artifacts/rootfs}"
readonly DIAGNOSTIC_DIR="${DIAGNOSTIC_DIR:-${WORKSPACE}/artifacts/diagnostics}"
readonly IMMORTALWRT_BRANCH="$LOCK_IMMORTALWRT_BRANCH"
readonly IMMORTALWRT_REF
readonly IMMORTALWRT_PACKAGES_REF
readonly IMMORTALWRT_LUCI_REF
readonly PASSWALL_PACKAGES_REF
readonly PASSWALL_LUCI_REF
readonly OPENCLASH_REF
readonly EASYTIER_OPENWRT_REF
readonly AMLOGIC_REF
readonly SOURCE_SET_ID

export CCACHE_DIR="${CCACHE_DIR:-${CACHE_DIR}/ccache}"
export CCACHE_MAXSIZE="${CCACHE_MAXSIZE:-3G}"
export GO_MOD_CACHE_DIR="${CACHE_DIR}/go-mod"

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
mkdir -p "$(dirname "$SOURCE_DIR")" "$CACHE_DIR/dl" "$GO_MOD_CACHE_DIR" "$CCACHE_DIR" "$ARTIFACT_DIR" "$DIAGNOSTIC_DIR"
cp "$INPUT_MANIFEST" "$DIAGNOSTIC_DIR/build-inputs.json"
current_stage=prepare
stage_started=$SECONDS
stage() {
  printf '%s\t%s\n' "$current_stage" "$((SECONDS - stage_started))" >>"$DIAGNOSTIC_DIR/timings.tsv"
  current_stage="$1"
  stage_started=$SECONDS
  printf '%s\n' "$current_stage" >"$DIAGNOSTIC_DIR/current-stage.txt"
}
finish() {
  local code=$?
  trap - EXIT
  if [[ -f "$DIAGNOSTIC_DIR/current-stage.txt" ]]; then
    read -r current_stage <"$DIAGNOSTIC_DIR/current-stage.txt" || true
  fi
  printf '%s\t%s\n' "$current_stage" "$((SECONDS - stage_started))" >>"$DIAGNOSTIC_DIR/timings.tsv"
  printf 'stage=%s\nexit_code=%s\n' "$current_stage" "$code" >"$DIAGNOSTIC_DIR/result.txt"
  # Config originates from the repository, not from external user input.
  [[ ! -f "$SOURCE_DIR/.config" ]] || cp "$SOURCE_DIR/.config" "$DIAGNOSTIC_DIR/effective.config"
  ccache --show-stats >"$DIAGNOSTIC_DIR/ccache.txt" 2>/dev/null || true
  exit "$code"
}
trap finish EXIT

clone_at() {
  local repo="$1" branch="$2" ref="$3" destination="$4"
  echo "Cloning ${repo} branch ${branch} at ${ref}"
  # Replay does not depend on the branch still existing or resolving to its old tip.
  git init -q "$destination"
  git -C "$destination" remote add origin "$repo"
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

stage source
clone_at https://github.com/immortalwrt/immortalwrt.git "$IMMORTALWRT_BRANCH" "$IMMORTALWRT_REF" "$SOURCE_DIR"
assert_repo_ref "$SOURCE_DIR" "$IMMORTALWRT_REF"
readonly immortalwrt_ref="$IMMORTALWRT_REF"

cd "$SOURCE_DIR"
stage feeds
python3 "${REPO_DIR}/scripts/build_inputs.py" feeds --manifest "$INPUT_MANIFEST" >feeds.conf
# All feeds, including routing/telephony/video, are materialized at immutable SHAs.
timeout 1800 ./scripts/feeds update -a
python3 "${REPO_DIR}/scripts/build_inputs.py" verify-feeds --manifest "$INPUT_MANIFEST" --source-dir "$SOURCE_DIR"
cp feeds.conf "$DIAGNOSTIC_DIR/feeds.conf"

# Recreate indexes after verifying the pinned source. Never silently downgrade Go.
golang_version="$(bash "${REPO_DIR}/scripts/normalize-golang-feed.sh" \
  "${SOURCE_DIR}/feeds/packages/lang/golang")"
readonly golang_version
./scripts/feeds update -i -a

./scripts/feeds install -a

golang_host_makefile="${SOURCE_DIR}/package/feeds/packages/golang${golang_version}/Makefile"
[[ -f "$golang_host_makefile" ]] || {
  echo "Installed Go host package is missing: ${golang_host_makefile}" >&2
  exit 1
}
echo "Using Go host package golang${golang_version}"
printf '%s\n' "$golang_version" >"$DIAGNOSTIC_DIR/go-version.txt"
stage patches

# The rolling packages feed may enable Rust's CI LLVM download. Those
# artifacts are routinely garbage-collected, which makes reproducible builds
# fail with a 404. Build LLVM locally instead.
rust_makefile="${SOURCE_DIR}/feeds/packages/lang/rust/Makefile"
if [[ -f "$rust_makefile" ]]; then
  python3 "${REPO_DIR}/scripts/patch-rust.py" "$rust_makefile"
fi

assert_repo_ref feeds/passwall_packages "$PASSWALL_PACKAGES_REF"
assert_repo_ref feeds/passwall_luci "$PASSWALL_LUCI_REF"
readonly passwall_packages_ref="$PASSWALL_PACKAGES_REF"
readonly passwall_ref="$PASSWALL_LUCI_REF"

clone_at https://github.com/vernesong/OpenClash.git "$LOCK_OPENCLASH_BRANCH" "$OPENCLASH_REF" package/OpenClash
assert_repo_ref package/OpenClash "$OPENCLASH_REF"
readonly openclash_ref="$OPENCLASH_REF"
mv package/OpenClash/luci-app-openclash package/luci-app-openclash
rm -rf package/OpenClash

clone_at https://github.com/EasyTier/luci-app-easytier.git "$LOCK_EASYTIER_OPENWRT_BRANCH" "$EASYTIER_OPENWRT_REF" package/easytier-openwrt
assert_repo_ref package/easytier-openwrt "$EASYTIER_OPENWRT_REF"
readonly easytier_openwrt_ref="$EASYTIER_OPENWRT_REF"
easytier_version="$(sed -n 's/^EASYTIER_VERSION=//p' package/easytier-openwrt/version.mk)"
readonly easytier_version
[[ "$easytier_version" == "$EASYTIER_VERSION" ]] || {
  echo 'EasyTier manifest/source version mismatch' >&2
  exit 1
}

clone_at https://github.com/ophub/luci-app-amlogic.git "$LOCK_AMLOGIC_BRANCH" "$AMLOGIC_REF" package/luci-app-amlogic
assert_repo_ref package/luci-app-amlogic "$AMLOGIC_REF"
readonly amlogic_ref="$AMLOGIC_REF"

readonly easytier_sha256="$EASYTIER_AARCH64_SHA256"

python3 "${REPO_DIR}/scripts/patch-easytier.py" package/easytier-openwrt/easytier-noweb/Makefile

stage config
cat >.config <<'EOF'
CONFIG_TARGET_armsr=y
CONFIG_TARGET_armsr_armv8=y
CONFIG_TARGET_armsr_armv8_DEVICE_generic=y
CONFIG_TARGET_KERNEL_PARTSIZE=64
CONFIG_TARGET_ROOTFS_PARTSIZE=960
CONFIG_TARGET_ROOTFS_TARGZ=y
CONFIG_CCACHE=y
# Explicitly require the wireless integration package in the rootfs.
CONFIG_PACKAGE_wifi-scripts=y

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

stage preflight
if [[ "$BUILD_MODE" == full ]]; then
  rm -rf dl
  ln -s "$CACHE_DIR/dl" dl
  ccache --max-size "$CCACHE_MAXSIZE"
  ccache --zero-stats
fi
bash "${REPO_DIR}/scripts/compile-rootfs.sh" "$SOURCE_DIR" "$BUILD_MODE" "$DIAGNOSTIC_DIR"
if [[ "$BUILD_MODE" == preflight ]]; then
  echo 'Preflight complete; compilation and publication skipped.'
  exit 0
fi
ccache --show-stats
stage validate

shopt -s nullglob
rootfs_files=(bin/targets/armsr/armv8/*-generic-rootfs.tar.gz)
if ((${#rootfs_files[@]} == 0)); then
  echo "No armsr/armv8 rootfs archive was produced" >&2
  exit 1
fi
rootfs_archive="${rootfs_files[0]}"
((${#rootfs_files[@]} == 1)) || {
  echo 'Ambiguous rootfs output' >&2
  exit 1
}
python3 "${REPO_DIR}/scripts/validate-rootfs.py" "$rootfs_archive"
stage export
cp "$rootfs_archive" "$ARTIFACT_DIR/"
cp "$INPUT_MANIFEST" "$ARTIFACT_DIR/build-inputs.json"

cat >"$ARTIFACT_DIR/BUILD_INFO.txt" <<EOF
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
Build lock SHA256=$(sha256sum "$LOCK_FILE" | awk '{print $1}')
Source set=${SOURCE_SET_ID}
Go host version=${golang_version}
Kernel series=${LOCK_KERNEL_SERIES}
Builder image=${BUILDER_IMAGE:-unknown}
Builder digest=${BUILDER_IMAGE_DIGEST:-unknown}
EOF

ls -lh "$ARTIFACT_DIR"
