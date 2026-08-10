#!/usr/bin/env bash
# Arca — zero-setup launcher (macOS / Linux)
# Double-click or run: ./start.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Arca"

# 1) Locate Python 3.10+
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python 3.10+ is required but was not found." >&2
  exit 1
fi

# 2) Create the virtual environment once
if [ ! -d ".venv" ]; then
  echo "==> Creating virtual environment (.venv)"
  # --system-site-packages exposes the distro's python3-gi / GTK bindings,
  # which PyWebView needs for the native window on Linux.
  "$PY" -m venv --system-site-packages .venv || "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 3) Install Python dependencies
python -m pip install --quiet --disable-pip-version-check -r requirements.txt

# 4) Build the frontend when Node.js is available and the bundle is stale
if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
  (
    cd ui/web
    if [ ! -f dist/index.html ] \
      || find src index.html package.json package-lock.json \
        -newer dist/index.html -print -quit 2>/dev/null | grep -q .; then
      echo "==> Building frontend"
      npm install --no-audit --no-fund --silent
      npm run build
    fi
  )
else
  if [ ! -f ui/web/dist/index.html ]; then
    echo "WARNING: Node.js not found and no prebuilt frontend exists." >&2
    echo "         The UI will not load. Install Node.js or build ui/web manually." >&2
  fi
fi

echo "==> Starting Arca"
exec python run.py
