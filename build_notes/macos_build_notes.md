# macOS Build Notes

Build source: `<PROJECT_ROOT>`

Build command:

```bash
bash build_macos.sh
```

Trial control file:

```text
resources/trial_config.json
```

The formal activation logic remains in `core/license_manager.py`. Trial mode is activated only when `resources/trial_config.json` is present and contains `"trial_mode": true`. Remove that file before building a formal activation-gated release.

Output app before packaging:

```text
dist_macos/scFlow Studio.app
```

Release archive:

```text
release/scFlow_Studio_Mac_AcademicTrial_2026-10-01.zip
```
