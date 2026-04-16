#!/bin/bash
set -euo pipefail

FLASK_URL=${FLASK_URL:-http://127.0.0.1:15001}
FASTAPI_URL=${FASTAPI_URL:-http://127.0.0.1:15002}

python tests/parity/parity_harness.py \
  --flask-url "$FLASK_URL" \
  --fastapi-url "$FASTAPI_URL" \
  --allowlist tests/parity/allowlist.json \
  --report-out tests/parity/last_report.json

python tests/parity/check_determinism.py \
  --url "$FASTAPI_URL" \
  --cases tests/parity/determinism_cases.json \
  --report-out tests/parity/determinism_report.json
