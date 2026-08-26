#!/usr/bin/env bash
# Minimal end-to-end smoke: one chat round through the active model.
# Used as the per-milestone gate in design/datus-agent-cube-plan.md.
# Usage: scripts/smoke_chat.sh [prompt] [expected-substring]
set -euo pipefail

PROMPT="${1:-Answer with the digit only: what is one plus one?}"
EXPECTED="${2:-2}"
TIMEOUT="${SMOKE_TIMEOUT:-180}"
OUT="$(mktemp -t datus_smoke)"

# GNU coreutils `timeout` is not in a default macOS install; fall back to
# gtimeout (homeutils coreutils) or run without a wrapper.
TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"
run_with_timeout() {
  if [ -n "$TIMEOUT_BIN" ]; then "$TIMEOUT_BIN" "$TIMEOUT" "$@"; else "$@"; fi
}

cleanup() { rm -f "$OUT"; }
trap cleanup EXIT

if ! run_with_timeout datus -p "$PROMPT" >"$OUT" 2>&1; then
  echo "FAIL: datus -p exited non-zero (timeout ${TIMEOUT}s)"; tail -5 "$OUT"; exit 1
fi

if ! grep -q '"type":"usage"' "$OUT"; then
  echo "FAIL: no token usage reported — LLM round did not complete"; tail -5 "$OUT"; exit 1
fi

if grep -q 'rate_limit_error\|RateLimitError' "$OUT"; then
  echo "FAIL: rate limit error in output"; exit 1
fi

if ! grep -q "\"content\":\".*$EXPECTED" "$OUT"; then
  echo "FAIL: expected '$EXPECTED' not found in the answer"; grep '"type":"markdown"' "$OUT" | tail -1; exit 1
fi

echo "PASS: smoke chat completed"
grep -o '"requests":[0-9]*,"input_tokens":[0-9]*,"output_tokens":[0-9]*' "$OUT" | tail -1
