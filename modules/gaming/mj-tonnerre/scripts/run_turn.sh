#!/usr/bin/env bash
# run_turn.sh — Runs a game turn for a persistent NPC agent.
#
# Usage :
#   run_turn.sh <slug> --mode pnj|faction --campagne <chemin> "<contexte de scène>"
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

  slug         Identifiant du PNJ/faction (ex: barda, corneille)
  --mode       pnj (défaut) ou faction
  --campagne   Chemin du dossier de campagne (obligatoire)
  "<contexte>" Contexte narratif de la scène (obligatoire, entre guillemets)

Exemples :
  $0 barda --mode pnj --campagne .hermes/mj-tonnerre/campagnes/mon-monde \\
    "Les PJ entrent dans ta forge, couverts de boue, et demandent à réparer une lame."
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
        -*)         die "Option inconnue : $1" ;;
        *)
            if [[ -z "$SLUG" ]]; then
                SLUG="$1"
            elif [[ -z "$CONTEXTE" ]]; then
                CONTEXTE="$1"
            else
                die "Trop d'arguments."
            fi
            shift
            ;;
    esac
done

[[ -z "$SLUG" ]]     && usage
[[ -z "$CAMPAGNE" ]] && die "--campagne est obligatoire"
[[ -z "$CONTEXTE" ]] && die "Contexte de scène obligatoire (dernier argument entre guillemets)"

PROFILE="pnj-${SLUG}"
SKILL="mj-tonnerre-pnj"
[[ "$MODE" == "faction" ]] && PROFILE="faction-${SLUG}" && SKILL="mj-tonnerre-faction"

# ── Checks ──────────────────────────────────────────────────────────────
if ! command -v "$HERMES" &>/dev/null; then
    die "hermes introuvable. Passe HERMES_BIN=..."
fi

if [[ ! -f "$BUILD_BRIEF" ]]; then
    die "build_brief.py introuvable : $BUILD_BRIEF"
fi

if [[ ! -d "$CAMPAGNE" ]]; then
    die "Dossier campagne introuvable : $CAMPAGNE"
fi

# Check that the profile exists
if ! "$HERMES" profile list 2>/dev/null | grep -qw "$PROFILE"; then
    warn "Profil \"$PROFILE\" introuvable."
    echo "  → Lance d'abord : $(dirname "$0")/ensure_agent.sh $SLUG --mode $MODE --campagne $CAMPAGNE"
    exit 1
fi

# ── Step 1 — Build the brief ────────────────────────────────────────────
echo "📋 Construction du brief pour $SLUG..." >&2

if [[ "$MODE" == "faction" ]]; then
    BRIEF=$(python3 "$BUILD_BRIEF" "$CAMPAGNE" --faction "$SLUG" 2>/dev/null) || \
        die "build_brief.py a échoué pour la faction \"$SLUG\""
else
    BRIEF=$(python3 "$BUILD_BRIEF" "$CAMPAGNE" "$SLUG" 2>/dev/null) || \
        die "build_brief.py a échoué pour le PNJ \"$SLUG\""
fi

if [[ -z "$BRIEF" ]]; then
    die "Brief vide pour \"$SLUG\" — vérifie sa fiche dans pnj.json"
fi

ok "Brief construit (${#BRIEF} caractères)" >&2

# ── Step 2 — Assemble the message ───────────────────────────────────────
MESSAGE="$BRIEF

---
## 🎬 Contexte de scène (donné par le MJ)

$CONTEXTE

---
Réponds au format 🎭 RP / 🎯 INTENTION / ❓ AU MJ / 🔒 NOTES.
Rappel : tu es **$SLUG**. Tu ne sais que ce que ton brief et ce contexte te disent.
Tu n'as pas accès aux joueurs — tu réponds AU MJ, pas à eux."

# ── Step 3 — Call hermes (create-or-resume) ───────────────────────────
echo "🚀 Appel de $PROFILE..." >&2

# First attempt: with -c (resume the existing session)
# If the NPC already has a session, -c resumes it → it remembers
# If it is the first turn (no session), -c fails → retry without -c
REPONSE=$("$HERMES" -p "$PROFILE" -s "$SKILL" chat -Q -q "$MESSAGE" -c 2>&1) || true

# Detect the "no session to continue" failure
if echo "$REPONSE" | grep -qi "no previous.*session.*continue\|no.*session.*found"; then
    warn "Premier tour détecté — création de la session..."
    REPONSE=$("$HERMES" -p "$PROFILE" -s "$SKILL" chat -Q -q "$MESSAGE" 2>&1) || {
        RC=$?
        warn "hermes a retourné le code $RC"
        if [[ -n "$REPONSE" ]]; then
            echo "$REPONSE" >&2
        fi
        exit $RC
    }
fi

if [[ -z "$REPONSE" ]]; then
    die "Réponse vide — le PNJ n'a rien dit (timeout ? erreur modèle ?)"
fi

# ── Step 4 — Display the response ──────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "🎭 $SLUG répond :"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "$REPONSE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

exit 0
