#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ "${OS:-}" == "Windows_NT" ]]; then
  echo "This script must run inside WSL or Linux, not native Windows."
  exit 1
fi

missing_commands=()
for cmd in python3 git zip unzip java; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    missing_commands+=("$cmd")
  fi
done

if (( ${#missing_commands[@]} > 0 )); then
  echo "Missing required system tools: ${missing_commands[*]}"
  echo "Install them first with:"
  echo "  sudo apt update && sudo apt install -y python3 python3-venv python3-pip openjdk-17-jdk git zip unzip"
  exit 1
fi

if [[ ! -d .venv-android ]]; then
  python3 -m venv .venv-android
fi

source .venv-android/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install --upgrade buildozer cython

echo
echo "============================================================"
echo "PyPondo Android build starting"
echo "============================================================"
echo

python buildozer_shim.py android debug

latest_apk="$(ls -1t bin/*.apk 2>/dev/null | head -n 1 || true)"
echo
echo "============================================================"
echo "Android build complete"
echo "============================================================"
if [[ -n "$latest_apk" ]]; then
  echo "APK: $latest_apk"
else
  echo "Build finished but no APK was found in bin/."
fi
