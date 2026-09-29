import importlib.util
from pathlib import Path
import plistlib
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("catalog", Path(__file__).resolve().parents[1] / "scripts/catalog.py")
catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(catalog)


def listing(identifier="org.example.focus", slug="focus"):
    return {
        "schemaVersion": 1, "id": identifier, "slug": slug, "name": "Focus",
        "tagline": "A test fixture", "description": "Metadata validation fixture, not a distributed product.",
        "developer": {"name": "Example", "url": "https://example.org"},
        "categories": ["Productivity"], "price": {"amount": 0, "currency": "USD", "billing": "free"},
        "status": "preview", "version": "1.0.0", "requirements": ["macOS 14 or later"],
        "sourceUrl": "https://example.org/source", "supportUrl": "https://example.org/support"
    }


def artifact():
    return {"downloadURL": "https://example.org/focus-1.0.0.zip", "sha256": "a" * 64,
            "publisherTeamID": "ABCDE12345", "version": "1.0.0", "apiVersion": 1}


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def write(self, item, name=None):
        path = self.directory / (name or item["id"] + ".plist")
        path.write_bytes(plistlib.dumps(item))
        return path

    def test_deterministic_full_records_sort_by_id_without_source_version(self):
        self.write(listing("org.zulu.focus", "zulu"))
        self.write(listing("org.alpha.focus", "alpha"))
        first = catalog.generate(self.directory)
        second = catalog.generate(self.directory)
        self.assertEqual(first, second)
        result = plistlib.loads(first)
        self.assertEqual(result["schemaVersion"], 1)
        self.assertEqual([item["id"] for item in result["extensions"]], ["org.alpha.focus", "org.zulu.focus"])
        self.assertNotIn("schemaVersion", result["extensions"][0])
        self.assertEqual(result["extensions"][0]["developer"]["name"], "Example")

    def test_empty_catalog_is_valid_and_legacy_toml_is_untouched(self):
        legacy = self.directory / "old-pack.toml"
        legacy.write_text('id = "old.pack"\n')
        self.assertEqual(plistlib.loads(catalog.generate(self.directory))["extensions"], [])
        self.assertEqual(legacy.read_text(), 'id = "old.pack"\n')

    def test_canonical_artifact_and_matching_legacy_alias_normalize(self):
        item = listing()
        item["status"] = "available"
        item["artifact"] = artifact()
        item["artifact"]["url"] = item["artifact"]["downloadURL"]
        item["artifact"]["sha256"] = "A" * 64
        self.write(item)
        release = plistlib.loads(catalog.generate(self.directory))["extensions"][0]["artifact"]
        self.assertNotIn("url", release)
        self.assertEqual(release["downloadURL"], artifact()["downloadURL"])
        self.assertEqual(release["sha256"], "a" * 64)
        legacy = artifact()
        legacy["url"] = legacy.pop("downloadURL")
        self.assertEqual(catalog.validate_artifact(legacy, "1.0.0")["downloadURL"], artifact()["downloadURL"])

    def test_available_without_actual_artifact_is_rejected(self):
        item = listing()
        item["status"] = "available"
        self.write(item)
        with self.assertRaisesRegex(catalog.CatalogError, "reviewed artifact"):
            catalog.generate(self.directory)

    def test_invalid_release_identity_hash_version_and_url_are_rejected(self):
        invalid = [
            {"sha256": ""}, {"publisherTeamID": "development"}, {"version": "2.0.0"}, {"apiVersion": 2},
            {"downloadURL": "http://example.org/focus.zip"},
            {"downloadURL": "https://user:secret@example.org/focus.zip"},
            {"downloadURL": "https://example.org/checkout"},
            {"downloadURL": "https://example.org:abc/plugin.zip"},
            {"downloadURL": "https://[::1]:abc/plugin.zip"},
            {"downloadURL": "https://example.org:65536/plugin.zip"},
            {"downloadURL": "https://exa\\mple.org/plugin.zip"},
            {"url": "https://example.org/other.zip"}
        ]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(catalog.CatalogError):
                catalog.validate_artifact(artifact() | changes, "1.0.0")

    def test_filename_and_unique_slug_are_enforced(self):
        wrong = self.write(listing(), "wrong.plist")
        with self.assertRaisesRegex(catalog.CatalogError, "filename"):
            catalog.generate(self.directory)
        wrong.unlink()
        self.write(listing())
        self.write(listing("org.other.focus"))
        with self.assertRaisesRegex(catalog.CatalogError, "duplicate extension slug"):
            catalog.generate(self.directory)

    def test_reviewable_plists_reject_duplicate_keys_binary_and_entities(self):
        path = self.write(listing())
        data = path.read_bytes()
        path.write_bytes(data.replace(b"<key>id</key>", b"<key>id</key><string>org.forged.id</string><key>id</key>", 1))
        with self.assertRaisesRegex(catalog.CatalogError, "duplicate"):
            catalog.read_source(path)
        path.write_bytes(plistlib.dumps(listing(), fmt=plistlib.FMT_BINARY))
        with self.assertRaisesRegex(catalog.CatalogError, "reviewable XML"):
            catalog.read_source(path)
        path.write_bytes(b'<!DOCTYPE plist [<!ENTITY x "bad">]><plist><dict/></plist>')
        with self.assertRaisesRegex(catalog.CatalogError, "entity"):
            catalog.read_source(path)

    def test_links_and_nested_files_are_rejected(self):
        original = self.write(listing())
        link = self.directory / "org.example.link.plist"
        link.symlink_to(original)
        with self.assertRaisesRegex(catalog.CatalogError, "not a link"):
            catalog.read_source(link)
        link.unlink()
        nested = self.directory / "nested"
        nested.mkdir()
        original.rename(nested / original.name)
        with self.assertRaisesRegex(catalog.CatalogError, "directly"):
            catalog.generate(self.directory)

    def test_source_and_item_count_limits(self):
        path = self.directory / "oversized.plist"
        path.write_bytes(b" " * (catalog.MAX_SOURCE_BYTES + 1))
        with self.assertRaisesRegex(catalog.CatalogError, "64 KiB"):
            catalog.read_source(path)
        path.unlink()
        for number in range(catalog.MAX_ITEMS + 1):
            (self.directory / f"org.example.p{number}.plist").touch()
        with self.assertRaisesRegex(catalog.CatalogError, "500"):
            catalog.generate(self.directory)

    def test_aggregate_limit_is_checked_before_publication(self):
        for number in range(125):
            item = listing(f"org.example.p{number}", f"p{number}")
            item["description"] = "x" * 16_384
            self.write(item)
        with self.assertRaisesRegex(catalog.CatalogError, "2 MB"):
            catalog.generate(self.directory)

    def test_https_assets_and_legacy_assets_are_supported_without_unsafe_paths(self):
        for value in ["https://raw.githubusercontent.com/owner/repo/main/icon.png", "assets/extensions/focus.svg"]:
            self.assertTrue(catalog.asset(value))
        for value in ["http://example.org/icon.png", "assets/extensions/../secret.png", "assets/extensions//icon.png",
                      "assets/extensions/icon.png?secret=1", "https://user:pass@example.org/icon.png"]:
            self.assertFalse(catalog.asset(value))

    def test_type_price_and_schema_rules(self):
        invalid = [
            {"schemaVersion": True}, {"schemaVersion": 2}, {"id": "org.Example.Focus"}, {"name": ""},
            {"status": []}, {"price": {"amount": True, "currency": "USD", "billing": "free"}},
            {"price": {"amount": 1, "currency": "USD", "billing": "free"}},
            {"price": {"amount": float("nan"), "currency": "USD", "billing": "one-time"}},
            {"price": {"amount": 1, "currency": "USD", "billing": []}}
        ]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(catalog.CatalogError):
                catalog.validate_item(listing() | changes, "org.example.focus.plist")

    def test_optional_publisher_product_fields_survive_generation(self):
        item = listing()
        item.update({"websiteUrl": "https://example.org/focus", "purchaseUrl": "https://example.org/buy", "privacy": "Publisher-owned terms.",
                     "features": [{"title": "One", "description": "Two"}], "featured": True})
        self.write(item)
        result = plistlib.loads(catalog.generate(self.directory))["extensions"][0]
        self.assertEqual(result["websiteUrl"], item["websiteUrl"])
        self.assertEqual(result["purchaseUrl"], item["purchaseUrl"])
        self.assertEqual(result["features"], item["features"])
        self.assertTrue(result["featured"])

    def test_optional_product_website_requires_safe_https(self):
        for url in ["http://example.org/focus", "https://user:secret@example.org/focus",
                    "https://example.org:abc/focus", "https://exa\\mple.org/focus"]:
            with self.subTest(url=url), self.assertRaisesRegex(catalog.CatalogError, "websiteUrl"):
                catalog.validate_item(listing() | {"websiteUrl": url}, "org.example.focus.plist")


if __name__ == "__main__":
    unittest.main()
