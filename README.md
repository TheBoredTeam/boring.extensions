# Boring Notch extensions

The reviewed native Extension Store catalog for Boring Notch. Each independently
distributed extension has one XML property list under `extensions/`. Maintainers
review those records; CI generates the complete `catalog.plist` consumed by the
app. Adding or updating an approved extension does **not** require an app release.

The public endpoint is:

```text
https://raw.githubusercontent.com/TheBoredTeam/boring.extensions/main/catalog.plist
```

This repository contains listing data, catalog tooling, and an API reference,
not extension implementations or customer purchases. Publishers build, sign,
notarize, and distribute their own `.bnplugin` ZIPs. They own pricing, checkout,
accounts, licenses, refunds, and access enforcement. Boring Notch supplies
discovery, delivery, installation, and the native runtime; paid and free bundles
use the same installation contract.

## Build an extension with a coding assistant

Start with [LLM.txt](LLM.txt), which includes a ready-to-customize prompt and the
reading order. [AGENTS.md](AGENTS.md) covers implementation conventions, native
view ownership, live activities, regular/compact tabs, lifecycle cleanup, testing,
packaging, and Store submission. The [API reference](docs/README.md) includes the
exact C header and its provenance. These activities/tabs APIs are a **developer
preview**; confirm a compatible host build before promising that an extension
works in a released app.

## Register or update an extension

1. Fork this repository and add `extensions/<manifest-id>.plist`. Start from an
   existing record and keep its XML property-list format. The filename and `id`
   must exactly match the bundle's lowercase manifest identifier.
2. Fill in truthful product, publisher, compatibility, and support information.
   A preview or coming-soon listing does not need a downloadable artifact.
3. For an available release, include the **actual final ZIP** download URL,
   SHA-256 digest, publisher signing Team ID, exact version, and native API
   version. Use immutable public HTTPS release URLs. A checkout URL belongs in
   `purchaseUrl`, never `artifact.downloadURL`.
4. Run `python3 -m unittest discover -s tests -v` and
   `python3 scripts/catalog.py --output /tmp/boring-extension-catalog.plist`.
5. Open a pull request. Include the publisher's public identity, release/source
   link, compatibility and signing/notarization evidence, and what changed.
   Maintainers review listings and every release update before merging.

Change source records, not `catalog.plist`. The pull-request workflow validates
the sources and uploads a generated review artifact. After a merge to `main`,
the workflow regenerates and commits the aggregate. The repository must allow
the catalog workflow's `contents: write` token to update `catalog.plist` on
`main`. No developer GitHub token, API key, or app rebuild is needed by users.

The app fetches one aggregate, not one request per extension. It validates every
listing before display, keeps a revalidated last-good cache, refreshes when the
Store's one-hour freshness window expires, and supports immediate manual
Refresh. Network or malformed-data failures preserve previously verified
listings and show a refresh error. Registry changes become visible on refresh;
GitHub's normal CDN propagation still applies.

## Source schema

Each source is a flat dictionary with `schemaVersion = 1` plus the fields below.
The aggregate has `{schemaVersion: 1, extensions: [full listing dictionaries]}`;
per-source `schemaVersion` keys are omitted from those listing dictionaries.
Records are sorted by manifest ID, and output bytes are deterministic.

| Field | Meaning |
| --- | --- |
| `id`, `slug`, `name` | Exact bundle manifest ID, unique stable lowercase URL slug, and display name. |
| `tagline`, `description` | Short and full plain-text product descriptions. |
| `developer` | Dictionary with `name` and public HTTPS `url`. |
| `categories`, `requirements` | Arrays of category names and concrete compatibility requirements. |
| `price` | Dictionary with numeric `amount`, three-letter uppercase `currency`, and `billing`: `free`, `one-time`, `monthly`, or `yearly`. Zero price must use `free`. |
| `status` | `coming-soon`, `preview`, or `available`. Only available records with valid artifacts offer installation. |
| `version` | Exact bundle version for available releases; an honest preview label for unreleased products. |
| `statusNote` | Optional explanation of current release readiness. |
| `websiteUrl` | Optional public HTTPS product page for “View on website”. Without it the app uses `developer.url`; it never invents a website page from the slug. |
| `sourceUrl`, `supportUrl`, `purchaseUrl` | Optional public HTTPS destinations. Payments remain with the developer. |
| `icon`, `artwork` | Optional public HTTPS images. Existing `assets/extensions/...` website paths remain supported. |
| `artifact` | Required for `available`; see the release record below. |

Additional product information such as `features`, `privacy`, `installSteps`,
`previews`, or `artworkAlt` is preserved for compatible consumers. Unknown fields
do not execute code. Do not include signing secrets, private download tokens,
customer information, license codes, install counts, or unsupported claims.

An artifact is an XML `<dict>` with these keys:

| Key | Required value |
| --- | --- |
| `downloadURL` | Direct public HTTPS URL of the final `.zip`. |
| `sha256` | The ZIP's 64-character hexadecimal SHA-256 digest. |
| `publisherTeamID` | The publisher's ten-character Apple signing Team ID. |
| `version` | Exactly the listing and packaged manifest version. |
| `apiVersion` | Integer `1`. |

The generator also reads the legacy artifact key `url`, normalizes it to
`downloadURL`, and rejects disagreeing aliases. The canonical plist format uses
`downloadURL`. Compute the digest **after** signing, notarization, and packaging:

```sh
shasum -a 256 /path/to/Extension-1.0.0.zip
```

Catalog validation proves structure and identity consistency. A maintainer must
review the actual release; the app separately verifies the ZIP hash, archive
structure, code signatures/notarization, manifest ID, version, and signing Team
ID before installation. Merely setting `status` to `available` does not establish
that a publisher has shipped or a user has paid.

## Bounds and local checks

Source files must be reviewable XML, at most 64 KiB each, with no duplicate
dictionary keys, symbolic links, or XML entity declarations. At most 500 listings
are supported; the full generated catalog must fit within 2 MB. IDs and slugs
must be unique. The generator rejects unsafe URLs, malformed prices, incompatible
artifact versions, and available records without complete release metadata.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/catalog.py              # Generate catalog.plist locally.
python3 scripts/catalog.py --check      # Verify an existing aggregate is current.
```

The initial records preserve the existing Lock Screen coming-soon listing and
Now Playing developer preview. Neither claims an approved consumer ZIP release.
Lock Screen remains one product: Music, Focus, and Glance share its publisher's
single $1 permanent unlock.
