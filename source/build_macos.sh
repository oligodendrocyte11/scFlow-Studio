#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

echo "== scFlow Studio macOS build =="
echo "Root: $ROOT_DIR"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "This script is intended to run on macOS." >&2
  exit 1
fi

if [[ -n "${SCFLOW_PYTHON:-}" ]]; then
  PYTHON_BIN="$SCFLOW_PYTHON"
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  PYTHON_BIN="python3"
fi

SPEC_FILE="$ROOT_DIR/scflow_studio_macos.spec"
DIST_DIR="$ROOT_DIR/dist_macos"
BUILD_DIR="$ROOT_DIR/build_macos"

if [[ ! -f "$SPEC_FILE" ]]; then
  echo "Missing spec file: $SPEC_FILE" >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c "import PySide6, PyInstaller, numpy, pandas, scipy, h5py, openpyxl; print('ok')" >/dev/null 2>&1; then
  echo "Selected Python environment is missing required packages." >&2
  echo "Install dependencies first, for example:" >&2
  echo "  pip install -r requirements.txt pyinstaller" >&2
  exit 1
fi

mkdir -p "$DIST_DIR" "$BUILD_DIR"

if [[ ! -f "$ROOT_DIR/Singlecell.icns" ]]; then
  echo "Warning: Singlecell.icns not found. The app bundle may use a generic icon."
fi

echo "Using Python: $PYTHON_BIN"
if command -v Rscript >/dev/null 2>&1; then
  echo "Using system Rscript for build-time checks: $(command -v Rscript)"
else
  echo "System Rscript not found; build will rely on bundled runtime only."
fi

"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath "$DIST_DIR" \
  --workpath "$BUILD_DIR" \
  "$SPEC_FILE"

APP_BUNDLE="$DIST_DIR/scFlow Studio.app"
RUNTIME_DUP="$APP_BUNDLE/Contents/Frameworks/vendor/cellassign_runtime"
RUNTIME_RES="$APP_BUNDLE/Contents/Resources/vendor/cellassign_runtime"
SOURCE_RUNTIME="$ROOT_DIR/vendor/cellassign_runtime"

if [[ -d "$APP_BUNDLE" && -d "$SOURCE_RUNTIME" ]]; then
  echo "Refreshing bundled CellAssign runtime in Resources..."
  rm -rf "$RUNTIME_RES"
  mkdir -p "$(dirname "$RUNTIME_RES")"
  cp -R "$SOURCE_RUNTIME" "$RUNTIME_RES"
fi

if [[ -d "$RUNTIME_DUP" ]]; then
  echo "Removing duplicate Frameworks CellAssign runtime copy..."
  rm -rf "$RUNTIME_DUP"
fi

cleanup_distributable_bundle() {
  local app_bundle="$1"
  local runtime_root="$app_bundle/Contents/Resources/vendor/cellassign_runtime"

  echo "Cleaning distributable bundle..."

  find "$app_bundle" -name '*.dSYM' -prune -exec rm -rf {} + 2>/dev/null || true
  find "$app_bundle" -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
  find "$app_bundle" -name '*.pyc' -delete 2>/dev/null || true

  if [[ -d "$runtime_root/Python.framework/Versions/3.13" ]]; then
    rm -rf "$runtime_root/Python.framework/Versions/3.13/include" 2>/dev/null || true
    rm -f "$runtime_root/Python.framework/Versions/3.13/Headers" 2>/dev/null || true
    rm -rf "$runtime_root/Python.framework/Versions/3.13/share" 2>/dev/null || true
    rm -rf "$runtime_root/Python.framework/Versions/3.13/etc" 2>/dev/null || true
    rm -f "$runtime_root/Python.framework/Versions/3.13/bin/idle3" 2>/dev/null || true
    rm -f "$runtime_root/Python.framework/Versions/3.13/bin/idle3.13" 2>/dev/null || true
    rm -f "$runtime_root/Python.framework/Versions/3.13/bin/pydoc3" 2>/dev/null || true
    rm -f "$runtime_root/Python.framework/Versions/3.13/bin/pydoc3.13" 2>/dev/null || true
    rm -f "$runtime_root/Python.framework/Versions/3.13/bin/python3-config" 2>/dev/null || true
    rm -f "$runtime_root/Python.framework/Versions/3.13/bin/python3.13-config" 2>/dev/null || true
    rm -f "$runtime_root/Python.framework/Versions/3.13/bin/python3-intel64" 2>/dev/null || true
    rm -f "$runtime_root/Python.framework/Versions/3.13/bin/python3.13-intel64" 2>/dev/null || true
  fi

  xattr -cr "$app_bundle" 2>/dev/null || true
}

if [[ -d "$APP_BUNDLE" ]]; then
  cleanup_distributable_bundle "$APP_BUNDLE"
fi

if command -v /usr/bin/codesign >/dev/null 2>&1 && [[ -d "$APP_BUNDLE" ]]; then
  echo "Re-signing app bundle..."
  /usr/bin/codesign --force --sign - --all-architectures --deep --timestamp=none "$APP_BUNDLE" || true
fi

echo
echo "Build finished."
echo "App bundle: $APP_BUNDLE"
