# GitHub Cleanup Report

## Removed
- `.DS_Store`
- `source/.DS_Store`
- `release/.DS_Store`
- `.Rhistory`
- `source/core/__pycache__`
- `source/ui/pages/__pycache__`

## Moved
- source/tools/generate_license_keypair.py -> <PRIVATE_BACKUP_DIR>/generate_license_keypair.py
- source/tools/generate_activation_code.py -> <PRIVATE_BACKUP_DIR>/generate_activation_code.py
- source/build_windows.ps1 -> source/build_windows.ps1.example

## Updated
- `build_notes/macos_build_notes.md`
- `source/README.md`
- `source/MAC_DISTRIBUTION.md`

## Created
- `.gitignore`
- `CHECKSUMS.txt`
- `RELEASE_NOTES.md`
- `DEPENDENCIES.md`
- `REVIEWER_QUICK_START.md`
- `KNOWN_LIMITATIONS.md`

## Final Public Release Cleanup

### Moved to private backup
- source/resources/license/public_key.pem -> <PRIVATE_BACKUP_DIR>/public_key.pem

### Removed temporary files
- `.DS_Store`

### Updated
- `.gitignore` now ignores `*.pem` while preserving `source/resources/license/README.md`.
- `source/resources/license/README.md` documents that the public key is not included in the public source snapshot.
