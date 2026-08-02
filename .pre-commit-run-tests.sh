#!/usr/bin/env bash
# .pre-commit-run-tests.sh
# Run all four unit test suites + the repo checks. Called by the pre-push hook.
# Exits non-zero if any suite fails; each suite's exit code is checked independently
# so all suites run before we report.
#
# NOTE: set -e is intentionally NOT used here. Each suite is run with the
# `|| FAILED=1` pattern so that a failing suite never aborts the script early —
# all suites always run, and any failure is aggregated into FAILED.
#
# Escape hatch: MGM_SKILL_SIZE_SKIP=1 downgrades the skill-size failure to a
# warning, so a live campaign can be unblocked without bypassing the hook.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAILED=0

echo "=== Running unit test suites (pre-push guard) ==="

echo ""
echo "--- [1/6] scripts (unittest discover) ---"
(cd "$ROOT/modules/gaming/mygamemaster/scripts" && python3 -m unittest discover -s tests) || FAILED=1

echo ""
echo "--- [2/6] hooks (test_hooks.py) ---"
(cd "$ROOT/modules/gaming/mygamemaster/hooks" && python3 test_hooks.py) || FAILED=1

echo ""
echo "--- [3/6] tts (test_tts.py) ---"
(cd "$ROOT/modules/gaming/mygamemaster-tts/tests" && python3 test_tts.py) || FAILED=1

echo ""
echo "--- [4/6] repo scripts (unittest discover) ---"
(cd "$ROOT/scripts" && python3 -m unittest discover -s tests) || FAILED=1

echo ""
echo "--- [5/6] file references ---"
(cd "$ROOT" && python3 scripts/check_references.py) || FAILED=1

echo ""
echo "--- [6/6] skill character budget ---"
(cd "$ROOT" && python3 scripts/check_skill_size.py) || FAILED=1

echo ""
if [ $FAILED -ne 0 ]; then
  echo "=== RESULT: a suite or a repo check FAILED — push blocked ==="
  exit 1
fi

echo "=== RESULT: all checks passed ==="
exit 0
