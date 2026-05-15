# Installation

## macOS Academic Trial Build

1. Open `release/scFlow_Studio_Mac_AcademicTrial_2026-10-01.zip`.
2. Extract `scFlow Studio.app`.
3. Place the app in a normal user directory.
4. Double-click to launch. No activation code is required for this trial build.

If macOS reports that the app cannot be opened because it is from an unidentified developer, use right-click **Open** or run:

```bash
xattr -dr com.apple.quarantine "scFlow Studio.app"
```

## Source Build

The source code is available in `source/`. Rebuilding the full standalone macOS app requires the prepared bundled runtime folders documented in `source/vendor/README.md`, Python dependencies in `requirements.txt`, and the macOS build script:

```bash
cd source
bash build_macos.sh
```

The trial mode is controlled by `resources/trial_config.json`. Remove that file before building a formal license-gated version.
