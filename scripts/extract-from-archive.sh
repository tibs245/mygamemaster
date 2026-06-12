#!/usr/bin/env bash
# ───────────────────────────────────────────────────────────────────────────
# extract-from-archive.sh — Extracts valuable content from archive_hermes/ into the repo.
#
# Idempotent: re-runnable without side effects (rsync --delete on targets).
# NEVER writes into archive_hermes/ (read-only source).
#
# Copies:
#   skills/gaming/mj-tonnerre*           -> modules/gaming/
#   home/.hermes/mj-tonnerre/base_items.yaml         -> data/mj-tonnerre/
#   home/.hermes/mj-tonnerre/campaigns/_template     -> data/mj-tonnerre/campaigns/
#   .hermes/mj-tonnerre/campaigns/<campagne>         -> data/mj-tonnerre/campaigns/
#
# Purged on copy: macOS ._* files, nested .git folders, __pycache__.
# ───────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCHIVE="${REPO_ROOT}/archive_hermes"
SRC_SKILLS="${ARCHIVE}/skills/gaming"
SRC_HOME_MJ="${ARCHIVE}/home/.hermes/mj-tonnerre"
SRC_CAMP="${ARCHIVE}/.hermes/mj-tonnerre/campaigns"

DST_MODULES="${REPO_ROOT}/modules/gaming"
DST_DATA="${REPO_ROOT}/data/mj-tonnerre"
DST_CAMP="${DST_DATA}/campaigns"

# Common exclusions (macOS artifacts, nested git, caches, runtime state)
EXCLUDES=(
  --exclude '._*'
  --exclude '.DS_Store'
  --exclude '.git/'
  --exclude '__pycache__/'
  --exclude '*.pyc'
)

if [[ ! -d "$ARCHIVE" ]]; then
  echo "✗ archive_hermes/ introuvable à ${ARCHIVE}" >&2
  exit 1
fi

echo "▶ Extraction depuis ${ARCHIVE}"
mkdir -p "$DST_MODULES" "$DST_CAMP"

# 1. Modules (mj-tonnerre* skills) ------------------------------------------
echo "  • modules/gaming/  ← skills/gaming/mj-tonnerre*"
for d in "${SRC_SKILLS}"/mj-tonnerre*/; do
  [[ -d "$d" ]] || continue
  name="$(basename "$d")"
  rsync -a --delete "${EXCLUDES[@]}" "$d" "${DST_MODULES}/${name}/"
done

# 2. Base items ----------------------------------------------------------
echo "  • data/mj-tonnerre/base_items.yaml"
if [[ -f "${SRC_HOME_MJ}/base_items.yaml" ]]; then
  rsync -a "${EXCLUDES[@]}" "${SRC_HOME_MJ}/base_items.yaml" "${DST_DATA}/base_items.yaml"
fi

# 3. Campaign template ---------------------------------------------------
echo "  • data/mj-tonnerre/campaigns/_template/"
if [[ -d "${SRC_HOME_MJ}/campaigns/_template" ]]; then
  rsync -a --delete "${EXCLUDES[@]}" "${SRC_HOME_MJ}/campaigns/_template/" "${DST_CAMP}/_template/"
fi

# 4. Campaigns (authoritative game data) -------------------------------
for c in "${SRC_CAMP}"/*/; do
  [[ -d "$c" ]] || continue
  name="$(basename "$c")"
  echo "  • data/mj-tonnerre/campaigns/${name}/"
  rsync -a --delete "${EXCLUDES[@]}" "$c" "${DST_CAMP}/${name}/"
done

# 5. Safety net: no residual ._* files ---------------------------------
find "${REPO_ROOT}/modules" "${REPO_ROOT}/data" -name '._*' -delete 2>/dev/null || true

echo "✓ Extraction terminée."
echo "  Modules : $(find "${DST_MODULES}" -maxdepth 1 -type d -name 'mj-tonnerre*' | wc -l | tr -d ' ') skills"
echo "  Campagnes : $(find "${DST_CAMP}" -maxdepth 1 -mindepth 1 -type d | wc -l | tr -d ' ') (dont _template)"
