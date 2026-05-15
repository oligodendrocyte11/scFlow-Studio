# Reviewer Test Instructions

## Purpose

This academic trial build lets reviewers inspect and run the scFlow Studio workflow without requesting an activation code.

## Trial App

- File: `release/scFlow_Studio_Mac_AcademicTrial_2026-10-01.zip`
- Valid until: 2026-10-01
- Activation: not required

## Suggested Smoke Test

1. Unzip the release file.
2. Launch `scFlow Studio.app`.
3. Confirm the main window title includes **Academic Trial Version**.
4. Create a small test project.
5. Import a small 10X matrix folder.
6. Run data checking and one lightweight QC step.
7. Confirm outputs appear in the preview/results panel and the project cache.

## macOS Security Note

The trial build is ad-hoc signed but not Apple-notarized. If macOS blocks the app, right-click **Open** or remove quarantine for local testing.
