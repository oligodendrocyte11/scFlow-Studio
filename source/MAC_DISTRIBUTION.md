# macOS Distribution

This project can build a local `.app` with `build_macos.sh` and can produce a Developer ID signed, notarized DMG with `distribute_macos.sh`.

## 1. Build the app

```bash
./build_macos.sh
```

Output:

```text
dist_macos/scFlow Studio.app
```

## 2. Requirements for direct distribution

To let other Macs open the app without the "damaged" / "unidentified developer" Gatekeeper warning, Apple requires:

- Apple Developer Program membership.
- A `Developer ID Application` certificate installed in Keychain.
- Notarization credentials for `xcrun notarytool`.

Check local signing identities:

```bash
security find-identity -v -p codesigning
```

You need an identity similar to:

```text
Developer ID Application: Your Name (TEAMID)
```

## 3. Recommended notarization setup

Create an App Store Connect API key or app-specific password, then store credentials once:

```bash
xcrun notarytool store-credentials "scflow-notary"   --apple-id "you@example.com"   --team-id "TEAMID"   --password "app-specific-password"
```

Then run:

```bash
DEVELOPER_ID_APP="Developer ID Application: Your Name (TEAMID)" NOTARYTOOL_PROFILE="scflow-notary" ./distribute_macos.sh
```

Output:

```text
dist_macos/scFlow Studio.dmg
```

## 4. Alternative one-shot credentials

```bash
DEVELOPER_ID_APP="Developer ID Application: Your Name (TEAMID)" APPLE_ID="you@example.com" APPLE_TEAM_ID="TEAMID" APPLE_APP_PASSWORD="app-specific-password" ./distribute_macos.sh
```

## 5. Local unsigned DMG for testing only

```bash
SKIP_NOTARIZE=1 ./distribute_macos.sh
```

This creates a DMG, but it is not a fully trusted public distribution artifact.

## 6. Current limitation

Without Developer ID signing and notarization, Gatekeeper can reject the app on another Mac. Users may see "damaged" or "cannot be opened" even when the app itself is technically complete.
