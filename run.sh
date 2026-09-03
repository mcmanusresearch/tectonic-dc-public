#!/usr/bin/env bash
# Full reproduction, start to finish. No credentials, no account, no API key.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install -q -r requirements.txt
python3 src/01_inventory.py
python3 src/02_extract.py
python3 src/03_onset.py
python3 src/04_chart.py
echo
echo "Done. Compare results/onset.csv against the table in README.md."
