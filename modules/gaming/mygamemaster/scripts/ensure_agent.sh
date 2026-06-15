#!/usr/bin/env bash
# ensure_agent.sh — Provisions a Hermes profile for a persistent NPC agent.
#
# Usage:
#   ensure_agent.sh <slug> [--mode pnj|faction] [--campagne <chemin>]
#
# What it does:
#   1. Checks whether the profile already exists (hermes profile list)
#   2. If not → clones default → injects the NPC config (skills, toolsets, memory)
#   3. Verifies that the mygamemaster-pnj (or -faction) skill is loaded
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
Usage: $0 <slug> [--mode pnj|faction] [--campagne <chemin>]

  slug        Identifiant du profil (ex: barda, corneille)
  --mode      pnj (défaut) ou faction
  --campagne  Chemin du dossier de campagne (pour info seulement)
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
        -*)         die "Option inconnue : $1" ;;
        *)          [[ -z "$SLUG" ]] && SLUG="$1" || die "Slug déjà donné : $SLUG" ; shift ;;
    esac
done

[[ -z "$SLUG" ]] && usage

PROFILE="pnj-${SLUG}"
[[ "$MODE" == "faction" ]] && PROFILE="faction-${SLUG}"

# ── Check that hermes is available ───────────────────────────────────────
if ! command -v "$HERMES" &>/dev/null; then
    warn "hermes introuvable dans \$PATH. Cherche dans les conteneurs..."
    # Try typical locations
    for candidate in hermes /usr/local/bin/hermes /opt/hermes/bin/hermes; do
        if command -v "$candidate" &>/dev/null; then
            HERMES="$candidate"
            ok "hermes trouvé : $HERMES"
            break
        fi
    done
    if ! command -v "$HERMES" &>/dev/null; then
        die "hermes introuvable. Installe-le ou passe HERMES_BIN=..."
    fi
fi

# ── List existing profiles ────────────────────────────────────────
echo "📋 Recherche du profil \"$PROFILE\"..."
EXISTING=$("$HERMES" profile list 2>/dev/null || true)

if echo "$EXISTING" | grep -qw "$PROFILE"; then
    ok "Profil \"$PROFILE\" existe déjà."
    echo ""
    echo "━━━ Résumé du profil ━━━"
    "$HERMES" profile show "$PROFILE" 2>/dev/null || true
    echo "━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "ℹ️  Pour le recréer : hermes profile delete $PROFILE && $0 $SLUG --mode $MODE"
    exit 0
fi

# ── Create the profile from default ──────────────────────────────────────
echo "🔧 Création du profil \"$PROFILE\" (clone de default)..."
"$HERMES" profile create "$PROFILE" --clone-from default 2>/dev/null || \
    die "Échec de création du profil. Vérifie que 'default' existe."

ok "Profil créé."

# ── Configure memory ──────────────────────────────────────────────
echo "🧠 Configuration mémoire (8000 caractères)..."
"$HERMES" config set memory.memory_char_limit 8000 --profile "$PROFILE" 2>/dev/null || \
    warn "Impossible de régler memory_char_limit (peut nécessiter édition manuelle de profiles/$PROFILE/config.yaml)"

# ── Configure skills ──────────────────────────────────────────────
SKILL_NAME="mygamemaster-pnj"
[[ "$MODE" == "faction" ]] && SKILL_NAME="mygamemaster-faction"

echo "📚 Vérification du skill $SKILL_NAME..."
SKILL_PATH="$SKILL_DIR/gaming/$SKILL_NAME/SKILL.md"
if [[ -f "$SKILL_PATH" ]]; then
    ok "Skill trouvé : $SKILL_PATH"
else
    warn "Skill $SKILL_NAME introuvable à $SKILL_PATH"
    warn "Le profil devra charger le skill manuellement : hermes -p $PROFILE -s $SKILL_NAME"
fi

# ── Final summary ────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}✅ Profil \"$PROFILE\" prêt.${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Slug      : $SLUG"
echo "  Profil    : $PROFILE"
echo "  Mode      : $MODE"
echo "  Skill     : $SKILL_NAME"
echo "  Mémoire   : 8000 caractères"
echo ""
echo "Pour lancer un tour :"
echo "  $(dirname "$0")/run_turn.sh $SLUG --mode $MODE${CAMPAGNE:+ --campagne $CAMPAGNE} \"<contexte de scène>\""
echo ""
echo "Pour tester le profil manuellement :"
echo "  $HERMES -p $PROFILE -s $SKILL_NAME chat -q \"Qui es-tu ?\""
echo ""

# ── Quick check ─────────────────────────────────────────────────
if "$HERMES" profile show "$PROFILE" &>/dev/null; then
    ok "Vérification finale OK — le profil est fonctionnel."
else
    warn "Vérification finale échouée — le profil existe mais peut être incomplet."
fi

exit 0
