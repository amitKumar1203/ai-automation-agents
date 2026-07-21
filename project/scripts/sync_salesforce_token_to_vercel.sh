#!/usr/bin/env bash
# Sync Salesforce refresh token from salesforce_token.json to Vercel and redeploy.
# Run AFTER: python3 -m integrations.salesforce_client login
# Do NOT run local refresh/tests before this script — Salesforce may rotate the token.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOKEN_FILE="$ROOT/salesforce_token.json"

if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "Missing $TOKEN_FILE"
  echo "Run: cd project && python3 -m integrations.salesforce_client login"
  exit 1
fi

read -r REFRESH < <(
  python3 - <<PY
import json
from pathlib import Path
data = json.loads(Path("$TOKEN_FILE").read_text(encoding="utf-8"))
print(data["refresh_token"])
PY
)
read -r INSTANCE < <(
  python3 - <<PY
import json
from pathlib import Path
data = json.loads(Path("$TOKEN_FILE").read_text(encoding="utf-8"))
print(data["instance_url"])
PY
)

if [[ -z "${REFRESH}" || -z "${INSTANCE}" ]]; then
  echo "Could not read refresh_token / instance_url from $TOKEN_FILE"
  exit 1
fi

cd "$ROOT"

echo "Updating SALESFORCE_REFRESH_TOKEN on Vercel (production)..."
printf '%s' "$REFRESH" | npx vercel env rm SALESFORCE_REFRESH_TOKEN production --yes 2>/dev/null || true
printf '%s' "$REFRESH" | npx vercel env add SALESFORCE_REFRESH_TOKEN production --force

echo "Updating SALESFORCE_INSTANCE_URL on Vercel (production)..."
printf '%s' "$INSTANCE" | npx vercel env rm SALESFORCE_INSTANCE_URL production --yes 2>/dev/null || true
printf '%s' "$INSTANCE" | npx vercel env add SALESFORCE_INSTANCE_URL production --force

echo "Redeploying API to production..."
npx vercel --prod --yes

echo ""
echo "Verify:"
echo "  curl https://ai-automation-agents-api.vercel.app/api/po-agent/run"
