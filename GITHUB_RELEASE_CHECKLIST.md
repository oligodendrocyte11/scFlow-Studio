# GitHub Release Checklist

## Repository materials

- [x] Cross-platform README with current Windows release information
- [x] Windows installation and uninstall instructions
- [x] Quick start and GSE250245 sample grouping
- [x] Complete English Word manual
- [x] Release notes and changelog
- [x] Version and dependency summary
- [x] SHA-256 checksums
- [x] License, notice, citation, and third-party dependency statements
- [x] Known limitations and security guidance
- [x] Public screenshot without local paths, credentials, or sample identifiers

## Windows release assets

- [x] `scFlow Studio Agent V0.1.0 Setup.exe`
- [x] `scFlow Studio Agent V0.1.0 User Manual.docx`
- [x] Installer size below GitHub's 2 GiB per-release-asset limit
- [x] Activation-free through 2026-10-31
- [x] Activation required starting 2026-11-01
- [x] Unsigned-installer warning documented

## Before publishing

- [ ] Confirm the intended GitHub account is signed in
- [ ] Upload the repository documentation commit
- [ ] Create tag `windows-agent-v0.1.0`
- [ ] Upload both release assets
- [ ] Publish the release and verify the online asset sizes and checksums

## Later macOS release

Publish the matching DMG under a separate tag and release page. Add its checksum, signing/notarization status, system requirements, and availability policy without replacing the Windows-specific instructions.
