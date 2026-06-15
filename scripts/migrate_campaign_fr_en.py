#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
migrate_campaign_fr_en.py — Migrate a MyGameMaster campaign from the OLD
(French) on-disk layout to the NEW (English) layout expected by the renamed
engine.

WHAT IT DOES
------------
The big "full FR->EN" refactor renamed, across the whole project:
  * the data tree      data/mj-tonnerre/campagnes/   -> data/mygamemaster/campaigns/
  * the seed file      data/mj-tonnerre/base_items.yaml -> data/mygamemaster/base_items.yaml
  * per-campaign files  monde.json     -> world.json
                        pnj.json       -> npcs.json
                        acteurs.json   -> actors.json
                        evenements.json-> events.json
  * per-campaign dir    personnages/   -> characters/
  * every JSON *dict KEY* (recursively, at any depth) per the glossary below.

It does NOT translate VALUES. Your real campaigns' French prose (descriptions,
narrative text, notes...) is preserved verbatim. ID-prefixed values such as
"acteur:mosswick", "lieu:thornwick/...", "faction:pale-court", "evt:...",
"rel:..." and unit values such as "unite": "jour" stay exactly as they are.
The script renames KEYS only.

Everything else in a campaign directory (geo.json, collecte.csv, sessions/,
outils/, images/, .banquier/, *.md, .gitignore, ...) is moved as-is. Note that
JSON files anywhere under the campaign (including sessions/*.json) still get the
recursive KEY rename, because the session schema also uses the glossary.

THE GLOSSARY (confirmed key-for-key against the committed refactor example:
  OLD  data/mj-tonnerre/campagnes/example-mistfall/   (branch main)
  NEW  data/mygamemaster/campaigns/example-mistfall/  (branch chore/integrate-all-and-rename)
)

  systeme              -> system
  univers              -> universe
  regles               -> rules
  etat_global          -> global_state
  lieux                -> locations
  deplacements         -> movements
  nom                  -> name
  nom_joueur           -> player_name
  nom_perso            -> character_name
  notes_perso          -> personal_notes
  classe               -> class_
  niveau               -> level
  niveau_suivant       -> next_level
  historique           -> history
  equipement           -> equipment
  inventaire           -> inventory
  competences          -> skills
  sorts                -> spells
  sante                -> health
  pv_max               -> hp_max
  pv_actuels           -> hp_current
  blessures            -> wounds
  etats                -> conditions
  temps                -> time
  ton                  -> tone
  mj                   -> gm
  mj_discord_id        -> gm_discord_id
  secrets_mj           -> gm_secrets
  verbosite            -> verbosity
  faits_etablis        -> established_facts
  acteurs              -> actors
  acteur               -> actor            (KEY only; the VALUE "acteur:..." is left untouched)
  evenements           -> events
  evenement            -> event            (KEY only; the VALUE "evt:..." is left untouched)
  pnj                  -> npcs
  trajectoire          -> trajectory
  chronologie          -> timeline
  suivi                -> tracking
  voyage               -> travel
  meteo                -> weather
  lieux_visites        -> visited_locations
  pnj_rencontres       -> npcs_met
  hypotheses_mj        -> gm_hypotheses
  objectifs            -> goals
  objectif_court_terme -> short_term_goals
  objectif_long_terme  -> long_term_goals
  objectifs_ct         -> short_term_goals
  objectifs_lt         -> long_term_goals
  tracabilite          -> traceability
  temporalite          -> temporality
  pnj_faction_vivants  -> living_npcs_factions
  joie                 -> joy
  confiance            -> trust
  peur                 -> fear
  colere               -> anger
  tristesse            -> sadness
  raison               -> reason
  rythme               -> pacing
  ton_aime             -> tone_likes
  ton_evite            -> tone_dislikes
  verbosite_combat     -> combat_verbosity
  limites_contenu      -> content_boundaries
  aime_etre_trompe     -> enjoys_deception
  heure_debut          -> start_hour
  heure_fin            -> end_hour
  heure_courante       -> current_hour
  jour_courant         -> current_day
  heure                -> hour             (e.g. meta.time.tracking.heure)
  jour                 -> day              (e.g. meta.time.tracking.jour)

  Composite / token patterns (the token "inventaire" inside an otherwise-free
  key is rewritten to "inventory", preserving the rest of the key):
       <x>_inventaire        -> <x>_inventory
       inventaire_<x>        -> inventory_<x>
       <x>_inventaire_<y>    -> <x>_inventory_<y>   (e.g. oryn_inventaire_note -> oryn_inventory_note)

KEYS THAT INTENTIONALLY STAY FRENCH (the refactor kept these — do NOT rename):
  lieu (as a KEY), vers, ressources, relations, motivations, situation, plan,
  localisation, localisation_id, but_long_terme, majeur, echeance,
  echeance_source, echeance_jours, significativite, visible_par_pj,
  preconditions, consequence_attendue, consequence_effets, unite, delai_ut,
  poids, intensite, description_narrative, ancrage, aretes, altitude, parent,
  duree_min, regime, gouvernance, renouvellement, procedure, verification,
  principe, magie_fae, factions, faction, faction_actions_horloge,
  quete_active, artefacts_connus, regions, ambiance, crunch, combat, stats,
  resolution, nat1, nat20, relation_niveau, attitude, role, etat_fin,
  jalons_temporels, langue, etat, temperament, note, secrets, temps_jeu,
  oryn_pv, sable_pv, ...  (anything not in the glossary above is preserved).

USAGE
-----
  # One campaign (dry-run by default — prints what would change, writes nothing):
  python3 scripts/migrate_campaign_fr_en.py data/mj-tonnerre/campagnes/la-naissance-dun-roi

  # Apply it (a backup is always made first):
  python3 scripts/migrate_campaign_fr_en.py data/mj-tonnerre/campagnes/la-naissance-dun-roi --apply

  # Migrate the WHOLE old tree (every campaign + base_items.yaml) into the new tree:
  python3 scripts/migrate_campaign_fr_en.py --all data/mj-tonnerre
  python3 scripts/migrate_campaign_fr_en.py --all data/mj-tonnerre --apply

  # Choose where backups go:
  python3 scripts/migrate_campaign_fr_en.py <campaign_dir> --apply --backup-dir /tmp/hermes-bak

SAFETY
------
  * Default mode is --dry-run: nothing is written.
  * --apply always makes a full backup of the source first
    (default: "<dir>.bak-fr-en", or --backup-dir).
  * Every written JSON is re-parsed with json.load to confirm validity.
  * Idempotent-ish: re-running on already-migrated data is a safe no-op
    (already-English keys/filenames are left alone).

AFTER MIGRATING — you ALSO need to:
  * Re-deploy. The Ansible templates now point at /opt/data/mygamemaster/...
    and use MGM_* environment variables.
  * games.yml `data_dir` values are UNCHANGED: the campaign FOLDER names stay
    the same (e.g. "la-naissance-dun-roi"); only the parent dir
    (campagnes -> campaigns, mj-tonnerre -> mygamemaster), the filenames, and
    the JSON keys change. You do not need to edit games.yml.
"""

import argparse
import json
import os
import re
import shutil
import sys

# --------------------------------------------------------------------------- #
# Glossary
# --------------------------------------------------------------------------- #

# Exact, whole-key renames. KEYS ONLY — values are never touched.
KEY_MAP = {
    "systeme": "system",
    "univers": "universe",
    "regles": "rules",
    "etat_global": "global_state",
    "lieux": "locations",
    "deplacements": "movements",
    "nom": "name",
    "nom_joueur": "player_name",
    "nom_perso": "character_name",
    "notes_perso": "personal_notes",
    "classe": "class_",
    "niveau": "level",
    "niveau_suivant": "next_level",
    "historique": "history",
    "equipement": "equipment",
    "inventaire": "inventory",
    "competences": "skills",
    "sorts": "spells",
    "sante": "health",
    "pv_max": "hp_max",
    "pv_actuels": "hp_current",
    "blessures": "wounds",
    "etats": "conditions",
    "temps": "time",
    "ton": "tone",
    "mj": "gm",
    "mj_discord_id": "gm_discord_id",
    "secrets_mj": "gm_secrets",
    "verbosite": "verbosity",
    "faits_etablis": "established_facts",
    "acteurs": "actors",
    "acteur": "actor",
    "evenements": "events",
    "evenement": "event",
    "pnj": "npcs",
    "trajectoire": "trajectory",
    "chronologie": "timeline",
    "suivi": "tracking",
    "voyage": "travel",
    "meteo": "weather",
    "lieux_visites": "visited_locations",
    "pnj_rencontres": "npcs_met",
    "hypotheses_mj": "gm_hypotheses",
    "objectifs": "goals",
    "objectif_court_terme": "short_term_goals",
    "objectif_long_terme": "long_term_goals",
    "objectifs_ct": "short_term_goals",
    "objectifs_lt": "long_term_goals",
    "tracabilite": "traceability",
    "temporalite": "temporality",
    "pnj_faction_vivants": "living_npcs_factions",
    "joie": "joy",
    "confiance": "trust",
    "peur": "fear",
    "colere": "anger",
    "tristesse": "sadness",
    "raison": "reason",
    "rythme": "pacing",
    "ton_aime": "tone_likes",
    "ton_evite": "tone_dislikes",
    "verbosite_combat": "combat_verbosity",
    "limites_contenu": "content_boundaries",
    "aime_etre_trompe": "enjoys_deception",
    "heure_debut": "start_hour",
    "heure_fin": "end_hour",
    "heure_courante": "current_hour",
    "jour_courant": "current_day",
    "heure": "hour",
    "jour": "day",
}

# Token-pattern: rewrite the standalone token "inventaire" to "inventory"
# inside an otherwise-free composite key (e.g. "oryn_inventaire_note" ->
# "oryn_inventory_note"). Word boundaries are underscores / start / end.
_INVENTAIRE_TOKEN = re.compile(r"(?<![a-z])inventaire(?![a-z])")

# File renames (basename -> basename) for files living directly in a campaign.
FILE_MAP = {
    "monde.json": "world.json",
    "pnj.json": "npcs.json",
    "acteurs.json": "actors.json",
    "evenements.json": "events.json",
}

# Directory renames (basename -> basename).
DIR_MAP = {
    "personnages": "characters",
}

# Data-root renames (for --all).
DATA_ROOT_BASENAME_OLD = "mj-tonnerre"
DATA_ROOT_BASENAME_NEW = "mygamemaster"
CAMPAIGNS_DIR_OLD = "campagnes"
CAMPAIGNS_DIR_NEW = "campaigns"


# --------------------------------------------------------------------------- #
# Key renaming
# --------------------------------------------------------------------------- #

def rename_key(key):
    """Return the migrated form of a single dict KEY (str)."""
    if not isinstance(key, str):
        return key
    if key in KEY_MAP:
        return KEY_MAP[key]
    # composite "inventaire" token pattern
    if "inventaire" in key:
        new = _INVENTAIRE_TOKEN.sub("inventory", key)
        if new != key:
            return new
    return key


def migrate_obj(obj):
    """Recursively rename dict KEYS in a JSON-like structure. Values untouched."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            out[rename_key(k)] = migrate_obj(v)
        return out
    if isinstance(obj, list):
        return [migrate_obj(it) for it in obj]
    # scalar value — left exactly as-is (never translated)
    return obj


# --------------------------------------------------------------------------- #
# Filesystem helpers
# --------------------------------------------------------------------------- #

def log(msg):
    print(msg, flush=True)


def make_backup(src_dir, backup_dir, dry_run):
    """Copy src_dir tree to backup_dir before mutating. Returns backup path."""
    if dry_run:
        log("  [dry-run] would back up %s -> %s" % (src_dir, backup_dir))
        return backup_dir
    if os.path.exists(backup_dir):
        raise SystemExit(
            "ERROR: backup target already exists: %s\n"
            "       Remove it or pass a different --backup-dir." % backup_dir
        )
    shutil.copytree(src_dir, backup_dir, symlinks=True)
    log("  backed up %s -> %s" % (src_dir, backup_dir))
    return backup_dir


def migrate_json_file(path, dry_run):
    """Rewrite a JSON file in place with migrated keys. Re-validates on write."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        log("  WARNING: %s is not valid JSON (%s) — left untouched" % (path, exc))
        return False
    migrated = migrate_obj(data)
    if migrated == data:
        log("    keys: no change  (%s)" % os.path.basename(path))
        return False
    if dry_run:
        log("    keys: would migrate  (%s)" % os.path.basename(path))
        return True
    text = json.dumps(migrated, ensure_ascii=False, indent=2) + "\n"
    # validate round-trip before clobbering
    json.loads(text)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    # final re-validation from disk
    with open(path, "r", encoding="utf-8") as fh:
        json.load(fh)
    log("    keys: migrated  (%s)" % os.path.basename(path))
    return True


def rename_dirs_in_place(root, dry_run):
    """Rename DIR_MAP directories that sit directly under `root`."""
    for old, new in DIR_MAP.items():
        old_p = os.path.join(root, old)
        new_p = os.path.join(root, new)
        if os.path.isdir(old_p):
            if os.path.exists(new_p):
                log("    dir: %s already exists, skipping rename of %s" % (new, old))
                continue
            if dry_run:
                log("    dir: would rename %s/ -> %s/" % (old, new))
            else:
                os.rename(old_p, new_p)
                log("    dir: renamed %s/ -> %s/" % (old, new))


def rename_files_in_dir(directory, dry_run):
    """Rename FILE_MAP files that sit directly in `directory`."""
    for old, new in FILE_MAP.items():
        old_p = os.path.join(directory, old)
        new_p = os.path.join(directory, new)
        if os.path.isfile(old_p):
            if os.path.exists(new_p):
                log("    file: %s already exists, skipping rename of %s" % (new, old))
                continue
            if dry_run:
                log("    file: would rename %s -> %s" % (old, new))
            else:
                os.rename(old_p, new_p)
                log("    file: renamed %s -> %s" % (old, new))


def all_json_files(root):
    """Yield every *.json path under `root` (after dir/file renames)."""
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith(".json"):
                yield os.path.join(dirpath, fn)


# --------------------------------------------------------------------------- #
# Campaign migration (in place: the directory keeps its location)
# --------------------------------------------------------------------------- #

def migrate_campaign_inplace(campaign_dir, dry_run, backup_dir=None):
    """Migrate a single campaign directory in place (files/dirs/keys)."""
    campaign_dir = os.path.abspath(campaign_dir)
    if not os.path.isdir(campaign_dir):
        raise SystemExit("ERROR: not a directory: %s" % campaign_dir)

    log("Campaign: %s" % campaign_dir)

    if not dry_run:
        bdir = backup_dir or (campaign_dir.rstrip(os.sep) + ".bak-fr-en")
        make_backup(campaign_dir, bdir, dry_run=False)
    elif backup_dir:
        log("  [dry-run] would back up to %s" % backup_dir)
    else:
        log("  [dry-run] would back up to %s.bak-fr-en" % campaign_dir)

    # 1) rename top-level dirs (personnages -> characters) then files
    rename_dirs_in_place(campaign_dir, dry_run)
    rename_files_in_dir(campaign_dir, dry_run)

    # 2) migrate KEYS in every JSON file (top-level + sessions/ + anything else).
    #    In dry-run the renames above did not happen, so walk old names too.
    json_paths = set(all_json_files(campaign_dir))
    if dry_run:
        # also include the would-be-renamed files under their current names
        for old in FILE_MAP:
            p = os.path.join(campaign_dir, old)
            if os.path.isfile(p):
                json_paths.add(p)
    changed = 0
    for p in sorted(json_paths):
        if migrate_json_file(p, dry_run):
            changed += 1
    log("  JSON files with key changes: %d" % changed)
    log("")


# --------------------------------------------------------------------------- #
# --all : migrate the whole old data tree into the new one
# --------------------------------------------------------------------------- #

def migrate_all(data_root, dry_run, backup_dir=None):
    """Migrate data/mj-tonnerre -> data/mygamemaster (all campaigns + base_items)."""
    data_root = os.path.abspath(data_root)
    if not os.path.isdir(data_root):
        raise SystemExit("ERROR: not a directory: %s" % data_root)

    parent = os.path.dirname(data_root)
    base = os.path.basename(data_root.rstrip(os.sep))
    if base == DATA_ROOT_BASENAME_OLD:
        new_root = os.path.join(parent, DATA_ROOT_BASENAME_NEW)
    elif base == DATA_ROOT_BASENAME_NEW:
        new_root = data_root  # already new
    else:
        # unknown name: migrate into a sibling "<base>-mygamemaster"
        new_root = data_root.rstrip(os.sep) + "-" + DATA_ROOT_BASENAME_NEW
    log("Data root: %s  ->  %s" % (data_root, new_root))

    old_campaigns = os.path.join(data_root, CAMPAIGNS_DIR_OLD)
    if not os.path.isdir(old_campaigns):
        old_campaigns = os.path.join(data_root, CAMPAIGNS_DIR_NEW)
    new_campaigns = os.path.join(new_root, CAMPAIGNS_DIR_NEW)

    # Back up the entire old data root once.
    if not dry_run:
        bdir = backup_dir or (data_root.rstrip(os.sep) + ".bak-fr-en")
        make_backup(data_root, bdir, dry_run=False)
        os.makedirs(new_campaigns, exist_ok=True)
    else:
        log("  [dry-run] would back up %s -> %s" %
            (data_root, backup_dir or (data_root + ".bak-fr-en")))
        log("  [dry-run] would create %s" % new_campaigns)

    # base_items.yaml — moved as-is (content is unchanged by the refactor).
    old_bi = os.path.join(data_root, "base_items.yaml")
    new_bi = os.path.join(new_root, "base_items.yaml")
    if os.path.isfile(old_bi):
        if dry_run:
            log("  [dry-run] would copy base_items.yaml -> %s" % new_bi)
        else:
            shutil.copy2(old_bi, new_bi)
            log("  copied base_items.yaml -> %s" % new_bi)

    # Each campaign: copy folder (same folder name) into new tree, then migrate.
    if not os.path.isdir(old_campaigns):
        log("  no campaigns dir found under %s" % data_root)
        return
    for entry in sorted(os.listdir(old_campaigns)):
        src = os.path.join(old_campaigns, entry)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(new_campaigns, entry)
        log("--")
        if dry_run:
            log("Campaign: %s  ->  %s  [dry-run]" % (src, dst))
            # run a dry-run pass on the SOURCE so the user sees per-file changes
            _dry_report_campaign(src)
            continue
        if os.path.exists(dst):
            log("  %s already exists in new tree — migrating it in place" % dst)
        else:
            shutil.copytree(src, dst, symlinks=True)
            log("  copied %s -> %s" % (src, dst))
        # migrate the COPY in place; backup already taken at data-root level
        migrate_campaign_inplace(dst, dry_run=False, backup_dir=_NO_BACKUP)


# Sentinel: skip per-campaign backup (the whole tree was already backed up).
_NO_BACKUP = "__already_backed_up__"


def _dry_report_campaign(src):
    """Dry-run report for a campaign without touching anything (for --all)."""
    rename_dirs_in_place(src, dry_run=True)
    rename_files_in_dir(src, dry_run=True)
    json_paths = set(all_json_files(src))
    for old in FILE_MAP:
        p = os.path.join(src, old)
        if os.path.isfile(p):
            json_paths.add(p)
    changed = 0
    for p in sorted(json_paths):
        if migrate_json_file(p, dry_run=True):
            changed += 1
    log("  JSON files that would change: %d" % changed)


# Re-bind make_backup for the per-campaign sentinel case.
_orig_make_backup = make_backup


def make_backup(src_dir, backup_dir, dry_run):  # noqa: F811  (intentional wrap)
    if backup_dir == _NO_BACKUP:
        return None
    return _orig_make_backup(src_dir, backup_dir, dry_run)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser():
    p = argparse.ArgumentParser(
        prog="migrate_campaign_fr_en.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Migrate a MyGameMaster campaign from the OLD French layout\n"
            "(data/mj-tonnerre/campagnes/<slug>/, monde.json/pnj.json/...,\n"
            "French JSON keys) to the NEW English layout\n"
            "(data/mygamemaster/campaigns/<slug>/, world.json/npcs.json/...,\n"
            "English JSON keys). Renames files, dirs and dict KEYS only — never\n"
            "translates values (French prose and ID-prefixed values are kept)."
        ),
        epilog=(
            "Examples:\n"
            "  # dry-run one campaign (writes nothing):\n"
            "  %(prog)s data/mj-tonnerre/campagnes/la-naissance-dun-roi\n"
            "  # apply it (backup made first):\n"
            "  %(prog)s data/mj-tonnerre/campagnes/la-naissance-dun-roi --apply\n"
            "  # migrate the whole old tree into data/mygamemaster/:\n"
            "  %(prog)s --all data/mj-tonnerre --apply\n\n"
            "After applying you must also re-deploy (Ansible now uses\n"
            "/opt/data/mygamemaster/... and MGM_* env). games.yml data_dir values\n"
            "are unchanged: folder names stay the same."
        ),
    )
    p.add_argument(
        "campaign_dir", nargs="?",
        help="Path to ONE campaign directory to migrate in place "
             "(e.g. data/mj-tonnerre/campagnes/la-naissance-dun-roi).",
    )
    p.add_argument(
        "--all", dest="all_root", metavar="DATA_ROOT",
        help="Migrate the WHOLE old data tree (e.g. data/mj-tonnerre): every "
             "campaign under campagnes/ plus base_items.yaml, into "
             "data/mygamemaster/.",
    )
    p.add_argument(
        "--apply", action="store_true",
        help="Actually write changes. Without this flag the tool runs in "
             "--dry-run mode and only prints what it would do.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Explicitly request dry-run (this is the default).",
    )
    p.add_argument(
        "--backup-dir", metavar="DIR",
        help="Where to put the backup of the source before applying "
             "(default: '<source>.bak-fr-en').",
    )
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if not args.campaign_dir and not args.all_root:
        build_parser().print_help()
        raise SystemExit("\nERROR: give a <campaign_dir> or use --all DATA_ROOT.")
    if args.campaign_dir and args.all_root:
        raise SystemExit("ERROR: use either <campaign_dir> OR --all, not both.")

    dry_run = not args.apply  # --dry-run is the default; --apply turns it off
    mode = "DRY-RUN (no changes written)" if dry_run else "APPLY (writing changes)"
    log("=== migrate_campaign_fr_en.py — %s ===" % mode)
    if dry_run:
        log("    (re-run with --apply to actually migrate; a backup is made first)")
    log("")

    if args.all_root:
        migrate_all(args.all_root, dry_run=dry_run, backup_dir=args.backup_dir)
    else:
        migrate_campaign_inplace(
            args.campaign_dir, dry_run=dry_run, backup_dir=args.backup_dir
        )

    log("=== done (%s) ===" % ("dry-run" if dry_run else "applied"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
