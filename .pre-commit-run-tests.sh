#!/usr/bin/env bash
# .pre-commit-run-tests.sh
# Run all three unit test suites. Called by the pre-push pre-commit hook.
# Exits non-zero if any suite fails; each suite's exit code is checked independently
# so all suites run before we report.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAILED=0

echo "=== Running unit test suites (pre-push guard) ==="

echo ""
echo "--- [1/3] scripts (unittest discover) ---"
(cd "$ROOT/modules/gaming/mj-tonnerre/scripts" && python3 -m unittest discover -s tests)
RC=$?
if [ $RC -ne 0 ]; then
  echo "FAILED: scripts test suite (exit $RC)"
  FAILED=1
fi

echo ""
echo "--- [2/3] hooks (test_hooks.py) ---"
(cd "$ROOT/modules/gaming/mj-tonnerre/hooks" && python3 test_hooks.py)
RC=$?
if [ $RC -ne 0 ]; then
  echo "FAILED: hooks test suite (exit $RC)"
  FAILED=1
fi

echo ""
echo "--- [3/3] tts (test_tts.py) ---"
(cd "$ROOT/modules/gaming/mj-tonnerre-tts/tests" && python3 test_tts.py)
RC=$?
if [ $RC -ne 0 ]; then
  echo "FAILED: tts test suite (exit $RC)"
  FAILED=1
fi

echo ""
if [ $FAILED -ne 0 ]; then
  echo "=== RESULT: one or more test suites FAILED — push blocked ==="
  exit 1
fi

echo "=== RESULT: all test suites passed ==="
exit 0
