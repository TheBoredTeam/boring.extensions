#!/usr/bin/env python3
"""Validate individual native-extension plists and build the public aggregate."""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import plistlib
import re
import sys
import unicodedata
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

MAX_SOURCE_BYTES = 65_536
MAX_ITEMS = 500
MAX_CATALOG_BYTES = 2_000_000
ROOT = Path(__file__).resolve().parents[1]
ID_PATTERN = re.compile(r"[a-z][a-z0-9]*(\.[a-z0-9-]+)+\Z")
SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class CatalogError(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise CatalogError(reason)


def text(value: object, limit: int) -> bool:
    return (isinstance(value, str) and bool(value.strip())
            and len(value.encode("utf-8")) <= limit
            and not any(unicodedata.category(char) in {"Cc", "Cf"}
                        and char not in "\n\r\u0085" for char in value))


def https(value: object) -> bool:
    if not isinstance(value, str) or len(value.encode("utf-8")) > 4_096:
        return False
    if "#" in value or "\\" in value or any(ord(char) <= 32 for char in value):
        return False
    try:
        parsed = urlsplit(value)
        # urlsplit leaves malformed/non-numeric ports lazy until this property
        # is read. Match Foundation's URL decoding before publishing records.
        _ = parsed.port
        return (parsed.scheme.lower() == "https" and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None)
    except ValueError:
        return False


def asset(value: object) -> bool:
    if https(value):
        return True
    return (isinstance(value, str) and value.startswith("assets/extensions/")
            and not any(char in value for char in "\\%?#")
            and not any(part in {"", ".", ".."} for part in value.split("/"))
            and value.rsplit(".", 1)[-1].lower() in {"svg", "png", "webp", "jpg", "jpeg"})


def validate_artifact(value: object, version: str) -> dict:
    require(isinstance(value, dict), "artifact must be a dictionary")
    canonical = value.get("downloadURL")
    legacy = value.get("url")
    require(canonical is None or legacy is None or canonical == legacy,
            "artifact.downloadURL and legacy artifact.url disagree")
    url = canonical if canonical is not None else legacy
    require(https(url) and urlsplit(url).path.lower().endswith(".zip"),
            "artifact.downloadURL must be a public HTTPS ZIP URL without credentials or fragments")
    require(isinstance(value.get("sha256"), str)
            and re.fullmatch(r"[A-Fa-f0-9]{64}", value["sha256"]) is not None,
            "artifact.sha256 must contain the exact ZIP's 64 hexadecimal digest characters")
    require(isinstance(value.get("publisherTeamID"), str)
            and re.fullmatch(r"[A-Z0-9]{10}", value["publisherTeamID"]) is not None,
            "artifact.publisherTeamID must be the publisher's 10-character signing Team ID")
    release_version = value.get("version")
    require(text(release_version, 64) and release_version == release_version.strip()
            and not any(unicodedata.category(char) in {"Cc", "Cf"} for char in release_version)
            and release_version == version, "artifact.version must exactly match the listing version")
    require(type(value.get("apiVersion")) is int and value["apiVersion"] == 1,
            "artifact.apiVersion must be 1")
    normalized = dict(value)
    normalized.pop("url", None)
    normalized["downloadURL"] = url
    normalized["sha256"] = value["sha256"].lower()
    return normalized


def validate_item(item: object, filename: str) -> dict:
    require(isinstance(item, dict), "source plist root must be a dictionary")
    require(type(item.get("schemaVersion")) is int and item["schemaVersion"] == 1,
            "schemaVersion must be 1")
    identifier = item.get("id")
    require(isinstance(identifier, str) and len(identifier.encode("utf-8")) <= 128
            and ID_PATTERN.fullmatch(identifier) is not None, "id must be a lowercase reverse-domain manifest ID")
    require(filename == f"{identifier}.plist", "filename must exactly match <manifest-id>.plist")
    slug = item.get("slug")
    require(isinstance(slug, str) and len(slug.encode("utf-8")) <= 128
            and SLUG_PATTERN.fullmatch(slug) is not None, "slug must use lowercase letters, digits, and single hyphens")
    for key, limit in [("name", 128), ("tagline", 512), ("description", 16_384), ("version", 64)]:
        require(text(item.get(key), limit), f"{key} is missing, empty, too long, or contains control characters")
    developer = item.get("developer")
    require(isinstance(developer, dict) and text(developer.get("name"), 128)
            and https(developer.get("url")), "developer requires a name and public HTTPS URL")
    for key, maximum, limit in [("categories", 16, 64), ("requirements", 32, 1_024)]:
        values = item.get(key)
        require(isinstance(values, list) and len(values) <= maximum
                and all(text(value, limit) for value in values), f"{key} must be a bounded array of text")
    price = item.get("price")
    require(isinstance(price, dict), "price must be a dictionary")
    amount = price.get("amount")
    require(type(amount) in {int, float} and 0 <= amount <= 1_000_000 and math.isfinite(amount),
            "price.amount must be a finite nonnegative amount")
    require(isinstance(price.get("currency"), str) and re.fullmatch(r"[A-Z]{3}", price["currency"]) is not None,
            "price.currency must be three uppercase letters")
    require(isinstance(price.get("billing"), str) and price["billing"] in {"free", "one-time", "monthly", "yearly"}
            and ((amount == 0) == (price["billing"] == "free")), "free billing must have zero price, and paid billing a positive price")
    require(isinstance(item.get("status"), str) and item["status"] in {"coming-soon", "preview", "available"}, "unknown listing status")
    if "statusNote" in item:
        require(text(item["statusNote"], 4_096), "invalid statusNote")
    for key in ["websiteUrl", "sourceUrl", "supportUrl", "purchaseUrl", "downloadUrl"]:
        if key in item:
            require(https(item[key]), f"{key} must be a public HTTPS URL")
    for key in ["icon", "artwork"]:
        if key in item:
            require(asset(item[key]), f"{key} must be an HTTPS asset or valid legacy website asset path")
    normalized = dict(item)
    normalized.pop("schemaVersion")
    if "artifact" in item:
        normalized["artifact"] = validate_artifact(item["artifact"], item["version"])
    require(item["status"] != "available" or "artifact" in normalized,
            "available listings require reviewed artifact metadata; keep unreleased products coming-soon/preview")
    return normalized


def read_source(path: Path) -> dict:
    require(not path.is_symlink() and path.is_file(), "source must be a regular file, not a link")
    with path.open("rb") as source:
        data = source.read(MAX_SOURCE_BYTES + 1)
    require(len(data) <= MAX_SOURCE_BYTES, "source plist exceeds 64 KiB")
    # XML is intentionally required for human-reviewed sources. Detect duplicate
    # keys before plistlib would silently choose the final value in a dictionary.
    require(not data.startswith(b"bplist"), "source plists must use reviewable XML format")
    require(b"<!ENTITY" not in data, "XML entity declarations are not allowed")
    try:
        xml = ET.fromstring(data)
        for dictionary in xml.iter("dict"):
            children = list(dictionary)
            require(len(children) % 2 == 0, "malformed plist dictionary")
            keys = children[::2]
            require(all(key.tag == "key" for key in keys), "malformed plist dictionary key")
            names = [key.text or "" for key in keys]
            require(len(names) == len(set(names)), "duplicate plist dictionary key")
        item = plistlib.loads(data)
    except (ET.ParseError, plistlib.InvalidFileException, ValueError, TypeError, OverflowError) as error:
        raise CatalogError(f"invalid source plist: {error}") from error
    return validate_item(item, path.name)


def generate(directory: Path) -> bytes:
    require(directory.is_dir(), "extensions source directory does not exist")
    files = sorted(directory.rglob("*.plist"))
    require(len(files) <= MAX_ITEMS, "catalog exceeds 500 extension records")
    items = []
    for path in files:
        try:
            require(path.parent == directory, "place source records directly in extensions/")
            items.append(read_source(path))
        except CatalogError as error:
            raise CatalogError(f"{path.name}: {error}") from error
    require(len({item["id"] for item in items}) == len(items), "duplicate extension id")
    require(len({item["slug"] for item in items}) == len(items), "duplicate extension slug")
    items.sort(key=lambda item: item["id"])
    aggregate = plistlib.dumps({"schemaVersion": 1, "extensions": items}, fmt=plistlib.FMT_XML, sort_keys=True)
    require(len(aggregate) <= MAX_CATALOG_BYTES, "aggregate catalog exceeds 2 MB")
    return aggregate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "extensions")
    parser.add_argument("--output", type=Path, default=ROOT / "catalog.plist")
    parser.add_argument("--check", action="store_true", help="Validate that the existing aggregate is current without changing files.")
    args = parser.parse_args()
    try:
        data = generate(args.source)
        if args.check:
            require(args.output.is_file() and args.output.read_bytes() == data,
                    "generated aggregate is stale; run python3 scripts/catalog.py")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(data)
        count = len(plistlib.loads(data)["extensions"])
        print(f"Validated {count} native extension records; deterministic catalog is {len(data)} bytes.")
        return 0
    except (CatalogError, OSError) as error:
        print(f"Catalog validation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
