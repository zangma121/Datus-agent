#!/usr/bin/env bash
# Minimal end-to-end smoke: one chat round through the active model.
# Used as the per-milestone gate in design/datus-agent-cube-plan.md.
# Usage: scripts/smoke_chat.sh [prompt]
set -euo pipefail

PROMPT="${1:-用一句话回答：1+1等于几}"
TIMEOUT="${SMOKE_TIMEOUT:-180}"
OUT="$(mktemp -t datus_smoke)"

cleanup() { rm -f "$OUT"; }
trap cleanup EXIT

if ! timeout "$TIMEOUT" datus -p "$PROMPT" >"$OUT" 2>&1; then
  echo "FAIL: datus -p exited non-zero (timeout ${TIMEOUT}s)"; tail -5 "$OUT"; exit 1
fi

if ! grep -q '"type":"usage"' "$OUT"; then
  echo "FAIL: no token usage reported — LLM round did not complete"; tail -5 "$OUT"; exit 1
fi

if grep -q 'rate_limit_error\|RateLimitError' "$OUT"; then
  echo "FAIL: rate limit error in output"; exit 1
fi

echo "PASS: smoke chat completed"
grep -o '"requests":[0-9]*,"input_tokens":[0-9]*,"output_tokens":[0-9]*' "$OUT" | tail -1
