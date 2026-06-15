#!/bin/sh
# install-hooks.sh — Installs the MJ Tonnerre pre-commit hook into a campaign.
#
# Finds the git repository that versions the given campaign, then copies the
# pre-commit hook into <repo>/.git/hooks/pre-commit, injecting the absolute
# path of the scripts folder (the one where this script lives).
#
# Usage:
#   ./install-hooks.sh <path/campaign>
#   ./install-hooks.sh <path/campaign> --force      # overwrite an existing hook
#
# Examples:
#   ./install-hooks.sh ../../../../.hermes/mygamemaster/campaigns/la-naissance-dun-roi
#   ./install-hooks.sh /absolute/path/to/campaign --force
#
# The installed hook blocks the commit if a JSON file is broken (see pre-commit.hook).
# Uninstall: delete <repo>/.git/hooks/pre-commit.

set -eu

CAMPAGNE="${1:-}"
FORCE=0
if [ "${2:-}" = "--force" ]; then
    FORCE=1
fi

if [ -z "$CAMPAGNE" ]; then
    echo "Usage : $0 <chemin/campagne> [--force]" >&2
    exit 2
fi

if [ ! -d "$CAMPAGNE" ]; then
    echo "❌ Campagne introuvable : $CAMPAGNE" >&2
    exit 2
fi

# Directory of this script = scripts folder (absolute path).
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK_TEMPLATE="$SCRIPTS_DIR/pre-commit.hook"

if [ ! -f "$HOOK_TEMPLATE" ]; then
    echo "❌ Modèle de hook introuvable : $HOOK_TEMPLATE" >&2
    exit 2
fi

# Find the git repository that versions the campaign.
GIT_DIR="$(cd "$CAMPAGNE" && git rev-parse --git-dir 2>/dev/null || true)"
if [ -z "$GIT_DIR" ]; then
    echo "❌ Aucun dépôt git ne versionne $CAMPAGNE." >&2
    echo "   Initialise-le (git init) ou indique une campagne déjà versionnée." >&2
    exit 2
fi
# Make GIT_DIR absolute (git returns it relative to the campaign's cwd).
GIT_DIR="$(cd "$CAMPAGNE" && cd "$GIT_DIR" && pwd)"

HOOKS_DIR="$GIT_DIR/hooks"
TARGET="$HOOKS_DIR/pre-commit"

mkdir -p "$HOOKS_DIR"

if [ -f "$TARGET" ] && [ "$FORCE" -ne 1 ]; then
    echo "⚠ Un hook pre-commit existe déjà : $TARGET" >&2
    echo "   Relance avec --force pour l'écraser." >&2
    exit 1
fi

# Inject the absolute path of the scripts folder into the hook.
# (sed uses '|' as separator to avoid conflicts with '/'.)
sed "s|__MGM_SCRIPTS_DIR__|$SCRIPTS_DIR|g" "$HOOK_TEMPLATE" > "$TARGET"
chmod +x "$TARGET"

echo "✅ Hook installé : $TARGET"
echo "   Dossier scripts injecté : $SCRIPTS_DIR"
echo "   Le commit sera REFUSÉ si un JSON de campagne est cassé."
echo "   Bypass d'urgence : MGM_SKIP_HOOK=1 git commit …"
