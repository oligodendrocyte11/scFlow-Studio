# Reviewer Quick Start

## 1. Download the Windows release

Download `scFlow Studio Agent V0.1.0 Setup.exe` and the English manual from the [`windows-agent-v0.1.0` release](https://github.com/oligodendrocyte11/scFlow-Studio/releases/tag/windows-agent-v0.1.0). Verify the installer checksum in `CHECKSUMS.txt`.

The Windows build runs without activation through 2026-10-31. Activation is required starting 2026-11-01.

## 2. Install and launch

Run the installer on Windows 10 or Windows 11 x64. The build is not digitally signed, so SmartScreen may display an Unknown publisher warning.

## 3. Prepare test data

Recommended demonstration dataset:

- Dataset: GSE250245
- Samples: Sham, MMCAO, and SMCAO
- Groups: Sham; MCAO; MCAO

The repository does not include the large raw dataset. Prepare the 10X folders from the original public source before importing.

## 4. Suggested smoke test

1. Create a project in a writable directory outside the installation folder.
2. Import one small 10X sample or H5AD object.
3. Confirm sample name, group, and species.
4. Run Data Import and Quality Control.
5. Confirm that the Log updates and result previews are generated.
6. Save and reopen the project.

## 5. Full workflow

For complete testing, follow the 16 numbered pages and the GSE250245 walkthrough in `docs/scFlow-Studio-Agent-V0.1.0-User-Manual.docx`.

A matching macOS DMG will be published separately with platform-specific instructions.
