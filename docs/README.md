# Native extension API reference

[extension-api.h](extension-api.h) is a verbatim snapshot of the Boring Notch
native C ABI. It is included here so authors and coding assistants can read exact
function signatures and ownership rules without depending on an unpublished
host branch. It is a declaration/reference file, not an extension implementation
or a host library to link.

## Provenance and compatibility

- Upstream repository: [TheBoredTeam/boring.notch](https://github.com/TheBoredTeam/boring.notch).
- Upstream path: `docs/extension-api.h`.
- Source revision: `b7c2177cea9f31387f59716366c5d0a93645baa3` on the local
  `feat/live-activity-host` worktree, checked on 2026-09-29.
- SHA-256: `6f3cf593e429f2940cce7c9f89b880dced684401d3550ecc1244d9563d02012e`.
- License: upstream GPL-3.0 license text is included in [LICENSE-GPL-3.0.txt](LICENSE-GPL-3.0.txt).

At publication of this reference, that host revision has not been pushed or
released. Its full activities/tabs behavior is a **developer preview**. Do not
invent a public download URL or assume a current release, `main`, or `dev`
implements this entire header. Confirm the intended host build's capabilities
before promising installation, compact tabs, or lock-screen activity support.
The existing Now Playing catalog preview is a separate example; its source is
not evidence that it implements this full contract.

Manifest `apiVersion` is **1**, including the additive `tab_view_v2` factory.
The snapshot supports settings, collapsed desktop/lock-screen activities, and
native regular/compact tabs as described in the header. It does not expose host
resizing, forced navigation, a payment service, or a general secure-window API.

## Updating this snapshot

Compare the actual host header and implementation before changing the reference.
Copy the header verbatim, record the source revision and SHA-256, and update
`AGENTS.md` and `LLM.txt` if their guidance changes. When a compatible host is
publicly available, replace the preview availability note with verified links
and compatibility information; do not infer a minimum app version from ABI v1.

Check the snapshot without creating build artifacts:

```sh
shasum -a 256 docs/extension-api.h
xcrun clang -x c -fsyntax-only -include docs/extension-api.h /dev/null
xcrun clang++ -x c++ -fsyntax-only -include docs/extension-api.h /dev/null
```

The host's runtime/installer remains the authority for a particular build.
If it disagrees with this reference, document the mismatch and target a verified
compatible contract rather than relaxing host validation.
