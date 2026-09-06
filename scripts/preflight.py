#!/usr/bin/env python3
"""Check the effective OpenWrt configuration and installed Go dependency seam."""

import argparse
import re
import sys
from pathlib import Path

REQUIRED = (
    "PACKAGE_wifi-scripts",
    "PACKAGE_luci-app-amlogic",
    "PACKAGE_luci-app-easytier",
    "PACKAGE_easytier-noweb",
    "PACKAGE_luci-app-openclash",
    "PACKAGE_luci-app-passwall",
    "PACKAGE_kmod-brcmfmac",
    "BRCMFMAC_SDIO",
    "PACKAGE_cypress-firmware-43455-sdio",
    "PACKAGE_iw",
    "PACKAGE_iwinfo",
    "PACKAGE_wireless-regdb",
    "PACKAGE_wpad-basic-mbedtls",
    "PACKAGE_travelmate",
    "PACKAGE_luci-app-travelmate",
    "PACKAGE_relayd",
    "PACKAGE_luci-proto-relay",
)


def go_version(source):
    base = source / "feeds/packages/lang/golang"
    values = (base / "golang-values.mk").read_text()
    versions = re.findall(
        r"^GO_DEFAULT_VERSION\s*:?=\s*([0-9]+\.[0-9]+)\s*$", values, re.MULTILINE
    )
    if len(versions) != 1:
        raise ValueError("Invalid Go default metadata")
    version = versions[0]
    target = base / f"golang{version}/Makefile"
    if not target.is_file():
        raise ValueError(
            f"Go {version} host source missing; refusing unverified version fallback"
        )
    installed = source / f"package/feeds/packages/golang{version}/Makefile"
    if not installed.is_file() or installed.resolve() != target.resolve():
        raise ValueError(
            f"Go {version} installed target is missing/stale; regenerate feeds indexes and install"
        )
    dummy = source / "package/feeds/packages/golang/Makefile"
    text = dummy.read_text()
    # Generic host dependency may use PKG_VERSION, supplied by golang-values.mk.
    if not re.search(
        r"^HOST_BUILD_DEPENDS\s*:?=\s*golang(?:\$\(PKG_VERSION\)|"
        + re.escape(version)
        + r")/host\s*$",
        text,
        re.MULTILINE,
    ):
        raise ValueError("Generic Go host dependency does not match selected target")
    if "$(PKG_VERSION)" in text and not re.search(
        r"^PKG_VERSION\s*:?=\s*\$\(GO_DEFAULT_VERSION\)\s*$", text, re.MULTILINE
    ):
        raise ValueError(
            "Generic Go package no longer derives version from GO_DEFAULT_VERSION"
        )
    return version


def check(source):
    config = set((source / ".config").read_text().splitlines())
    missing = [symbol for symbol in REQUIRED if f"CONFIG_{symbol}=y" not in config]
    if missing:
        raise ValueError("Required effective config missing: " + ", ".join(missing))
    return go_version(source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    try:
        print("Preflight passed; Go host=" + check(args.source))
    except (ValueError, OSError) as error:
        print("Preflight failed: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
