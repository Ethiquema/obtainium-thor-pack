# obtainium-thor-pack

One [Obtainium](https://github.com/ImranR98/Obtainium) import file for handheld Android gaming
(built for the AYN Thor and other dual-screen devices): emulators, frontends, native ports of
classic games (recompilations and decompilations), dual-screen companion apps and tools.
It is regenerated every day by GitHub Actions, so apps and sources stay current without any
manual editing.

## Install

1. Install [Obtainium](https://github.com/ImranR98/Obtainium/releases/latest).
2. In Obtainium: **Import/Export > Obtainium Import**, then select the file downloaded from:

   ```
   https://github.com/Ethiquema/obtainium-thor-pack/releases/latest/download/obtainium-thor-pack.json
   ```

3. Add a GitHub token in Obtainium settings: importing a hundred apps hits the anonymous API rate limit.

Re-importing later adds new apps and updates existing entries; apps you added yourself are kept.

## What is inside

<!-- catalogue:start -->
<!-- catalogue:end -->

## How it is built

[`sources.yaml`](sources.yaml) lists the sources in priority order. The first source that provides an
app wins; apps are deduplicated by repository URL, then by app id.

1. Existing Obtainium packs, read as published: [RJNY](https://github.com/RJNY/Obtainium-Emulation-Pack),
   [stopthink](https://github.com/stopthink/Obtainium-Emulation-Pack-Plus) (standard and dual-screen),
   [BBoi34 Recomp/Decomp](https://codeberg.org/BBoi34/Obtainium-Recomp-Decomp),
   [joeys-obtainium](https://github.com/JoeysRetroHandhelds/joeys-obtainium).
2. Repositories no pack covers: the [Dual-Screen-Games](https://github.com/codm2000/Dual-Screen-Games)
   catalogue is parsed and an entry is generated from each repository's metadata.
   Only repositories whose releases ship an APK are kept; the others (mod zips, no release) are listed
   as skipped in [CATALOGUE.md](CATALOGUE.md).

`README.md` (this list) and `CATALOGUE.md` are rewritten by the workflow on each run.

## Limits

- Generated entries (not taken from a pack) use `owner.repo` as a placeholder app id with
  `allowIdChange` enabled, so Obtainium can replace it with the real package name.
- The file has no `settings` block: importing it never overwrites your Obtainium preferences.
- Dual-screen builds are separate forks (Azahar, melonDS, Cemu, Eden Duo): install the fork, not the upstream emulator.

## Add a source

Edit `sources.yaml` and push. Types: `github-release-asset` (repo, asset_regex), `github-file` (repo, path),
`deeplink-page` (url of a page with `obtainium://app/...` links),
`link-page` (a page listing repositories), `repos` (list of repository URLs).

## Run locally

```
pip install pyyaml
GITHUB_TOKEN=<token> python3 generate.py
```

Environment: `OUTPUT`, `CATALOGUE`, `README`, `SOURCES` override the default file paths.
