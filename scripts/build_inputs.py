#!/usr/bin/env python3
"""Resolve immutable build inputs, or validate/replay them without remote resolution."""

import argparse
import hashlib
import http.client
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SHA = r"[0-9a-f]{40}"
DIGEST = r"[0-9a-f]{64}"
SOURCES = {
    "IMMORTALWRT": ("immortalwrt/immortalwrt", "IMMORTALWRT"),
    "IMMORTALWRT_PACKAGES": ("immortalwrt/packages", "IMMORTALWRT_PACKAGES"),
    "IMMORTALWRT_LUCI": ("immortalwrt/luci", "IMMORTALWRT_LUCI"),
    "PASSWALL_PACKAGES": (
        "Openwrt-Passwall/openwrt-passwall-packages",
        "PASSWALL_PACKAGES",
    ),
    "PASSWALL_LUCI": ("Openwrt-Passwall/openwrt-passwall", "PASSWALL_LUCI"),
    "OPENCLASH": ("vernesong/OpenClash", "OPENCLASH"),
    "EASYTIER_OPENWRT": ("EasyTier/luci-app-easytier", "EASYTIER_OPENWRT"),
    "AMLOGIC": ("ophub/luci-app-amlogic", "AMLOGIC"),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def matches(pattern, value):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


def command(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True, timeout=120).strip()


def lock_values():
    values = {}
    for line in (ROOT / "build-lock.env").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        require(
            sep
            and matches(r"LOCK_[A-Z_]+", key)
            and matches(r"[A-Za-z0-9_./:-]+", value),
            "Invalid lock field",
        )
        require(key not in values, "Duplicate lock field")
        values[key] = value
    expected = {"LOCK_SCHEMA", "LOCK_BUILDER_IMAGE", "LOCK_KERNEL_SERIES"} | {
        "LOCK_" + key + "_BRANCH" for _, key in SOURCES.values()
    }
    require(
        set(values) == expected and values["LOCK_SCHEMA"] == "2",
        "Unsupported/incomplete build lock",
    )
    return values


def identity():
    files = [ROOT / "Dockerfile", ROOT / "build-lock.env", ROOT / "rootfs-lock.env"]
    for directory in ("scripts", ".github/workflows", "n1-overlay"):
        files.extend(
            p
            for p in (ROOT / directory).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        )
    return checksum(
        canonical(
            {
                p.relative_to(ROOT).as_posix(): checksum(p.read_bytes())
                for p in sorted(files)
            }
        )
    )


def remote(url):
    # Only fixed public GitHub endpoints are used by the resolver; no credentials logged.
    require(
        matches(
            r"https://(?:raw\.githubusercontent\.com|api\.github\.com)/[A-Za-z0-9_./-]+",
            url,
        ),
        "Unsupported resolver endpoint",
    )
    parsed = urlsplit(url)
    connection = http.client.HTTPSConnection(parsed.netloc, timeout=60)
    try:
        connection.request(
            "GET",
            parsed.path,
            headers={
                "User-Agent": "CleanOpenWrt-N1",
                "Accept": "application/vnd.github+json",
            },
        )
        response = connection.getresponse()
        require(
            response.status == 200, "Resolver endpoint unavailable (redirects refused)"
        )
        payload = response.read(8 * 1024 * 1024 + 1)
        require(len(payload) <= 8 * 1024 * 1024, "Resolver response too large")
        return payload.decode()
    finally:
        connection.close()


def git_url(url):
    require(
        matches(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", url),
        "Unsupported source URL",
    )
    return url


def resolve_ref(url, branch):
    git_url(url)
    require(matches(r"[A-Za-z0-9_./-]+", branch), "Invalid branch")
    rows = command("git", "ls-remote", url, "refs/heads/" + branch).splitlines()
    require(len(rows) == 1, "Cannot resolve branch")
    ref = rows[0].split()[0]
    require(matches(SHA, ref), "Invalid upstream SHA")
    return ref


def parse_feeds(text, sources, frozen=None):
    feeds = []
    overrides = {"packages": "IMMORTALWRT_PACKAGES", "luci": "IMMORTALWRT_LUCI"}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        require(
            len(parts) == 3 and parts[0] == "src-git",
            "Unsupported feed definition; resolve explicitly before building",
        )
        _, name, spec = parts
        require(matches(r"[a-zA-Z0-9_]+", name), "Invalid feed name")
        if "^" in spec:
            url, ref = spec.split("^", 1)
            require(matches(SHA, ref), "Feed revision must be a complete SHA")
        else:
            url, sep, branch = spec.partition(";")
            if name in overrides:
                ref = sources[overrides[name]]["ref"]
            elif frozen is not None:
                require(name in frozen, "Manifest omitted an upstream feed: " + name)
                ref = frozen[name]["ref"]
            else:
                ref = resolve_ref(url, branch if sep else "master")
        git_url(url)
        if name in overrides:
            require(
                url == sources[overrides[name]]["url"], "Overridden feed URL mismatch"
            )
            ref = sources[overrides[name]]["ref"]
        feeds.append({"name": name, "url": url, "ref": ref})
    return [
        {"name": name, **sources[key]}
        for name, key in (
            ("passwall_packages", "PASSWALL_PACKAGES"),
            ("passwall_luci", "PASSWALL_LUCI"),
        )
    ] + feeds


def make_manifest(builder):
    lock = lock_values()
    sources = {}
    for name, (repo, key) in SOURCES.items():
        url = f"https://github.com/{repo}.git"
        sources[name] = {
            "url": url,
            "ref": resolve_ref(url, lock[f"LOCK_{key}_BRANCH"]),
        }
    main_ref = sources["IMMORTALWRT"]["ref"]
    feeds = parse_feeds(
        remote(
            f"https://raw.githubusercontent.com/immortalwrt/immortalwrt/{main_ref}/feeds.conf.default"
        ),
        sources,
    )
    version_text = remote(
        f"https://raw.githubusercontent.com/EasyTier/luci-app-easytier/{sources['EASYTIER_OPENWRT']['ref']}/version.mk"
    )
    versions = re.findall(
        r"^EASYTIER_VERSION=([0-9]+\.[0-9]+\.[0-9]+)\s*$", version_text, re.MULTILINE
    )
    require(len(versions) == 1, "Cannot resolve EasyTier version")
    version = versions[0]
    asset_name = f"easytier-linux-aarch64-v{version}.zip"
    try:
        release = json.loads(
            remote(
                f"https://api.github.com/repos/EasyTier/EasyTier/releases/tags/v{version}"
            )
        )
    except (ValueError, OSError) as error:
        raise ValueError("Cannot read EasyTier release metadata") from error
    assets = [a for a in release["assets"] if a["name"] == asset_name]
    require(len(assets) == 1, "Ambiguous/missing EasyTier asset")
    digest = assets[0].get("digest", "")
    require(matches("sha256:" + DIGEST, digest), "Missing EasyTier digest")
    data = {
        "schema": 1,
        "project_ref": command("git", "rev-parse", "HEAD"),
        "input_hash": identity(),
        "builder": builder,
        "sources": sources,
        "feeds": feeds,
        "easytier": {"version": version, "sha256": digest[7:]},
    }
    data["source_set_id"] = checksum(canonical(data))
    return data


def validate(data, check_identity=True):
    require(
        isinstance(data, dict)
        and set(data)
        == {
            "schema",
            "project_ref",
            "input_hash",
            "builder",
            "sources",
            "feeds",
            "easytier",
            "source_set_id",
        },
        "Invalid manifest fields",
    )
    require(
        isinstance(data["schema"], int)
        and not isinstance(data["schema"], bool)
        and data["schema"] == 1
        and matches(SHA, data["project_ref"])
        and matches(DIGEST, data["input_hash"]),
        "Invalid manifest schema/identity",
    )
    require(
        matches(
            re.escape(lock_values()["LOCK_BUILDER_IMAGE"]) + "@sha256:" + DIGEST,
            data["builder"],
        ),
        "Invalid builder digest/repository",
    )
    require(
        isinstance(data["sources"], dict) and set(data["sources"]) == set(SOURCES),
        "Incomplete sources",
    )
    for key, item in data["sources"].items():
        require(
            isinstance(item, dict) and set(item) == {"url", "ref"},
            "Invalid source fields",
        )
        require(
            item["url"] == f"https://github.com/{SOURCES[key][0]}.git"
            and matches(SHA, item["ref"]),
            "Invalid source",
        )
    require(
        isinstance(data["feeds"], list) and 4 <= len(data["feeds"]) <= 64,
        "Invalid feeds",
    )
    names = set()
    for feed in data["feeds"]:
        require(
            isinstance(feed, dict) and set(feed) == {"name", "url", "ref"},
            "Invalid feed fields",
        )
        require(
            matches(r"[A-Za-z0-9_]+", feed["name"])
            and feed["name"] not in names
            and matches(SHA, feed["ref"]),
            "Invalid/duplicate feed",
        )
        git_url(feed["url"])
        names.add(feed["name"])
    for name, key in (
        ("packages", "IMMORTALWRT_PACKAGES"),
        ("luci", "IMMORTALWRT_LUCI"),
        ("passwall_packages", "PASSWALL_PACKAGES"),
        ("passwall_luci", "PASSWALL_LUCI"),
    ):
        require(
            {"name": name, **data["sources"][key]} in data["feeds"],
            "Required feed mismatch",
        )
    easytier = data["easytier"]
    require(
        isinstance(easytier, dict)
        and set(easytier) == {"version", "sha256"}
        and matches(r"[0-9]+\.[0-9]+\.[0-9]+", easytier["version"])
        and matches(DIGEST, easytier["sha256"]),
        "Invalid EasyTier input",
    )
    require(
        matches(DIGEST, data["source_set_id"])
        and data["source_set_id"]
        == checksum(canonical({k: v for k, v in data.items() if k != "source_set_id"})),
        "Manifest content digest mismatch",
    )
    if check_identity:
        require(
            data["project_ref"] == command("git", "rev-parse", "HEAD")
            and data["input_hash"] == identity(),
            "Replay requires the original project revision AND unchanged build inputs; no automatic checkout/fallback",
        )
    return data


def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result

    require(Path(path).stat().st_size <= 1024 * 1024, "Manifest too large")
    try:
        data = json.loads(Path(path).read_text(), object_pairs_hook=pairs)
    except (ValueError, OSError) as error:
        raise ValueError("Cannot read manifest JSON") from error
    return validate(data)


def emit_environment(data):
    values = {key + "_REF": item["ref"] for key, item in data["sources"].items()}
    values.update(
        SOURCE_SET_ID=data["source_set_id"],
        BUILDER_IMAGE_DIGEST=data["builder"],
        EASYTIER_AARCH64_SHA256=data["easytier"]["sha256"],
        EASYTIER_VERSION=data["easytier"]["version"],
    )
    print("\n".join(f"{key}={value}" for key, value in values.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation",
        choices=("resolve", "validate", "env", "feeds", "verify-feeds", "lock"),
    )
    parser.add_argument("--manifest", default="build-inputs.json")
    parser.add_argument("--builder")
    parser.add_argument("--source-dir")
    args = parser.parse_args()
    if args.operation == "lock":
        lock_values()
        return
    if args.operation == "resolve":
        data = validate(make_manifest(args.builder))
        Path(args.manifest).write_text(json.dumps(data, indent=2) + "\n")
        return
    data = load(args.manifest)
    if args.operation == "env":
        emit_environment(data)
    elif args.operation == "feeds":
        print(
            "\n".join(
                f"src-git {f['name']} {f['url']}^{f['ref']}" for f in data["feeds"]
            )
        )
    elif args.operation == "verify-feeds":
        require(args.source_dir, "Missing source directory")
        source = Path(args.source_dir)
        frozen = {feed["name"]: feed for feed in data["feeds"]}
        expected = parse_feeds(
            (source / "feeds.conf.default").read_text(), data["sources"], frozen
        )
        require(
            expected == data["feeds"],
            "Manifest feed list differs from pinned upstream definitions",
        )
        actual_names = {
            p.name
            for p in (source / "feeds").iterdir()
            if p.is_dir() and (p / ".git").exists()
        }
        require(
            actual_names == {f["name"] for f in data["feeds"]},
            "Unfrozen/missing feed checkout",
        )
        for feed in data["feeds"]:
            ref = command(
                "git", "-C", str(source / "feeds" / feed["name"]), "rev-parse", "HEAD"
            )
            require(ref == feed["ref"], "Feed checkout mismatch: " + feed["name"])


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        # Messages are fixed validation descriptions, not remote contents.
        print("Build input validation failed: " + str(error), file=sys.stderr)
        sys.exit(1)
    except (
        OSError,
        subprocess.SubprocessError,
        KeyError,
        TypeError,
        http.client.HTTPException,
    ):
        print(
            "Build input operation failed; check locked refs and network availability.",
            file=sys.stderr,
        )
        sys.exit(1)
