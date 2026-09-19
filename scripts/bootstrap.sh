#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m pip install -e ".[dev]"
python scripts/seed_locodes.py
python scripts/demo_reset.py
echo "Bootstrapped. Copy .env.example → .env"
