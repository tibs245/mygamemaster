#!/usr/bin/env bash
# ensure_agent.sh — Provisions a Hermes profile for a persistent NPC agent.
#
# Usage:
#   ensure_agent.sh <slug> [--mode pnj|faction] [--campagne <path>]
#
# What it does:
#   1. Checks whether the profile already exists (hermes profile list)
#   2. If not → clones default → injects the NPC config (skills, toolsets, memory)
#   3. Verifies that the mygamemaster-npc (or -faction) skill is loaded
#   4. Displays a summary of the created/existing profile
#
# Exit codes:
#   0 = profile ready (created or already existing)
#   1 = error (missing slug, hermes unreachable, etc.)
#
# NPC memory: memory_char_limit=8000 (vs 2200 global) — modern models
# have windows ≥200k tokens, might as well take advantage of that.

set -euo pipefail

HERMES="${HERMES_BIN:-hermes}"
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPTS_DIR/../.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

die() { echo -e "${RED}❌ $*${NC}" >&2; exit 1; }
ok()  { echo -e "${GREEN}✅ $*${NC}"; }
warn(){ echo -e "${YELLOW}⚠️  $*${NC}"; }

usage() {
    cat <<EOF
Usage: $0 <slug> [--mode pnj|faction] [--campagne <path>]

  slug        Profile identifier (e.g.: barda, corneille)
  --mode      pnj (default) or faction
  --campagne  Path to the campaign folder (informational only)
EOF
    exit 1
}

# ── Parse args ──────────────────────────────────────────────────────────
SLUG=""
MODE="pnj"
CAMPAGNE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode)     MODE="$2"; shift 2 ;;
        --campagne) CAMPAGNE="$2"; shift 2 ;;
        -h|--help)  usage ;;
        -*)         die "Unknown option: $1" ;;
        *)          [[ -z "$SLUG" ]] && SLUG="$1" || die "Slug already provided: $SLUG" ; shift ;;
    esac
done

[[ -z "$SLUG" ]] && usage

PROFILE="pnj-${SLUG}"
[[ "$MODE" == "faction" ]] && PROFILE="faction-${SLUG}"

# ── Check that hermes is available ───────────────────────────────────────
if ! command -v "$HERMES" &>/dev/null; then
    warn "hermes not found in \$PATH. Searching in containers..."
    # Try typical locations
    for candidate in hermes /usr/local/bin/hermes /opt/hermes/bin/hermes; do
        if command -v "$candidate" &>/dev/null; then
            HERMES="$candidate"
            ok "hermes found: $HERMES"
            break
        fi
    done
    if ! command -v "$HERMES" &>/dev/null; then
        die "hermes not found. Install it or set HERMES_BIN=..."
    fi
fi

# ── List existing profiles ────────────────────────────────────────
echo "📋 Looking up profile \"$PROFILE\"..."
EXISTING=$("$HERMES" profile list 2>/dev/null || true)

if echo "$EXISTING" | grep -qw "$PROFILE"; then
    ok "Profile \"$PROFILE\" already exists."
    echo ""
    echo "━━━ Profile summary ━━━"
    "$HERMES" profile show "$PROFILE" 2>/dev/null || true
    echo "━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "ℹ️  To recreate it: hermes profile delete $PROFILE && $0 $SLUG --mode $MODE"
    exit 0
fi

# ── Create the profile from default ──────────────────────────────────────
echo "🔧 Creating profile \"$PROFILE\" (cloned from default)..."
"$HERMES" profile create "$PROFILE" --clone-from default 2>/dev/null || \
    die "Failed to create profile. Make sure 'default' exists."

ok "Profile created."

# ── Configure memory ──────────────────────────────────────────────
echo "🧠 Configuring memory (8000 characters)..."
"$HERMES" config set memory.memory_char_limit 8000 --profile "$PROFILE" 2>/dev/null || \
    warn "Unable to set memory_char_limit (may require manual edit of profiles/$PROFILE/config.yaml)"

# ── Configure skills ──────────────────────────────────────────────
SKILL_NAME="mygamemaster-npc"
[[ "$MODE" == "faction" ]] && SKILL_NAME="mygamemaster-faction"

echo "📚 Checking skill $SKILL_NAME..."
SKILL_PATH="$SKILL_DIR/gaming/$SKILL_NAME/SKILL.md"
if [[ -f "$SKILL_PATH" ]]; then
    ok "Skill found: $SKILL_PATH"
else
    warn "Skill $SKILL_NAME not found at $SKILL_PATH"
    warn "The profile will need to load the skill manually: hermes -p $PROFILE -s $SKILL_NAME"
fi

# ── Final summary ────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}✅ Profile \"$PROFILE\" ready.${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Slug      : $SLUG"
echo "  Profile   : $PROFILE"
echo "  Mode      : $MODE"
echo "  Skill     : $SKILL_NAME"
echo "  Memory    : 8000 characters"
echo ""
echo "To run a turn:"
echo "  $(dirname "$0")/run_turn.sh $SLUG --mode $MODE${CAMPAGNE:+ --campagne $CAMPAGNE} \"<scene context>\""
echo ""
echo "To test the profile manually:"
echo "  $HERMES -p $PROFILE -s $SKILL_NAME chat -q \"Who are you?\""
echo ""

# ── Quick check ─────────────────────────────────────────────────
if "$HERMES" profile show "$PROFILE" &>/dev/null; then
    ok "Final check OK — the profile is functional."
else
    warn "Final check failed — the profile exists but may be incomplete."
fi

exit 0
