# GitHub Release Checklist

## Copied Source Code List

- `source/app/`
- `source/core/`
- `source/ui/`
- `source/widgets/`
- `source/tools/`
- `source/r_scripts/`
- `source/resources/` including `trial_config.json`
- `source/main.py`
- `source/requirements.txt`
- macOS packaging files and icons

## Generated Documentation List

- `README.md`
- `INSTALL.md`
- `QUICK_START.md`
- `USER_MANUAL.md`
- `CODE_AVAILABILITY.md`
- `availability_statement_template.md`
- `reviewer_test_instructions.md`
- `software_description.md`
- `LICENSE_ACADEMIC.md`
- `CITATION.cff`
- `VERSION.txt`
- `CHANGELOG.md`
- `LICENSE`
- `NOTICE`
- `THIRD_PARTY_LICENSES.md`
- `DATA_LICENSE.md`
- `demo_data/README.md`
- `build_notes/macos_build_notes.md`

## Trial App Build Path

`release/scFlow_Studio_Mac_AcademicTrial_2026-10-01.zip`

## Trial Expiration Behavior

- Trial mode is controlled by `resources/trial_config.json`.
- Active trial date range: current date through 2026-10-01 inclusive.
- After 2026-10-01, startup is blocked with the message: `This academic trial version expired on 2026-10-01. Please contact the authors for an updated version.`

## Activation Scope

- Activation is disabled only when `trial_config.json` is present and `trial_mode` is true.
- The regular license/activation code path remains in `core/license_manager.py`.
- The temporary root `resources/trial_config.json` used for this trial build was removed after packaging; the release source snapshot and packaged app still include it. Remove `resources/trial_config.json` from any future source checkout before building a formal activation-gated release.

## Remaining Manual Steps Before Uploading

- Replace remaining manuscript metadata placeholders after archival: GitHub URL is `https://github.com/oligodendrocyte11/scFlow-Studio`; Zenodo DOI remains `TODO: Zenodo DOI to be added after archival release`; author metadata has been partially filled as Zhuang Yuming where requested; contact email still needs confirmation.
- Confirm final license terms with the authors/institution.
- Upload this folder or a curated repository copy to GitHub.
- Archive the final repository release on Zenodo to obtain a DOI.
- Add the DOI and repository URL to the manuscript availability statement.

## Suggested Zenodo Archiving Step

Create a GitHub release, connect the repository to Zenodo, archive the release, and record the Zenodo DOI in `CITATION.cff` and `availability_statement_template.md`.

## Known Limitations

- The macOS trial app is ad-hoc signed and not Apple-notarized. Reviewers may need to use right-click **Open** or remove quarantine locally.
- The source snapshot does not duplicate the full bundled runtime or reference cache; these are included in the release app archive.
- Very large scRNA-seq datasets may require substantial RAM and disk space.

## Validation Performed

- Built `dist_macos/scFlow Studio.app` successfully with `bash build_macos.sh`.
- Verified the built app contains `Contents/Resources/resources/trial_config.json`.
- Verified the GitHub source snapshot reports `source_trial=True`, `source_valid=True`, and `source_expires=2026-10-01`.
- Verified the root working project no longer has `resources/trial_config.json`, so future formal builds do not automatically enter trial mode.
- Verified the release zip contains `scFlow Studio.app/Contents/MacOS/scFlow Studio` and bundled `trial_config.json`.
- Launch-smoke-tested the built app; the process stayed alive for the smoke window and did not immediately exit.

## Release Archive

- Archive: `release/scFlow_Studio_Mac_AcademicTrial_2026-10-01.zip`
- Approximate archive size on this machine: 1.6 GB

## 2026-05-10 Patch Validation

- Fixed GSEA parameter labels: `Minimum genes per pathway` and `Maximum genes per pathway`.
- Fixed main annotation plot basenames/titles to follow the selected reduction (`umap_*` or `tsne_*`).
- Fixed subcluster and subtype plot basenames/titles to follow the selected reduction, including t-SNE split-by-group output.
- Synced the same fixes into `source/` for the GitHub/manuscript release folder.
- Rebuilt the academic trial app and overwrote `release/scFlow_Studio_Mac_AcademicTrial_2026-10-01.zip`.
- Removed the temporary root `resources/trial_config.json` after rebuilding; the packaged app and GitHub source snapshot still include the trial config.

## Licensing Update

- The original scFlow Studio source code is documented as source-available for non-commercial academic use under the PolyForm Noncommercial License 1.0.0.
- Commercial use requires prior written permission from the authors.
- Third-party dependencies remain under their respective original licenses and are not relicensed by this repository.

