#!/usr/bin/env python3
"""
check_session.py — Checklist discrepancy detector for MJ Tonnerre (READ ONLY).

Scans the LAST session of a campaign (or a specific session) and reports
discrepancies against the closing checklist, WITHOUT correcting anything. Turns
the "mental consistency checklist" (forgettable by design) into a factual report.

Discrepancies detected:
  1. Location in sessions[].lieux_visites absent from universe.regions[].locations
  2. NPC in sessions[].pnj_rencontres with no entry in npcs.json
  3. Faction (global_state.factions) without objectif_court_terme OR objectif_long_terme
  4. Faction without an entry in global_state.faction_actions_horloge
  5. Clock deadline OVERDUE (day < current day) not marked RESOLVED
  6. Clock deadline not parsable (informational — the clock cannot be
     advanced by machine, cf. audit 2.3)
  7. Session marked played (has actions/locations) but heure_fin is empty

Compatible with BOTH campaign schemas:
  - npcs.json can be {"npcs": [...]} (C1) or a bare list [...] (C2)
  - locations/NPCs matched by NORMALIZED NAME (tolerates punctuation/accents/variants)

Usage:
  python3 check_session.py <path/campaign>
  python3 check_session.py <path/campaign> --session 4
  python3 check_session.py <path/campaign> --json

Exit codes:
  0  no blocking discrepancy (informational discrepancies ℹ may remain)
  1  at least one blocking discrepancy detected
  2  usage error (campaign/files not found)
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

# ─── Name normalization (tolerant matching) ───────────────────────────────────

def normaliser(nom: str) -> str:
    """Normalizes a name for comparison: lowercase, no accents, no
    punctuation, reduced spaces. « Blue Hall — beneath the Heart » and
    « Blue Hall (beneath the Heart) » become comparable on their common
    token core."""
    if not nom:
        return ""
    s = unicodedata.normalize("NFKD", nom)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)   # punctuation → space
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokens_significatifs(nom_norm: str) -> set[str]:
    """Tokens of a normalized name, excluding short/structural stop words."""
    vides = {"de", "du", "des", "le", "la", "les", "l", "un", "une", "au",
             "aux", "et", "sous", "sur", "vers", "n", "no", "numero"}
    return {t for t in nom_norm.split() if t not in vides and len(t) > 1}


def lieu_present(nom_lieu: str, lieux_connus_norm: list[str]) -> bool:
    """A visited location is "present" in the world if its normalized name
    matches exactly a known location, OR if all its significant tokens
    are included in those of a known location (or vice versa)."""
    cible = normaliser(nom_lieu)
    if not cible:
        return True  # empty name: nothing to say, no discrepancy
    if cible in lieux_connus_norm:
        return True
    toks_cible = tokens_significatifs(cible)
    if not toks_cible:
        return True
    for connu in lieux_connus_norm:
        toks_connu = tokens_significatifs(connu)
        if not toks_connu:
            continue
        # Inclusion in either direction = same location (spelling variant)
        if toks_cible <= toks_connu or toks_connu <= toks_cible:
            return True
    return False


def pnj_present(nom_pnj: str, pnj_connus_norm: list[str]) -> bool:
    """An encountered NPC is "present" if its normalized name matches (exact or
    by token inclusion) a known entry."""
    return lieu_present(nom_pnj, pnj_connus_norm)


# ─── Loading (tolerant of both schemas) ──────────────────────────────────────

def charger_json(chemin: Path):
    with open(chemin, "r", encoding="utf-8") as f:
        return json.load(f)


def extraire_liste_pnj(pnj_data) -> list[dict]:
    """Returns the NPC list regardless of schema:
    {"npcs": [...]} (C1) or bare list [...] (C2)."""
    if isinstance(pnj_data, dict):
        return pnj_data.get("npcs", [])
    if isinstance(pnj_data, list):
        return pnj_data
    return []


def collecter_lieux_universe(monde: dict) -> list[str]:
    """All location names (normalized) from universe.regions[].locations[]."""
    noms = []
    for region in monde.get("universe", {}).get("regions", []):
        if not isinstance(region, dict):
            continue
        for lieu in region.get("locations", []):
            if isinstance(lieu, dict) and lieu.get("name"):
                noms.append(normaliser(lieu["name"]))
        # The region name itself is an acceptable location
        if region.get("name"):
            noms.append(normaliser(region["name"]))
    return noms


def nom_de(item):
    """Extracts a name from an entry (dict with 'name'/'nom', or a bare string)."""
    if isinstance(item, dict):
        return item.get("name") or item.get("nom") or ""
    if isinstance(item, str):
        return item
    return ""


# ─── Clock deadlines ──────────────────────────────────────────────────────────

_RE_RESOLU = re.compile(r"r[ée]solu", re.IGNORECASE)
# « Day 4 », « Day 5-6 », « Day 7-10 » (game day references)
_RE_JOUR = re.compile(r"jour\s+(\d+)(?:\s*[-–]\s*(\d+))?", re.IGNORECASE)


def echeance_jour_min(echeance: str):
    """Extracts the FIRST day from a text deadline. Returns:
        int  → parsed day (lower bound if range « Day 5-6 »)
        None → not parsable (free-text deadline like « In 2-3 weeks »)
    """
    if not echeance:
        return None
    m = _RE_JOUR.search(echeance)
    if m:
        return int(m.group(1))
    return None


def echeance_infos(ech):
    """Normalizes a deadline (legacy string OR pinned object) into a dict:
        {texte, statut, due, unite}
      - statut : 'en_cours' | 'echue' | 'resolue' | None (None = legacy format)
      - due    : effective deadline day/UT (int) or None if not calculable
      - unite  : 'jour' | 'ut'
    Handles both formats without crashing (object format arrives after migration)."""
    if isinstance(ech, dict):
        texte = str(ech.get("texte", "") or "")
        ancre = ech.get("ancre")
        borne = ech.get("max") if ech.get("max") is not None else ech.get("min")
        due = (ancre + borne) if isinstance(ancre, int) and isinstance(borne, int) else None
        return {"texte": texte, "statut": ech.get("statut"),
                "due": due, "unite": ech.get("unite", "jour")}
    texte = str(ech or "")
    return {"texte": texte, "statut": None,
            "due": echeance_jour_min(texte), "unite": "jour"}


def jour_courant(campagne: Path, monde: dict) -> int:
    """Estimates the current in-game day, deterministically:
      - UT mode: last t from events.json → day (units_per_day)
      - otherwise: max « Day N » mentioned in chronology + sessions
    Returns 1 by default."""
    jours = {1}

    # UT mode: events.json
    temps = monde.get("meta", {}).get("time", {})
    upd = temps.get("units_per_day")
    evt_path = campagne / "events.json"
    if upd and evt_path.exists():
        try:
            data = charger_json(evt_path)
            ts = [e["t"] for e in data.get("events", [])
                  if isinstance(e.get("t"), int) and e["t"] >= 0]
            if ts:
                jours.add(max(ts) // upd + 1)
        except (OSError, json.JSONDecodeError, KeyError):
            pass

    # « Day N » mentions in the chronology
    chrono = monde.get("global_state", {}).get("timeline", "")
    if isinstance(chrono, str):
        for m in re.findall(r"[Jj]our\s+(\d+)", chrono):
            jours.add(int(m))

    # « Day N » mentions in all sessions
    sessions_dir = campagne / "sessions"
    if sessions_dir.is_dir():
        for sp in sessions_dir.glob("*.json"):
            try:
                for m in re.findall(r"[Jj]our\s+(\d+)", sp.read_text(encoding="utf-8")):
                    jours.add(int(m))
            except OSError:
                pass

    return max(jours)


# ─── Detection logic ──────────────────────────────────────────────────────────

def trouver_derniere_session(sessions_dir: Path) -> Path | None:
    """Returns the session file with the highest number."""
    candidats = []
    for sp in sessions_dir.glob("*.json"):
        m = re.match(r"0*(\d+)", sp.stem)
        if m:
            candidats.append((int(m.group(1)), sp))
    if not candidats:
        return None
    candidats.sort()
    return candidats[-1][1]


def analyser(campagne: Path, num_session: int | None) -> dict:
    """Returns a discrepancy report (dict)."""
    monde = charger_json(campagne / "world.json")

    # Load NPCs (tolerant)
    pnj_path = campagne / "npcs.json"
    pnj_liste = extraire_liste_pnj(charger_json(pnj_path)) if pnj_path.exists() else []
    pnj_connus_norm = [normaliser(nom_de(p)) for p in pnj_liste if nom_de(p)]

    lieux_connus_norm = collecter_lieux_universe(monde)

    # Session selection
    sessions_dir = campagne / "sessions"
    if num_session is not None:
        session_path = sessions_dir / f"{num_session:03d}.json"
        if not session_path.exists():
            session_path = sessions_dir / f"{num_session}.json"
    else:
        session_path = trouver_derniere_session(sessions_dir)

    if not session_path or not session_path.exists():
        raise FileNotFoundError(f"Session not found in {sessions_dir}")

    session = charger_json(session_path)

    ecarts = []  # each discrepancy: {"level": "bloquant"|"info", "regle": str, "message": str}

    def ajouter(niveau, regle, message):
        ecarts.append({"level": niveau, "regle": regle, "message": message})

    # 1. Visited locations absent from the world
    for lv in session.get("visited_locations", []):
        nom = nom_de(lv)
        if nom and not lieu_present(nom, lieux_connus_norm):
            ajouter("bloquant", "lieu_absent",
                    f"Visited location « {nom} » absent from universe.regions[].locations")

    # 2. NPCs encountered with no entry
    for pr in session.get("npcs_met", []):
        nom = nom_de(pr)
        if nom and not pnj_present(nom, pnj_connus_norm):
            ajouter("bloquant", "pnj_sans_fiche",
                    f"Encountered NPC « {nom} » has no entry in npcs.json")

    # 3 & 4. Factions: ST+LT objectives and presence in the clock
    factions = monde.get("global_state", {}).get("factions", [])
    horloge = monde.get("global_state", {}).get("faction_actions_horloge", {})
    horloge_actions = horloge.get("actions", []) if isinstance(horloge, dict) else []
    factions_horloge = {normaliser(a.get("faction", "")) for a in horloge_actions
                        if isinstance(a, dict)}

    for f in factions:
        if not isinstance(f, dict):
            continue
        fnom = f.get("name", "(unnamed)")
        if not f.get("short_term_goals"):
            ajouter("bloquant", "faction_sans_ct",
                    f"Faction « {fnom} » missing objectif_court_terme")
        if not f.get("long_term_goals"):
            ajouter("bloquant", "faction_sans_lt",
                    f"Faction « {fnom} » missing objectif_long_terme")
        if normaliser(fnom) not in factions_horloge:
            ajouter("bloquant", "faction_sans_horloge",
                    f"Faction « {fnom} » has no entry in faction_actions_horloge")

    # 5 & 6. Overdue / non-parsable clock deadlines
    jc = jour_courant(campagne, monde)
    for entry in horloge_actions:
        if not isinstance(entry, dict):
            continue
        fnom = entry.get("faction", "(unknown faction)")
        for action in entry.get("actions_en_cours", []):
            if not isinstance(action, dict):
                continue
            ech = action.get("echeance", "")
            label = action.get("action", "(action ?)")
            info = echeance_infos(ech)
            texte = info["texte"]
            # Marked resolved (statut, deadline OR label) → skip
            if (info["statut"] == "resolue" or _RE_RESOLU.search(texte)
                    or _RE_RESOLU.search(str(label))):
                continue
            if info["statut"] == "echue":
                ajouter("bloquant", "echeance_depassee",
                        f"[{fnom}] deadline OVERDUE (statut) — "
                        f"consequence to play/resolve (action: {label})")
            elif info["due"] is None:
                ajouter("info", "echeance_non_parsable",
                        f"[{fnom}] non-parsable deadline « {texte} » — "
                        f"the clock cannot be advanced by machine (action: {label})")
            elif info["unite"] == "jour" and info["due"] < jc:
                ajouter("bloquant", "echeance_depassee",
                        f"[{fnom}] deadline OVERDUE: Day {info['due']} < current day {jc} "
                        f"— consequence to play/resolve (action: {label})")

    # 7. Session played but heure_fin empty
    a_du_contenu = bool(session.get("actions") or session.get("visited_locations")
                        or session.get("resume"))
    if a_du_contenu and not (session.get("end_hour") or "").strip():
        ajouter("bloquant", "session_non_finalisee",
                f"Session {session.get('session', '?')} has content but "
                f"heure_fin is empty (session not finalized)")

    return {
        "campagne": str(campagne),
        "session_fichier": str(session_path),
        "session_num": session.get("session"),
        "estimated_current_day": jc,
        "ecarts": ecarts,
        "n_bloquants": sum(1 for e in ecarts if e["level"] == "bloquant"),
        "n_info": sum(1 for e in ecarts if e["level"] == "info"),
    }


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_session.py",
        description="Detects checklist discrepancies for the last session (read-only).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 check_session.py .hermes/mygamemaster/campaigns/la-naissance-dun-roi\n"
            "  python3 check_session.py <campaign> --session 4 --json\n"
        ),
    )
    parser.add_argument("campagne", help="Path to the campaign folder.")
    parser.add_argument("--session", type=int, default=None,
                        help="Session number to check (default: the last one).")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Output in JSON format.")
    args = parser.parse_args(argv)

    campagne = Path(args.campagne)
    if not campagne.is_dir():
        print(f"❌ Campaign not found: {campagne}", file=sys.stderr)
        return 2
    if not (campagne / "world.json").exists():
        print(f"❌ world.json not found in {campagne}", file=sys.stderr)
        return 2

    try:
        rapport = analyser(campagne, args.session)
    except FileNotFoundError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2
    except (json.JSONDecodeError, KeyError) as e:
        print(f"❌ Unreadable data: {e}", file=sys.stderr)
        return 2

    if args.as_json:
        print(json.dumps(rapport, ensure_ascii=False, indent=2))
        return 1 if rapport["n_bloquants"] else 0

    print(f"🔍 Check — session {rapport['session_num']} "
          f"({Path(rapport['session_fichier']).name}) "
          f"— estimated current day: {rapport['estimated_current_day']}")
    if not rapport["ecarts"]:
        print("✅ No discrepancy detected.")
        return 0

    for e in rapport["ecarts"]:
        marqueur = "❌" if e["level"] == "bloquant" else "ℹ"
        print(f"{marqueur} [{e['regle']}] {e['message']}")

    print()
    print(f"Summary: {rapport['n_bloquants']} blocking discrepancy(ies), "
          f"{rapport['n_info']} informational.")
    return 1 if rapport["n_bloquants"] else 0


if __name__ == "__main__":
    sys.exit(main())
