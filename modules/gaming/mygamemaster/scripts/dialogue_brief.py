#!/usr/bin/env python3
"""
dialogue_brief.py — GM-side slice for a scene that turned into a conversation.

Answers the failure documented in references/dialogue-craft.md: the existing NPC
brief is a pile of FACTS, and a model fed nothing but facts writes an NPC who
recites them. A conversation needs what a character WANTS here, what they
WITHHOLD, what they REFUSE, and how their mouth works — assembled from the files,
filtered on the stake of this exchange.

Not to be confused with its two siblings:
  * `build_brief.py` serves a Level-2 NPC AGENT (hides GM-only fields, caches);
  * `show_npc.py` dumps the COMPLETE sheet for consultation;
  * this one serves the GM WRITING THE SCENE, and it filters — a brief that dumps
    everything produces a character who says everything.

GM-facing, like show_npc.py: it prints `gm_hypotheses` and `connaissances_privees`
so the GM knows what the pressure is. Those are never spoken unless the character
CHOOSES to reveal them.

READ-ONLY (never writes). STRICT FAIL-OPEN on data: a missing `voix` block, no
emotions, an unreadable npcs.json → the section is simply absent, never a crash.

Usage:
  python3 dialogue_brief.py <campaign> "<NPC>" [--stake "what the PC wants here"]
  python3 dialogue_brief.py <campaign> "<NPC>" --with "<other NPC>" [--with ...]
  python3 dialogue_brief.py <campaign> "<NPC>" --json [--facts N]
  python3 dialogue_brief.py <campaign> --list

Exit codes:
  0  brief produced (or --list)
  1  NPC not found
  2  usage error (campaign / npcs.json not found)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    import worldlib as W
    _charger = W.charger_json
    _resoudre = W.chemin_campagne
except Exception:  # fail-open: standalone if worldlib is unavailable
    def _charger(chemin, defaut=None):
        try:
            with open(chemin, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError, ValueError):
            return defaut

    def _resoudre(arg):
        return Path(arg).expanduser().resolve()

try:
    import emotions as E
    _ligne_emotion = E.summary_line
except Exception:  # fail-open: the mood section is optional
    def _ligne_emotion(_fiche):
        return ""

FACTS_DEFAULT = 5
FIELD_MAX = 400

# Words too common to carry a stake ("the bell" must match, "about the" must not).
_STOPWORDS = {
    "about", "after", "against", "because", "before", "being", "between", "could",
    "does", "doing", "from", "have", "here", "into", "just", "know", "make",
    "more", "much", "over", "same", "sont", "such", "than", "that", "their",
    "them", "then", "there", "these", "they", "this", "those", "under", "until",
    "very", "want", "wants", "what", "when", "where", "which", "while", "with",
    "would", "your", "avec", "dans", "elle", "leur", "mais", "pour", "quoi",
    "sans", "sont", "tout", "vers", "veut", "vous",
}


def _norme(texte: str) -> str:
    s = unicodedata.normalize("NFKD", str(texte or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _mots(texte: str) -> set:
    return {m for m in re.findall(r"[a-z0-9']{4,}", _norme(texte)) if m not in _STOPWORDS}


def _liste_pnj(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for cle in ("npcs", "pnj"):
            if isinstance(data.get(cle), list):
                return data[cle]
    return []


def _nom(fiche, defaut=""):
    if not isinstance(fiche, dict):
        return defaut
    return fiche.get("name") or fiche.get("nom") or defaut


def trouver(fiches, nom):
    """Exact case-insensitive match, then unique substring match. None otherwise."""
    cible = _norme(nom).strip()
    if not cible:
        return None
    for fiche in fiches:
        if _norme(_nom(fiche)).strip() == cible:
            return fiche
    partiels = [f for f in fiches if cible in _norme(_nom(f))]
    return partiels[0] if len(partiels) == 1 else None


def _txt(valeur, defaut=""):
    if isinstance(valeur, str) and valeur.strip():
        return valeur.strip()[:FIELD_MAX]
    return defaut


def _items(valeur):
    if isinstance(valeur, list):
        return [str(v).strip()[:FIELD_MAX] for v in valeur if str(v).strip()]
    if isinstance(valeur, str) and valeur.strip():
        return [valeur.strip()[:FIELD_MAX]]
    return []


def voix(fiche) -> dict:
    """The `voix` block, normalized. {} when absent or malformed (fail-open)."""
    brut = fiche.get("voix") if isinstance(fiche, dict) else None
    if not isinstance(brut, dict):
        return {}
    out = {}
    for cle in ("registre", "rythme", "sous_tension"):
        val = _txt(brut.get(cle))
        if val:
            out[cle] = val
    for cle in ("lexique", "tics", "ne_dit_jamais"):
        val = _items(brut.get(cle))
        if val:
            out[cle] = val
    return out


def faits_pertinents(fiche, stake: str, limite: int = FACTS_DEFAULT):
    """`established_facts` ranked against the stake. Returns (kept, dropped_count).

    Without a stake, the LAST facts win: a fact list grows chronologically, so its
    tail is what was most recently played and most likely to matter now.
    """
    faits = _items(fiche.get("established_facts"))
    limite = max(1, int(limite))
    if len(faits) <= limite:
        return faits, 0
    cles = _mots(stake)
    if not cles:
        return faits[-limite:], len(faits) - limite
    classes = sorted(
        enumerate(faits),
        key=lambda pair: (-len(cles & _mots(pair[1])), -pair[0]),
    )
    gardes = [f for _, f in classes[:limite]]
    ordre = [f for f in faits if f in gardes]
    return ordre, len(faits) - len(ordre)


def collecter(fiche, stake="", nb_faits=FACTS_DEFAULT) -> dict:
    """Structured brief for one NPC (the --json payload)."""
    limites = fiche.get("limites") if isinstance(fiche.get("limites"), dict) else {}
    faits, restants = faits_pertinents(fiche, stake, nb_faits)
    motivations = _items(limites.get("motivations_personnelles"))
    if not motivations:
        motivations = _items(fiche.get("motivations_personnelles"))
    return {
        "name": _nom(fiche, "?"),
        "titre": _txt(fiche.get("titre")),
        "stake": _txt(stake),
        "voix": voix(fiche),
        "veut": {
            "motivations": motivations,
            "attitude": _txt(fiche.get("attitude")),
        },
        "cache": _items(fiche.get("connaissances_privees")),
        "pression": _items(fiche.get("gm_hypotheses")),
        "refuse": {
            "lignes_rouges": _items(limites.get("lignes_rouges")),
            "peurs": _items(limites.get("peurs")),
        },
        "humeur": _ligne_emotion(fiche),
        "relation": {
            "niveau": _txt(fiche.get("relation_niveau")),
            "premiere_rencontre": _txt(fiche.get("premiere_rencontre")),
            "derniere_interaction": _txt(fiche.get("derniere_interaction")),
            "localisation": _txt(fiche.get("localisation_actuelle")),
        },
        "faits": faits,
        "faits_restants": restants,
    }


def _bloc(titre, lignes):
    if not lignes:
        return []
    return ["", titre] + ["  • %s" % ligne for ligne in lignes]


def rendre(brief: dict, autres=None) -> str:
    """Human-readable brief. Order is deliberate: wants → hides → refuses → voice.

    Facts come last. They are the material the scene draws on, not what drives it;
    putting them first is what produced the reciting NPC in the first place.
    """
    nom = brief["name"]
    entete = "🗣️  DIALOGUE BRIEF — %s%s" % (nom, (" (%s)" % brief["titre"]) if brief["titre"] else "")
    out = [entete, "=" * min(len(entete) + 2, 78)]
    out.append("Stake of this exchange: %s" % (brief["stake"] or "— not stated (name it before writing)"))

    veut = brief["veut"]
    lignes_veut = list(veut["motivations"])
    if veut["attitude"]:
        lignes_veut.append("Attitude toward the PC: %s" % veut["attitude"])
    out += _bloc("── WANTS HERE (write every line from this, not from the PC's question) ──", lignes_veut)
    out += _bloc("── HIDES (pressure the lines are written AGAINST — spoken only if they choose to) ──",
                 brief["cache"])
    out += _bloc("── UNCONFIRMED, GM ONLY (never narrate as fact, never let the NPC act on it) ──",
                 brief["pression"])

    refuse = brief["refuse"]
    lignes_refuse = ["Red line: %s" % x for x in refuse["lignes_rouges"]]
    lignes_refuse += ["Fear: %s" % x for x in refuse["peurs"]]
    out += _bloc("── REFUSES (a refusal is a gift: it gives the player something to push against) ──",
                 lignes_refuse)

    v = brief["voix"]
    if v:
        lignes_voix = []
        for cle, label in (("registre", "Register"), ("rythme", "Rhythm"),
                           ("sous_tension", "Under stress")):
            if v.get(cle):
                lignes_voix.append("%s: %s" % (label, v[cle]))
        for cle, label in (("lexique", "Vocabulary / imagery"),
                           ("tics", "Verbal signatures (sparingly)"),
                           ("ne_dit_jamais", "Never says")):
            if v.get(cle):
                lignes_voix.append("%s: %s" % (label, " ; ".join(v[cle])))
        out += _bloc("── VOICE (this mouth and no other) ──", lignes_voix)
    else:
        out += ["", "── VOICE ──",
                "  ⚠ No `voix` block on this sheet. Write the voice now (register, rhythm, what",
                "    they never say, how they deform under stress), play it, then PERSIST it in",
                "    npcs.json in this same response — a voice that drifts reads as a new character."]

    if brief["humeur"]:
        out += ["", "── MOOD (play it through behaviour and word choice — never state it) ──",
                "  %s" % brief["humeur"]]

    rel = brief["relation"]
    lignes_rel = []
    for cle, label in (("niveau", "Relation"), ("derniere_interaction", "Last interaction"),
                       ("premiere_rencontre", "First met"), ("localisation", "Currently at")):
        if rel.get(cle):
            lignes_rel.append("%s: %s" % (label, rel[cle]))
    out += _bloc("── RELATION ──", lignes_rel)

    titre_faits = "── FACTS RELEVANT TO THIS STAKE ──" if brief["stake"] else "── MOST RECENT FACTS ──"
    out += _bloc(titre_faits, brief["faits"])
    if brief["faits_restants"]:
        out.append("  … %d more established fact(s) on the sheet — show_npc.py \"%s\" for all."
                   % (brief["faits_restants"], nom))

    if autres:
        out += ["", "── ALSO IN THE SCENE (their mouths must not be interchangeable) ──"]
        for autre in autres:
            v2 = autre["voix"]
            resume = v2.get("registre") or "no `voix` block — write one"
            tics = " ; ".join(v2.get("tics", []))
            out.append("  • %s — %s%s" % (autre["name"], resume, (" [%s]" % tics) if tics else ""))

    out += ["", "── BEFORE YOU WRITE ──",
            "  ① every line pursues %s's own goal, not the PC's question" % nom,
            "  ② say less than they know — the gap is what makes it worth reading",
            "  ③ something must cost, move, or be refused before the scene ends",
            "  ④ a reader with the name tags removed should still know who is speaking",
            "  Rubric + dry-summary fallback: references/dialogue-craft.md"]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="GM-side brief for a scene that turned into a conversation.")
    ap.add_argument("campagne", help="campaign folder (contains npcs.json)")
    ap.add_argument("pnj", nargs="?", help="NPC name (exact or unambiguous substring)")
    ap.add_argument("--stake", default="", help="what the PC wants from this exchange (filters the facts)")
    ap.add_argument("--with", dest="autres", action="append", default=[],
                    help="another NPC present in the scene (repeatable)")
    ap.add_argument("--facts", type=int, default=FACTS_DEFAULT, help="max established_facts kept")
    ap.add_argument("--list", action="store_true", help="list the campaign's NPCs")
    ap.add_argument("--json", action="store_true", help="structured output")
    a = ap.parse_args(argv)

    camp = _resoudre(a.campagne)
    chemin = camp / "npcs.json" if camp.is_dir() else camp
    data = _charger(chemin, None)
    if data is None:
        print("🔴 npcs.json not found or unreadable: %s" % chemin, file=sys.stderr)
        return 2
    fiches = _liste_pnj(data)

    if a.list or not a.pnj:
        for fiche in fiches:
            marque = "🗣" if voix(fiche) else "·"
            print("  %s %s" % (marque, _nom(fiche, "?")))
        if not a.pnj and not a.list:
            print("\n(🗣 = has a `voix` block)", file=sys.stderr)
        return 0

    fiche = trouver(fiches, a.pnj)
    if not fiche:
        print("🔴 NPC not found (or ambiguous): %s" % a.pnj, file=sys.stderr)
        print("Available: %s" % ", ".join(_nom(f, "?") for f in fiches), file=sys.stderr)
        return 1

    brief = collecter(fiche, a.stake, a.facts)
    autres = []
    for nom in a.autres:
        f2 = trouver(fiches, nom)
        if f2 is not None and _nom(f2) != _nom(fiche):
            autres.append(collecter(f2, a.stake, a.facts))

    if a.json:
        print(json.dumps({"brief": brief, "autres": autres}, ensure_ascii=False, indent=2))
    else:
        print(rendre(brief, autres))
    return 0


if __name__ == "__main__":
    sys.exit(main())
