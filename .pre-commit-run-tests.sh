#!/usr/bin/env bash
# .pre-commit-run-tests.sh
# Run all three unit test suites. Called by the pre-push pre-commit hook.
# Exits non-zero if any suite fails; each suite's exit code is checked independently
# so all suites run before we report.
#
# NOTE: set -e is intentionally NOT used here. Each suite is run with the
# `|| FAILED=1` pattern so that a failing suite never aborts the script early —
# all three suites always run, and any failure is aggregated into FAILED.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAILED=0

echo "=== Running unit test suites (pre-push guard) ==="

echo ""
echo "--- [1/3] scripts (unittest discover) ---"
(cd "$ROOT/modules/gaming/mygamemaster/scripts" && python3 -m unittest discover -s tests) || FAILED=1

echo ""
echo "--- [2/3] hooks (test_hooks.py) ---"
(cd "$ROOT/modules/gaming/mygamemaster/hooks" && python3 test_hooks.py) || FAILED=1

echo ""
echo "--- [3/3] tts (test_tts.py) ---"
(cd "$ROOT/modules/gaming/mygamemaster-tts/tests" && python3 test_tts.py) || FAILED=1

echo ""
if [ $FAILED -ne 0 ]; then
  echo "=== RESULT: one or more test suites FAILED — push blocked ==="
  exit 1
fi

echo "=== RESULT: all test suites passed ==="
exit 0
