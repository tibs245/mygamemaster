#!/usr/bin/env python3
"""
world_docs.py — short blocks extracted from the campaign's reference documents.

`world.json > global_state.documents_de_reference` declares five files totalling
~166 000 chars that NO line of code ever opened. Asking the GM to remember to open
a 50 000-char file before describing the weather is a rule held by the prompt, and
the corpus shows what those are worth. So the extraction happens here and the
result is injected by `pre_llm_call.py`: the GM is shown the window instead of
being told where the window is.

First extractor: `season`. `saisons.json` carries 23 phase sheets of ~1 500 chars
plus a `table_de_lecture` of 927 chars mapping every day J1–J365 to a phase. We
resolve one day and emit ~300 chars — the light, the ground, the vegetation, and
the day the world tips into the next phase. The anti-tipping rule is appended only
within `BASCULE_JOURS` of that boundary, because that is the only moment it changes
what the GM should write.

The days cycle: `table_de_lecture` covers exactly one year and the first phase
declares `phase_precedente: "… (cycle précédent)"`, so J366 reads as J1 rather than
falling off the end of the table.

Conventions (contract §0, §9): source of truth = files; READ-ONLY, never writes;
STRICT FAIL-OPEN — a missing or broken document yields an empty block and exit 0,
never an exception, because this runs on the path of every turn. Exit 2 is reserved
for a usage error (campaign not found).

Targets: Python 3.11, PURE STDLIB.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from i18n import resolve_lang, t

INTERVALLE_RE = re.compile(r"^\s*J(\d+)\s*[-–—]\s*J(\d+)\s*$")
JOURS_PAR_CYCLE = 365
BASCULE_JOURS = 2
CONDENSE_MAX = 95
PRINCIPE_MAX = 140


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def charger(camp: Path, nom: str):
    """Reads one reference document. None if absent or unreadable (fail-open)."""
    try:
        with open(Path(camp) / nom, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as e:
        _log(f"ℹ world_docs : {nom} unreadable ({e}) — block skipped.")
        return None
    return data if isinstance(data, dict) else None


def jour_du_cycle(jour) -> int | None:
    """Maps an absolute fiction day onto the J1–J365 cycle. None if unusable."""
    try:
        n = int(jour)
    except (TypeError, ValueError):
        return None
    if n < 1:
        return None
    return ((n - 1) % JOURS_PAR_CYCLE) + 1


def resoudre_phase(table, jour) -> tuple[str, int, int] | None:
    """`table_de_lecture` lookup → (phase_id, first_day, last_day). None if no match."""
    n = jour_du_cycle(jour)
    if n is None or not isinstance(table, dict):
        return None
    for intervalle, phase_id in table.items():
        m = INTERVALLE_RE.match(str(intervalle))
        if not m:
            continue
        debut, fin = int(m.group(1)), int(m.group(2))
        if debut <= n <= fin and isinstance(phase_id, str):
            return phase_id, debut, fin
    return None


def _fiche(phases, phase_id):
    if not isinstance(phases, list):
        return {}
    for p in phases:
        if isinstance(p, dict) and p.get("id") == phase_id:
            return p
    return {}


def _condense(valeur, taille=CONDENSE_MAX) -> str:
    s = " ".join(str(valeur or "").split())
    if len(s) <= taille:
        return s
    coupe = s[:taille].rsplit(" ", 1)[0]
    return (coupe or s[:taille]) + "…"


def _suivante(phase_id: str) -> str:
    """`phase_suivante` values carry parenthesised notes — keep the id only."""
    return str(phase_id or "").split("(")[0].strip()


def season_block(camp, jour, lang="en") -> str:
    """The SEASON block for one fiction day. "" if the document cannot serve it."""
    doc = charger(Path(camp), "saisons.json")
    if not doc:
        return ""
    resolu = resoudre_phase(doc.get("table_de_lecture"), jour)
    if resolu is None:
        return ""
    phase_id, _, fin = resolu
    fiche = _fiche(doc.get("phases"), phase_id)
    if not fiche:
        return ""

    n = jour_du_cycle(jour)
    absolu = int(jour)
    restants = fin - n
    lignes = [t("season.header", lang, day=absolu,
                name=fiche.get("nom") or phase_id, phase=phase_id)]
    for cle, cle_i18n in (("lumiere", "season.light"),
                          ("sol_et_eau", "season.ground"),
                          ("vegetation", "season.vegetation")):
        valeur = _condense(fiche.get(cle))
        if valeur:
            lignes.append(t(cle_i18n, lang) + valeur)
    suivante = _suivante(fiche.get("phase_suivante"))
    if suivante:
        lignes.append(t("season.next", lang, phase=suivante, day=absolu + restants + 1,
                        days=restants + 1))
    if restants + 1 <= BASCULE_JOURS:  # restants is the last day IN the phase
        principe = _condense((doc.get("regle_anti_bascule") or {}).get("principe"),
                             PRINCIPE_MAX)
        if principe:
            lignes.append(t("season.tipping", lang) + principe)
    return "\n".join(lignes)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="world_docs.py",
        description="Short blocks extracted from the campaign reference documents.")
    sub = ap.add_subparsers(dest="commande", required=True)
    s = sub.add_parser("season", help="SEASON block for a fiction day J{n}")
    s.add_argument("campagne", help="campaign directory")
    s.add_argument("jour", nargs="?", default=None,
                   help="fiction day (default: rules.time.tracking.current_day)")
    s.add_argument("--lang", default=None, help="force the display locale")
    return ap


def _jour_courant(camp: Path):
    monde = charger(camp, "world.json") or {}
    suivi = (((monde.get("rules") or {}).get("time") or {}).get("tracking")) or {}
    return monde, suivi.get("current_day")


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    camp = Path(args.campagne)
    if not camp.is_dir():
        _log(f"❌ world_docs : campaign not found ({camp}).")
        return 2
    monde, jour_defaut = _jour_courant(camp)
    jour = args.jour if args.jour is not None else jour_defaut
    lang = args.lang or resolve_lang(monde)
    try:
        bloc = season_block(camp, jour, lang)
    except Exception as e:                          # ultimate CLI guard (fail-open)
        _log(f"❌ world_docs : unexpected failure ({e}).")
        bloc = ""
    if bloc:
        print(bloc)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
    except KeyboardInterrupt:
        _log("Interrupted.")
        sys.exit(2)
