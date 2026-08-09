# Reviewer Test Instructions

## Purpose

The time-limited Windows V0.1.0 release lets reviewers inspect and run the complete English workflow without requesting an activation code through 2026-10-31.

## Release assets

- `scFlow Studio Agent V0.1.0 Setup.exe`
- `scFlow Studio Agent V0.1.0 User Manual.docx`
- SHA-256 values in `CHECKSUMS.txt`

## Suggested smoke test

1. Verify the installer checksum.
2. Install and launch the application.
3. Create a project outside the installation directory.
4. Import a small 10X sample or H5AD object.
5. Confirm sample metadata and run Data Import.
6. Run Quality Control and verify the progress indicator, Log, figures, and tables.
7. Save, close, and reopen the project.

## Reporting a problem

Record the application version, Windows version, input format, step name, parameters, and final Log lines. Remove API keys, personal directories, and restricted sample information before sharing logs or screenshots.
