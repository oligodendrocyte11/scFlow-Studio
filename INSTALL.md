# Installation

## Windows x64 — scFlow Studio Agent V0.1.0

1. Open the [Windows V0.1.0 release](https://github.com/oligodendrocyte11/scFlow-Studio/releases/tag/windows-agent-v0.1.0).
2. Download `scFlow Studio Agent V0.1.0 Setup.exe`.
3. Verify its SHA-256 checksum against `CHECKSUMS.txt`.
4. Double-click the installer and choose the destination directory.
5. Launch **scFlow Studio Agent V0.1.0** from the Start menu or desktop shortcut.

The installer is not digitally signed. Windows SmartScreen may therefore display an **Unknown publisher** warning. Only continue after confirming that the downloaded file's SHA-256 checksum matches this repository.

The application bundles its required Python and R environments. Do not point the application to a system R installation. In **Settings**, leave the Rscript path on **Auto** unless troubleshooting.

### Trial period

- No activation is required through **2026-10-31**.
- A valid activation code is required starting **2026-11-01**.

### Uninstall

Use **Windows Settings > Apps > Installed apps > scFlow Studio Agent V0.1.0 > Uninstall**. Removing the application does not automatically remove projects saved outside the installation directory.

Back up project directories and exported results before uninstalling or upgrading.

## macOS

A matching macOS DMG will be distributed in a separate GitHub release. Follow the instructions and availability dates stated on that release page. Earlier academic-trial releases remain available as historical artifacts.

## Source builds

Project-owned source files are available in `source/`. Building the complete standalone application additionally requires matching platform-specific runtime bundles and package libraries. Do not assume that a source-only checkout contains the full distributable runtime.
