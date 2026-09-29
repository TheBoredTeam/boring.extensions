# Extension registry moved

The canonical Boring Notch extension registry is now
[TheBoredTeam/boring-notch-extensions](https://github.com/TheBoredTeam/boring-notch-extensions).

Authors maintain `extensions/<manifest-id>.toml` there. CI validates those TOML
records and generates one `catalog.json` for the native Store. Submit new
listings and release updates to that repository.

- [Create an extension with an AI assistant](https://github.com/TheBoredTeam/boring-notch-extensions/blob/main/LLM.txt)
- [Authoring conventions and best practices](https://github.com/TheBoredTeam/boring-notch-extensions/blob/main/AGENTS.md)
- [TOML schema and contribution guide](https://github.com/TheBoredTeam/boring-notch-extensions#register-or-update-a-native-extension)
- [Native API reference and preview compatibility](https://github.com/TheBoredTeam/boring-notch-extensions/blob/main/docs/README.md)

The new public feed is:

```text
https://raw.githubusercontent.com/TheBoredTeam/boring-notch-extensions/main/catalog.json
```

This repository retains its existing `catalog.plist` as a **frozen compatibility
feed** for preview clients that still use the former endpoint. Historical plist
sources and tooling remain for reference; automatic publication is disabled.
They are not a second active catalog. The two preview listings were migrated
without promoting them to approved downloadable releases.

The host change points new builds to the canonical JSON feed. A private binary
plist cache and a bundle's macOS `Info.plist` are unrelated to the catalog's TOML
authoring format and remain valid.
