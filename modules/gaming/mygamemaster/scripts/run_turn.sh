#!/usr/bin/env bash
# run_turn.sh — Runs a game turn for a persistent NPC agent.
#
# Usage :
#   run_turn.sh <slug> --mode pnj|faction --campagne <chemin> "<scene context>"
#
# Pipeline :
#   1. build_brief.py <campagne> <pnj>        → identity brief
#   2. Concatenates brief + scene context      → message to send
#   3. hermes -p pnj-<slug> chat -Q -q "..." -c → NPC response (pure stdout)
#      If -c fails (first turn, no session) → retries without -c
#   4. Displays the formatted response 🎭/🎯/❓/🔒
#
# The -c flag resumes the existing session → the NPC remembers previous turns.
# The -Q flag suppresses the banner → stdout = pure response, capturable.
#
# Exit codes :
#   0 = response received
#   1 = error (NPC not found, brief failed, hermes unreachable)
#   2 = timeout / no response

set -euo pipefail

HERMES="${HERMES_BIN:-hermes}"
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_BRIEF="$SCRIPTS_DIR/build_brief.py"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

die() { echo -e "${RED}❌ $*${NC}" >&2; exit 1; }
ok()  { echo -e "${GREEN}✅ $*${NC}"; }
warn(){ echo -e "${YELLOW}⚠️  $*${NC}" >&2; }

usage() {
    cat <<EOF
Usage: $0 <slug> --mode pnj|faction --campagne <chemin> "<contexte>"

  slug         NPC/faction identifier (e.g.: barda, corneille)
  --mode       pnj (default) or faction
  --campagne   Path to the campaign folder (required)
  "<contexte>" Narrative scene context (required, in quotes)

Examples:
  $0 barda --mode pnj --campagne .hermes/mygamemaster/campaigns/mon-monde \\
    "The PCs enter your forge, covered in mud, and ask to have a blade repaired."
EOF
    exit 1
}

# ── Parse args ──────────────────────────────────────────────────────────
SLUG=""
MODE="pnj"
CAMPAGNE=""
CONTEXTE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode)     MODE="$2"; shift 2 ;;
        --campagne) CAMPAGNE="$2"; shift 2 ;;
        -h|--help)  usage ;;
        -*)         die "Unknown option: $1" ;;
        *)
            if [[ -z "$SLUG" ]]; then
                SLUG="$1"
            elif [[ -z "$CONTEXTE" ]]; then
                CONTEXTE="$1"
            else
                die "Too many arguments."
            fi
            shift
            ;;
    esac
done

[[ -z "$SLUG" ]]     && usage
[[ -z "$CAMPAGNE" ]] && die "--campagne is required"
[[ -z "$CONTEXTE" ]] && die "Scene context is required (last argument, in quotes)"

PROFILE="pnj-${SLUG}"
SKILL="mygamemaster-pnj"
[[ "$MODE" == "faction" ]] && PROFILE="faction-${SLUG}" && SKILL="mygamemaster-faction"

# ── Checks ──────────────────────────────────────────────────────────────
if ! command -v "$HERMES" &>/dev/null; then
    die "hermes not found. Set HERMES_BIN=..."
fi

if [[ ! -f "$BUILD_BRIEF" ]]; then
    die "build_brief.py not found: $BUILD_BRIEF"
fi

if [[ ! -d "$CAMPAGNE" ]]; then
    die "Campaign folder not found: $CAMPAGNE"
fi

# Check that the profile exists
if ! "$HERMES" profile list 2>/dev/null | grep -qw "$PROFILE"; then
    warn "Profile \"$PROFILE\" not found."
    echo "  → Run first: $(dirname "$0")/ensure_agent.sh $SLUG --mode $MODE --campagne $CAMPAGNE"
    exit 1
fi

# ── Step 1 — Build the brief ────────────────────────────────────────────
echo "📋 Building brief for $SLUG..." >&2

if [[ "$MODE" == "faction" ]]; then
    BRIEF=$(python3 "$BUILD_BRIEF" "$CAMPAGNE" --faction "$SLUG" 2>/dev/null) || \
        die "build_brief.py failed for faction \"$SLUG\""
else
    BRIEF=$(python3 "$BUILD_BRIEF" "$CAMPAGNE" "$SLUG" 2>/dev/null) || \
        die "build_brief.py failed for NPC \"$SLUG\""
fi

if [[ -z "$BRIEF" ]]; then
    die "Empty brief for \"$SLUG\" — check its sheet in npcs.json"
fi

ok "Brief built (${#BRIEF} characters)" >&2

# ── Step 2 — Assemble the message ───────────────────────────────────────
MESSAGE="$BRIEF

---
## 🎬 Scene Context (provided by the GM)

$CONTEXTE

---
Reply in the format 🎭 RP / 🎯 INTENTION / ❓ TO THE GM / 🔒 NOTES.
Reminder: you are **$SLUG**. You only know what your brief and this context tell you.
You have no access to the players — you reply TO THE GM, not to them."

# ── Step 3 — Call hermes (create-or-resume) ───────────────────────────
echo "🚀 Calling $PROFILE..." >&2

# First attempt: with -c (resume the existing session)
# If the NPC already has a session, -c resumes it → it remembers
# If it is the first turn (no session), -c fails → retry without -c
REPONSE=$("$HERMES" -p "$PROFILE" -s "$SKILL" chat -Q -q "$MESSAGE" -c 2>&1) || true

# Detect the "no session to continue" failure
if echo "$REPONSE" | grep -qi "no previous.*session.*continue\|no.*session.*found"; then
    warn "First turn detected — creating the session..."
    REPONSE=$("$HERMES" -p "$PROFILE" -s "$SKILL" chat -Q -q "$MESSAGE" 2>&1) || {
        RC=$?
        warn "hermes returned code $RC"
        if [[ -n "$REPONSE" ]]; then
            echo "$REPONSE" >&2
        fi
        exit $RC
    }
fi

if [[ -z "$REPONSE" ]]; then
    die "Empty response — the NPC said nothing (timeout? model error?)"
fi

# ── Step 4 — Display the response ──────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "🎭 $SLUG responds:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "$REPONSE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

exit 0
