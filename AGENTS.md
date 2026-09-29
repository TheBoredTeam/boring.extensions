# Instructions for extension authors and coding assistants

Build small, independently distributed native macOS extensions that cooperate
with the host. Keep feature behavior inside the extension and use the documented
boundary for presentation. Prefer one clear implementation with reusable models
and controls over duplicated layouts or speculative frameworks.

## Scope and source of truth

This repository contains Store records, catalog tooling, and an API reference.
Create extension source in a separate project/repository. Do not put product
code, bundles, ZIPs, customer data, or build output under `extensions/`; that
directory contains only reviewed listing plists. Do not add an extension target,
source dependency, or bundled product to the Boring Notch build.

Read [the API provenance](docs/README.md), [the exact header](docs/extension-api.h),
and [the catalog schema](README.md). The header defines the binary boundary;
this guide supplies implementation conventions. Verify the target host's
contract if it differs from this snapshot, and explain compatibility differences
instead of silently guessing. The activities/tabs implementation is a developer
preview. Publishing this guide does not make it available in every released app.

The five base exports and optional activity/tab exports belong to **manifest
`apiVersion: 1`**. `bn_extension_tab_view_v2` is an additive layout-aware factory;
it does not imply `apiVersion: 2`. There is no host Swift package to import, no
JSON widget language, and no registration API that can force tab selection.
Do not confuse the internal host `NotchLiveActivity` Swift protocol with the
public C ABI used by independent bundles.

## Start with a concrete extension

1. Establish the main user action, a publisher-owned reverse-domain ID, target
   macOS/host build, and needed surfaces: activity, tab, settings, or a combination.
   Ask only for missing details that change implementation; state reasonable
   defaults for reversible choices.
2. Make one useful vertical slice: create an instance, publish a stable identity,
   mount a native view, update its model, and destroy it cleanly. Then add behavior.
3. Default to macOS 14+ with AppKit and SwiftUI, or AppKit alone. Record the actual
   minimum version and architectures tested. Guard newer system APIs explicitly.
4. Build in the extension's own project. A suitable starting layout is:

   ```text
   MyExtension/
     Sources/                 # ABI adapter, model, services, native views
     Resources/               # assets and localized strings
     Tests/                   # model and ABI/lifecycle smoke tests
     manifest.json
     Info.plist
     build.sh                 # standalone compilation/signing/ZIP packaging
     README.md                # requirements, build, install, privacy, licensing
     .gitignore               # dist/, local credentials, temporary output
   ```

   This source layout is a convention; the installed bundle layout below is the
   contract. Add files/modules when responsibilities warrant them.

Keep the ABI adapter thin. One instance owns the shared model and services;
controllers observe that model. Share commands, formatting, controls, and state
between activities, regular tabs, compact tabs, and settings. Use explicit
dependencies for clocks, network clients, storage, or purchase checks when they
make testing useful. Avoid global mutable feature state and one generic
abstraction for every possible future extension.

Use a unique Swift module name and publisher-prefixed Objective-C class names,
including explicit `@objc` names. Objective-C class names share a process-wide
namespace even when binaries are loaded separately. Store preferences in your
own identifier-based namespace; never overwrite the host's standard defaults.
Resolve assets/localizations from your extension bundle, not `Bundle.main`
(which is the host). Do not replace the application's delegate, run another
application event loop, or change process-wide appearance for your feature.

## Package identity

```text
org.example.focus.bnplugin/
  Contents/
    Info.plist
    MacOS/Focus
    Resources/manifest.json
```

Example manifest; replace the example publisher and identity before distribution:

```json
{
  "id": "org.example.focus",
  "name": "Focus",
  "version": "1.0.0",
  "apiVersion": 1,
  "activation": "always",
  "capabilities": ["liveActivities", "tabs"]
}
```

Declare only implemented capabilities. `activation` is `always` or `lockScreen`
and governs routine media delivery, not automatic activity withdrawal. It does
not grant a lock-screen tab or a general secure-window API.

Use a lowercase reverse-domain manifest ID matching
`[a-z][a-z0-9]*(\.[a-z0-9-]+)+`, at most 128 UTF-8 bytes. `CFBundleIdentifier`
must equal that ID; `CFBundleExecutable` names the actual binary. Set
`CFBundlePackageType` to `BNDL`, record `LSMinimumSystemVersion`, and keep
`CFBundleShortVersionString` aligned with the manifest release version. Use
monotonic `CFBundleVersion` values and a consistent versioning scheme.

Use one bundle at the ZIP root. Do not include an enclosing release folder,
another product bundle, links, encrypted files, or paths outside the bundle.
The installer allows at most 100,000,000 bytes compressed and expanded, 4,096
entries, and 65,536 bytes each for `Info.plist` and `manifest.json`.

## ABI, threading, and ownership

Export the exact C names and types in [extension-api.h](docs/extension-api.h).
All five base functions are required: `bn_extension_create_v1`,
`bn_extension_destroy_v1`, `bn_extension_update_v1`, `bn_extension_event_v1`, and
`bn_extension_settings_v1`. A settings export may return null. Swift authors
can use `@_cdecl` with C-compatible pointer/scalar types and an
`@convention(c)` command callback; no Swift objects or generics cross the ABI.

All ABI calls and command callbacks run on the main thread. Keep them short:
perform networking, expensive decoding, and blocking file work asynchronously,
then publish model changes on the main actor. Never block the main thread waiting
for a task that needs the main thread. Copy borrowed input before asynchronous use.

| Value | Ownership rule |
| --- | --- |
| Instance from `create` | Extension supplies one owned reference; `destroy` consumes it exactly once. In Swift, pair `passRetained` with `takeRetainedValue` in destruction. Ordinary calls use `takeUnretainedValue`. |
| Host command context | Opaque borrowed identity. Pass back unchanged; never dereference or release it. |
| Input JSON/IDs/events | Borrowed for the current call only. Copy/decode before returning. `update` uses its explicit byte count, not an assumed NUL terminator. |
| Activity/tab JSON result | Extension-owned, NUL-terminated UTF-8 buffer valid until the next ABI call. Never return a temporary `withCString` pointer. |
| Activity/tab controller | Fresh **+1 retained** `NSViewController` on every request; host consumes that retain. Swift factories use `Unmanaged.passRetained`. Never reuse a controller across displays or regions. |
| Settings controller | Borrowed pointer retained by the extension until destruction; host also retains it while displayed. Swift uses `passUnretained`, not the activity/tab ownership rule. |

Store state before invoking callbacks. Do not call the host during `create`;
the instance becomes registered after it returns. Commands can start with the
first update. The host defers metadata reconciliation; do not require synchronous
remounts inside callbacks. Validate input, ignore unknown JSON keys/events, and
contain errors at the ABI boundary. Avoid forced unwraps or process termination
on external data.

During `destroy`, mark the model inactive, silence command closures, cancel
tasks/timers, remove observers, close extension-owned windows, and free snapshot
buffers. A cancellation request alone is insufficient: late completions must
check instance lifetime before mutating state or calling the host. Views can
survive teardown transitions; they must retain safe state and become inert.
Never invoke a callback after destruction.

## Collapsed live activities

Declare `liveActivities`, export the snapshot and region factories, and return
complete snapshots such as:

```json
{"activities":[{"id":"focus-1","label":"Focus timer","relevance":"active"}]}
```

The header specifies all bounds: 16 activities per provider, 65,536 snapshot
bytes, local IDs of 1–100 ASCII bytes, and labels up to 256 UTF-8 bytes. Local
IDs use `[A-Za-z0-9][A-Za-z0-9._-]*`; the host supplies the publisher namespace.
Use a stable ID for one ongoing activity, and a new ID for a new session. Publish
`activities.changed` after descriptor or membership changes. Update the existing
observable model for ordinary text/progress changes without rebuilding views.

Supply only leading (`region = 0`) and trailing (`region = 1`) content. The host
owns camera clearance, outer padding, width limits, animations, selection, and
interruptions. Return null for an empty region. Supply finite ideal sizes and
adapt/truncate within bounds; never draw a camera spacer or reposition the host.
Do not use `timeSensitive` for every update to try to dominate other activities.

Remove an activity from the next snapshot to end it; an empty array withdraws
all. Optional `expiresAt` is finite UNIX seconds. Omitted `displays` means all
eligible displays; an empty list means none. Invalid JSON is not an empty result.

`surface` defaults to `desktop`. Publish `lockScreen` only after the host snapshot
advertises it in `activitySurfaces`; absent support means desktop only. Locked
regions are noninteractive and hidden while asleep or the session is inactive.
Choose deliberately what can appear on a locked Mac, including user-configurable
redaction for sensitive content. Tabs and the opened workspace never render there.

## Native tabs and compact layouts

Declare `tabs`, export `bn_extension_tabs_v1`, and at least one tab view factory:

```json
{"tabs":[{"id":"focus","title":"Focus","symbol":"timer","presentations":["regular","compact"]}]}
```

Each provider gets at most **eight tabs**, not hundreds. Hundreds of tabs across
many providers are supported by the host; do not split one product into many
providers to evade the limit. Prefer a small number of purpose-driven tabs and
navigation/search within their content. Titles are nonblank, without control
characters, and at most 64 UTF-8 bytes; SF Symbol names are at most 128 bytes.
Use available symbols with meaningful accessible titles. IDs follow the activity
grammar and remain stable through title/icon changes.

Omitting `presentations` means regular-only. Compact requires both explicit
`compact` membership and `bn_extension_tab_view_v2`. With v2 present, the host
uses it for regular and compact; a null result does **not** fall back to v1.
Export v1 additionally only when supporting compatible older hosts' regular UI.

The v2 factory receives a context like:

```json
{"presentation":"compact","displayID":null,"contentSize":{"width":336,"height":132}}
```

Decode it during the call, ignore unknown fields, validate finite positive
dimensions, and reject unsupported presentations. These numbers are an example,
not ABI constants. Layout in the supplied bounds; preferred size cannot enlarge
the notch. Design a deliberate compact layout that prioritizes the main action.
Share models and reusable controls with regular mode; do not scale down an
oversized regular view or declare compact support without implementing it.

The host supplies tab chrome and controls embedded/floating placement. Do not
draw another switcher, force selection, or attach the tab to another host window.
Use native SwiftUI/AppKit controls, internal scrolling, keyboard navigation,
accessible labels, suitable contrast, and Reduced Motion support. Do not grab
keyboard focus on mount. The selected tab alone mounts, separately per display;
retain durable feature/navigation state in the model across remounts.

Use `tabs.changed` for membership/title/icon/presentation changes, not progress
ticks. An empty array withdraws all tabs. Removal or presentation incompatibility
returns selection to Home. Hidden tabs should not create controllers or start
render timers; suspend visibility-specific work on unmount while preserving
necessary feature work. The existing strip provides scrolling and overflow;
do not promise host tab search, pinning, grouping, or recents.

## Commands and feature services

Use only the implemented commands:

| Command | Value |
| --- | --- |
| `activities.changed`, `tabs.changed` | `0` |
| `media.toggle`, `media.next`, `media.previous`, `media.favorite` | `0` |
| `media.seek` | Finite position in seconds within track bounds |
| `presentation.active`, `presentation.artwork` | `0` to opt out, `1` to opt in |

`presentation.active` controls routine media snapshots, not tab/activity
membership. Handle `lock`, `unlock`, `sleep`, `wake`, `session-inactive`, and
`session-active`; reconcile clocks after resuming instead of replaying missed
ticks. Media JSON includes title/artist/album, duration/elapsed/timestamp/rate,
playing/idle, favorite/canFavorite, base64 JPEG artwork, `activitySurfaces`, and
`presentationAllowed`. Accept empty/missing optional content. Extrapolate media
time from timestamp/rate; opt out of artwork if unused.

Use event-driven services and one shared clock where possible. Bound caches,
network responses, retries, and polling. Make network work cancellable and keep
errors recoverable in the extension UI. Never launch one timer per hidden tab.
Native plugins run **inside the host process**, sharing its permissions and
crash fate; signing does not provide per-plugin process isolation. Do not claim
sandbox isolation or an unsupported host permission broker.

Keep secrets out of source, plists, logs, and ZIPs. Use appropriate Keychain and
publisher-owned service storage, with explicit configuration and useful error
states. Do not invent extra host entitlements or weaken verification to make an
integration work. Explain unsupported requirements before depending on them.

## Build, test, and distribute

Build a standalone native library using system frameworks. A Swift build script
may use `xcrun swiftc -emit-library` with a unique module and an explicit macOS
target, then place the result at `Contents/MacOS/<CFBundleExecutable>`. Avoid
developer-machine absolute dylib paths. Build and verify arm64/x86_64 slices if
claiming both; an Apple silicon build alone is not a universal release.

For an isolated local test, an intact ad-hoc signature is accepted only by a
Debug host explicitly launched with `BN_ALLOW_DEVELOPMENT_EXTENSIONS=1`.
`BN_EXTENSION_TEST_DIRECTORY` can point that Debug host to disposable packages.
These overrides are absent in Release. Do not alter the user's normal installed
extensions or claim an ad-hoc smoke test verifies production distribution.

Validate the actual generated artifact and feature behavior:

- Check exported symbol names, manifest/Info.plist identity, architectures, and
  signature integrity. Load the separate binary through the real ABI, not just
  a model mock.
- Exercise create/update/event/destroy, empty publications, malformed/unknown
  input, activity expiry, metadata changes, withdrawal, and late task completion.
  Verify stable IDs and no callbacks after teardown.
- Mount fresh region/tab controllers for separate display contexts; check retain
  balance, controller safety after destruction, and no eager hidden views.
- Test each declared presentation, narrow supplied bounds, live model updates,
  mode changes, keyboard controls, accessibility, and Reduced Motion. For a
  lock-screen feature, separately test actual lock/unlock and sleep/wake.
- Install the ZIP through Settings, disable/re-enable, update/restart, uninstall,
  and confirm a failed replacement preserves the previous installation. Exercise
  physical multi-display behavior if claiming support was verified there.

If a compatible host checkout is available, its
`examples/live-activity-extension/` build/smoke/install scripts demonstrate the
real adapter and installer. Adapt assertions to the new extension; passing Focus
Timer's tests alone does not validate another binary. Simulated display contexts
are not evidence of physical multi-monitor testing.

Production distribution requires the publisher's own **Developer ID Application**
signature and Apple notarization. Preserve third-party notices and review the
licenses of reused implementation code; a paid product is not exempt from them.
Never use Boring Notch's publisher identity or fabricate credentials. Verify the
final ZIP in a signed compatible host on a clean Mac. A loaded Swift binary
cannot be safely unloaded/replaced live; respect the host's restart requirement.

## Store records and payments

Follow [README.md](README.md) for complete plist fields and limits. Keep
`extensions/<manifest-id>.plist`, its `id`, and the bundle ID identical. Use an
honest `preview` or `coming-soon` record until an actual release exists. Example
IDs, Team IDs, URLs, and digest placeholders are never publishable metadata.

For `available`, use a public immutable HTTPS ZIP URL and its actual final
SHA-256 digest, exact version, publisher Team ID, and `apiVersion: 1` in
`artifact`. Hash after signing, notarization, and final packaging. Listing,
artifact, and manifest versions must match. Submission includes release/source
links and real signing/compatibility evidence for maintainer review.

The Store handles discovery, download, publisher review, and installation.
Developers own checkout, licenses, activation, refunds, and paid access. Price
metadata is not an entitlement. A paid bundle can be downloaded publicly and
enforce access through its own settings/service. `purchaseUrl` is the checkout
destination; `artifact.downloadURL` must deliver the ZIP without customer tokens.

Edit individual source plists, not the generated `catalog.plist`. For catalog
or validator changes, run from this repository:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/catalog.py --output /tmp/boring-extension-catalog.plist
```

When sources are unchanged, `python3 scripts/catalog.py --check` verifies the
committed aggregate. With changed source records it may correctly report stale
output; main's workflow generates the aggregate after merge. Never use the CI
publication script's destructive disposable-checkout cleanup in a user checkout.
Do not broaden workflow permissions or touch unrelated listings for one submission.

For documentation-only changes, check references and API accuracy; a full app
rebuild is unnecessary. Update the header snapshot only with matching provenance
and reviewed host evidence, following [docs/README.md](docs/README.md).

## Completion report

Deliver the extension source, reproducible build instructions, packaged artifact
when build tools are available, and tests relevant to the actual feature. Explain
its privacy/data behavior, settings, compatibility, installation, and uninstall.
Separate what is implemented from what was built, smoke-tested, installed in a
real app, signed/notarized, published, and approved in the Store. List material
untested cases. Never imply that generated code, a preview listing, or a passing
unit test means a release is ready for everyday users.
