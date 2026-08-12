#!/usr/bin/env bash
set -euo pipefail

python -m pip_audit -r requirements.txt
if [ -f frontend/package-lock.json ]; then
  npm --prefix frontend audit --omit=dev
fi
