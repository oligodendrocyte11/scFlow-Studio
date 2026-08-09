# Public Release Hygiene

The Windows V0.1.0 publication materials were prepared with the following safeguards:

- Installers and large runtime folders are kept out of Git history and distributed as Release assets.
- The English manual was checked for local paths, API keys, comments, author metadata, and revision identifiers.
- Public screenshots use the English application interface and do not show personal projects or credentials.
- SHA-256 checksums are published for the installer and manual.
- Private signing keys, activation-generation tools, local validation outputs, temporary files, and runtime caches are not part of the Windows publication materials.
- The unsigned Windows installer status is disclosed to users.
- Platform-specific releases use separate tags so Windows and macOS requirements remain unambiguous.

Before each future release, repeat the secret scan, checksum generation, malware/signing review, documentation review, and online asset verification.
