# obtainium-thor-pack

A single Obtainium import file, regenerated daily by GitHub Actions from upstream
Obtainium packs (in priority order) and, for repositories no pack covers, from
repository metadata. Sources are declared in `sources.yaml`; nothing else is listed by hand.

Import URL (Obtainium: Import/Export > Obtainium Import, or add it as a source):

    https://github.com/OWNER/obtainium-thor-pack/releases/latest/download/obtainium-thor-pack.json

Repositories without an APK in their releases are skipped and listed in the job summary.
Generated entries use a placeholder app id with `allowIdChange` enabled.
