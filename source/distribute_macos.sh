#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

APP_BUNDLE="${APP_BUNDLE:-$ROOT_DIR/dist_macos/scFlow Studio.app}"
DIST_DIR="${DIST_DIR:-$ROOT_DIR/dist_macos}"
APP_NAME="${APP_NAME:-scFlow Studio}"
DMG_PATH="${DMG_PATH:-$DIST_DIR/scFlow Studio.dmg}"
ENTITLEMENTS="${ENTITLEMENTS:-$ROOT_DIR/macos_entitlements.plist}"
IDENTITY="${DEVELOPER_ID_APP:-}"
KEYCHAIN_PROFILE="${NOTARYTOOL_PROFILE:-}"
APPLE_ID="${APPLE_ID:-}"
APPLE_TEAM_ID="${APPLE_TEAM_ID:-}"
APPLE_APP_PASSWORD="${APPLE_APP_PASSWORD:-}"
SKIP_NOTARIZE="${SKIP_NOTARIZE:-0}"

usage() {
  cat <<USAGE
Usage:
  DEVELOPER_ID_APP="Developer ID Application: Name (TEAMID)" \
  NOTARYTOOL_PROFILE="scflow-notary" \
  ./distribute_macos.sh

Alternative notarization credentials:
  DEVELOPER_ID_APP="Developer ID Application: Name (TEAMID)" \
  APPLE_ID="you@example.com" APPLE_TEAM_ID="TEAMID" APPLE_APP_PASSWORD="app-specific-password" \
  ./distribute_macos.sh

For a local unsigned DMG only:
  SKIP_NOTARIZE=1 ./distribute_macos.sh
USAGE
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ "$(uname)" != "Darwin" ]]; then
  echo "This script must run on macOS." >&2
  exit 1
fi

if [[ ! -d "$APP_BUNDLE" ]]; then
  echo "App bundle not found: $APP_BUNDLE" >&2
  echo "Run ./build_macos.sh first." >&2
  exit 1
fi

if [[ ! -f "$ENTITLEMENTS" ]]; then
  echo "Entitlements file not found: $ENTITLEMENTS" >&2
  exit 1
fi

mkdir -p "$DIST_DIR"

if [[ -z "$IDENTITY" && "$SKIP_NOTARIZE" != "1" ]]; then
  echo "Missing DEVELOPER_ID_APP. Installed signing identities:" >&2
  security find-identity -v -p codesigning >&2 || true
  echo >&2
  usage >&2
  exit 1
fi

cleanup_app() {
  local app="$1"
  echo "Cleaning app bundle..."
  find "$app" -name '*.dSYM' -prune -exec rm -rf {} + 2>/dev/null || true
  find "$app" -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
  find "$app" -name '*.pyc' -delete 2>/dev/null || true
  xattr -cr "$app" 2>/dev/null || true
}

sign_app() {
  local app="$1"
  if [[ -z "$IDENTITY" ]]; then
    echo "No Developer ID identity supplied; applying local ad-hoc signature only."
    /usr/bin/codesign --force --sign - --all-architectures --deep --timestamp=none "$app"
    return
  fi

  echo "Signing with: $IDENTITY"
  /usr/bin/codesign     --force     --sign "$IDENTITY"     --options runtime     --timestamp     --all-architectures     --deep     --entitlements "$ENTITLEMENTS"     "$app"

  echo "Verifying code signature..."
  /usr/bin/codesign --verify --deep --strict --verbose=4 "$app"
}

create_dmg() {
  local app="$1"
  local dmg="$2"
  local staging
  staging="$(mktemp -d "$DIST_DIR/dmg_staging.XXXXXX")"
  trap 'rm -rf "$staging"' RETURN

  echo "Creating DMG staging folder..."
  cp -R "$app" "$staging/"
  ln -s /Applications "$staging/Applications"

  rm -f "$dmg"
  echo "Creating DMG: $dmg"
  hdiutil create     -volname "$APP_NAME"     -srcfolder "$staging"     -ov     -format UDZO     "$dmg"

  xattr -cr "$dmg" 2>/dev/null || true
}

notarize_dmg() {
  local dmg="$1"
  if [[ "$SKIP_NOTARIZE" == "1" ]]; then
    echo "Skipping notarization because SKIP_NOTARIZE=1."
    return
  fi

  echo "Submitting DMG for notarization..."
  if [[ -n "$KEYCHAIN_PROFILE" ]]; then
    xcrun notarytool submit "$dmg" --keychain-profile "$KEYCHAIN_PROFILE" --wait
  else
    if [[ -z "$APPLE_ID" || -z "$APPLE_TEAM_ID" || -z "$APPLE_APP_PASSWORD" ]]; then
      echo "Missing notarization credentials." >&2
      usage >&2
      exit 1
    fi
    xcrun notarytool submit "$dmg"       --apple-id "$APPLE_ID"       --team-id "$APPLE_TEAM_ID"       --password "$APPLE_APP_PASSWORD"       --wait
  fi

  echo "Stapling notarization ticket..."
  xcrun stapler staple "$dmg"
  xcrun stapler validate "$dmg"
}

assess_outputs() {
  local app="$1"
  local dmg="$2"
  echo "Gatekeeper assessment for app:"
  spctl -a -vvv -t execute "$app" || true
  echo "Gatekeeper assessment for DMG:"
  spctl -a -vvv -t open --context context:primary-signature "$dmg" || true
}

cleanup_app "$APP_BUNDLE"
sign_app "$APP_BUNDLE"
create_dmg "$APP_BUNDLE" "$DMG_PATH"
notarize_dmg "$DMG_PATH"
assess_outputs "$APP_BUNDLE" "$DMG_PATH"

echo
echo "Distribution artifact: $DMG_PATH"
