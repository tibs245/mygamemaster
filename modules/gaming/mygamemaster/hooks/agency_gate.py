#!/usr/bin/env python3
"""
agency_gate.py — DETERMINISTIC agency guard (TIER 0 rules AGENCY-01/02/03).

Owns the three rules the corpus proved fatal (the only two sessions scored 1/5 are the GM acting
or speaking in place of the PC), which `llm_judge.py` cannot own because it is fail-open by
design — an unreachable API or an exhausted budget let the offending turn through:

  AGENCY-01  Never write an action, gesture, posture, gaze, breath or movement of the PC —
             write only what the PC perceives.
  AGENCY-02  Never put words in the PC's mouth: when the player gave substance without text,
             emit [VERBATIM TO BE SUPPLIED BY THE PLAYER].
  AGENCY-03  Narrate at most ONE PC action per turn, and only the direct execution of an action
             the player has just declared — cite the declaration.

Stdlib only, no network, no model. The verdict shape mirrors `llm_judge.py` so that
`llm_judge.format_feedback` renders both.

TWO KINDS OF "DO NOT BLOCK", never to be confused:
  * fail-open as a GLOBAL POSTURE is forbidden here — the verdict never depends on a network
    call, a config flag or an attempt budget;
  * per-sentence CONFIDENCE is required — a false positive blocks a legitimate turn and makes the
    GM unusable, so only a closed lexicon of known verbs anchored on an unambiguous PC subject
    blocks. Unknown verb, modal, negation, question or verb of perception → AMBIGUOUS, the turn
    continues to the LLM judge rather than being guessed at.

HOW: dialogue (« … », " … ", “ … ”, dash lines) is masked first, so an NPC saying « tu devrais
partir » is never read as the GM making the PC act. Narration is split into sentences, questions
skipped, and each sentence anchored on a subject that can ONLY be the PC — French `tu`, English
`you`, or a player-character proper name. `vous`/`te`/`me` are deliberately not anchors: in French
they are usually object clitics ("Berthe vous regarde" is the NPC gazing, which is allowed). From
the anchor we walk over clitics, auxiliaries, articles and adverbs only, and classify the first
content word against three closed lexicons: perception → allowed, speech → AGENCY-02, action →
AGENCY-01. An action whose verb also appears in the player's declaration is AGENCY-03's bounded
exception and is allowed, with the declaration cited in the report.

OPERATOR ESCAPE HATCH
  MGM_AGENCY_GATE=off         disables the deterministic gate (default: ON).
                              Accepted off values: off / 0 / false / no / non / disabled.
  MGM_AGENCY_MAX_ATTEMPTS=N   rewrite budget before the loud forced pass (mj_checkpoint.py).

EXTENDING: everything is data in LEXICONS below — `"approch*"` is a prefix (≤5 trailing letters),
`"dis"` an exact token, accents ignored on both sides. A new language is a new key; nothing else
in this file is language-specific.

CLI:  echo "<draft>" | python3 agency_gate.py [--declared "..."] [--pc Rubis]
      exit 0 = no deterministic violation, 1 = violation (JSON report on stdout).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata

RULE_ACTION = "AGENCY-01"
RULE_SPEECH = "AGENCY-02"
RULE_COUNT = "AGENCY-03"

ENV_SWITCH = "MGM_AGENCY_GATE"
ENV_MAX_ATTEMPTS = "MGM_AGENCY_MAX_ATTEMPTS"

# A sentence carrying the AGENCY-02 placeholder is the prescribed CORRECT form, never a violation.
PLACEHOLDERS = ("[verbatim", "[a fournir", "[to be supplied")

PERCEPTION, ACTION, SPEECH, AMBIGUOUS = "perception", "action", "speech", "ambiguous"

# Lexicons — "stem*" = prefix match, "word" = exact token. Write accents naturally.
LEXICONS = {
    "fr": {
        "anchors": ["tu"],
        "skip": [
            "t", "te", "y", "en", "l", "le", "la", "les", "lui", "leur", "se", "s", "me", "m",
            "nous", "vous",
            "un", "une", "du", "de", "des", "ton", "ta", "tes", "son", "sa", "ses", "cette", "ce",
            "as", "avais", "es", "etais", "avez", "etes",
            "lentement", "doucement", "brusquement", "soudain", "soudainement", "enfin", "alors",
            "aussi", "deja", "encore", "puis", "vite", "prudemment", "instinctivement",
            "machinalement", "legerement", "longuement", "aussitot", "immediatement", "presque",
            "toujours", "simplement", "juste", "meme",
        ],
        "hedge": [
            "ne", "n", "pas", "plus", "jamais", "rien",
            "peux", "peut", "pourrais", "pourras", "dois", "devrais", "devras", "veux", "voulais",
            "voudrais", "essaies", "tentes", "comptes", "penses", "crois", "croyais", "semble",
            "sembles", "parais", "auras", "aurais", "seras", "serais", "si", "quand", "lorsque",
            "vais", "vas", "va",
        ],
        "perception": [
            "vois", "voit", "voyais", "voyait", "verras", "vu", "revois",
            "apercois", "apercoit", "apercev*", "apercu",
            "entend*", "entendu", "oui",
            "sens", "sent", "sentais", "sentait", "senti", "sentiras", "ressens", "ressent",
            "percois", "percoit", "percevais", "percu",
            "remarqu*", "distingu*", "discern*", "devin*",
            "reconnais", "reconnait", "reconnaiss*", "reconnu",
            "comprend*", "comprenn*", "compris",
            "sais", "sait", "savais", "su", "connais", "connait",
            "souviens", "souvient", "souvenais",
            "goutes", "goute", "hume", "humes",
        ],
        "speech": [
            "dis", "dit", "disais", "redis", "parl*",
            "repond*", "repliqu*", "retorqu*", "murmur*", "chuchot*", "cri*", "demand*",
            "declar*", "ajout*", "expliqu*", "racont*", "annonc*", "promet*", "jur*",
            "remerci*", "salu*", "appel*",
        ],
        "action": [
            "approch*", "avanc*", "recul*", "march*", "cour*", "entr*", "sor*", "mont*",
            "descend*", "pos*", "prend*", "prenn*", "pris", "saisi*", "attrap*", "touch*",
            "tend*", "lev*", "baiss*", "tourn*", "retourn*", "ouvr*", "ferm*", "frapp*",
            "souri*", "hoch*", "acquiesc*", "respir*", "souffl*", "inspir*", "expir*", "serr*",
            "gliss*", "agenouill*", "assied*", "assoi*", "assey*", "regard*", "fix*", "observ*",
            "scrut*", "detourn*", "clign*", "hauss*", "suis", "suit", "suivais", "suiv*",
            "travers*", "franchi*", "quitt*", "depos*", "ramass*", "tir*", "pouss*", "boi*",
            "buv*", "mang*", "degain*", "brandi*", "ecri*", "lis", "lit", "lisais", "lu",
            "bond*", "saut*", "grimp*", "plong*", "pench*", "inclin*", "croises", "croisant",
            "frisson*", "trembl*", "hesit*", "reprend*", "laiss*", "arret*", "stopp*", "boug*",
            "deplac*", "cherch*", "fouill*", "jet*", "soulev*", "souleve*", "empoign*",
            "agripp*", "lach*", "pivot*", "enjamb*", "esquiv*", "frott*", "essui*",
            "ecart*", "allum*", "etein*", "attach*", "detach*", "retir*", "enlev*", "remet*",
            "remets", "donn*", "lanc*", "install*", "gratt*", "caress*", "embrass*", "redress*",
            "accroupi*", "cueill*", "allong*", "etend*", "enfil*", "attends", "attend*",
            "avale", "avales", "avalais", "verse", "verses", "versais", "coupe", "coupes",
            "coupais", "tape", "tapes", "tapais", "retien*", "retenais", "nou*",
            "rapport*", "ramen*", "rentr*", "repart*", "reviens", "revient",
        ],
        "conj": ["et", "puis", "avant"],
        # « … », dis-tu. — narrative inversion survives inside a masked dialogue line.
        "inverted_speech": r"\b(dis|reponds|repond|repliques|retorques|murmures|chuchotes|"
                           r"demandes|ajoutes|souffles|cries|lances)\s*-\s*tu\b",
    },
    "en": {
        "anchors": ["you"],
        "skip": [
            "yourself", "the", "a", "an", "your", "his", "her", "its", "their",
            "have", "has", "had", "are", "were", "am", "is", "been", "being", "ve", "re",
            "slowly", "carefully", "quietly", "then", "finally", "suddenly", "instinctively",
            "already", "still", "now", "gently", "quickly", "almost", "just", "also", "again",
            "simply", "barely", "instantly",
        ],
        "hedge": [
            "not", "no", "never", "nothing", "dont", "doesnt", "didnt", "cant", "cannot",
            "can", "could", "must", "should", "may", "might", "would", "will", "ll",
            "want", "wants", "wanted", "need", "needs", "try", "tries", "tried",
            "seem", "seems", "think", "thinks", "believe", "wonder", "if", "when", "whether",
        ],
        "perception": [
            "see", "sees", "saw", "seen", "hear", "hears", "heard", "feel", "feels", "felt",
            "smell", "smells", "smelled", "smelt", "taste", "tastes", "tasted",
            "notice*", "perceive*", "sense", "senses", "sensed", "recogniz*", "recognis*",
            "realiz*", "realis*", "know", "knows", "knew", "remember*", "glimpse*", "make",
        ],
        "speech": [
            "say", "says", "said", "reply", "replies", "replied", "answer*", "ask", "asks",
            "asked", "whisper*", "shout*", "yell*", "mutter*", "murmur*", "tell", "tells",
            "told", "call*", "add", "adds", "added", "explain*", "declare*", "promise*",
            "thank*", "greet*", "speak", "speaks", "spoke",
        ],
        "action": [
            "approach*", "step*", "walk*", "run", "runs", "ran", "reach*", "place*", "put",
            "puts", "set", "sets", "grab*", "take", "takes", "took", "seize*", "open*",
            "close*", "shut", "turn*", "kneel*", "knelt", "nod", "nods", "nodded", "smile*",
            "breathe*", "breath*", "draw", "draws", "drew", "push*", "pull*", "lift*", "lower*",
            "raise*", "enter*", "exit*", "leave", "leaves", "left", "climb*", "descend*",
            "cross*", "touch*", "press*", "grip*", "clench*", "look*", "stare*", "gaze*",
            "glance*", "watch*", "follow*", "sit", "sits", "sat", "stand", "stands", "stood",
            "lean*", "move*", "pick*", "drop*", "hand", "hands", "handed", "give", "gives",
            "gave", "swallow*", "shiver*", "tense*", "tighten*", "flinch*", "drink", "drinks",
            "drank", "eat", "eats", "ate", "write", "writes", "wrote", "read", "reads",
            "rise", "rises", "rose", "shrug*", "wince*", "hold", "holds", "held", "grasp*",
            "slide", "slides", "slid", "crouch*", "duck*", "jump*", "search*", "pause",
            "pauses", "paused", "hesitate*", "tremble*", "freeze", "freezes", "froze",
            "wipe*", "light*", "lit", "unsheathe*", "brush*", "tie", "ties", "tied", "untie*",
            "carry", "carries", "carried", "throw", "throws", "threw", "slip", "slips",
            "slipped", "point", "points", "pointed", "gesture*", "rush*", "stride*", "strode",
            "stumble*", "sigh*", "blink*", "settle*", "crawl*", "wait", "waits", "waited",
            "spin", "spins", "spun", "go", "goes", "went", "bring", "brings", "brought",
            "gather*", "haul*", "fetch*", "head", "heads", "headed", "return",
            "returns", "returned",
        ],
        "conj": ["and", "then", "before"],
        "inverted_speech": None,
    },
}

_TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_SENT_RE = re.compile(r"[.!?…;\n]+")

_QUOTE_RES = [
    re.compile(r"«.*?»", re.S),
    re.compile(r"“.*?”", re.S),
    re.compile(r"\".*?\"", re.S),
    re.compile(r"^[ \t]*[—–-][ \t].*$", re.M),
]


def strip_accents(s):
    """Lowercase, accent-free form so 'reconnaît' and 'reconnait' hit the same lexicon entry."""
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def _mask_dialogue(text):
    """Blanks quoted dialogue, preserving length and newlines so indices stay aligned with `text`."""
    out = text
    for rx in _QUOTE_RES:
        out = rx.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), out)
    return out


def _quotes(text):
    """Normalized contents of every quoted span."""
    found = []
    for rx in _QUOTE_RES[:3]:
        for m in rx.finditer(text or ""):
            inner = strip_accents(m.group(0)[1:-1]).strip()
            if len(inner) >= 4:
                found.append(inner)
    return found


def _sentences(masked):
    """(start, end) spans of sentence-ish segments of the masked text."""
    spans, start = [], 0
    for m in _SENT_RE.finditer(masked):
        if masked[start:m.end()].strip():
            spans.append((start, m.end()))
        start = m.end()
    if masked[start:].strip():
        spans.append((start, len(masked)))
    return spans


def _match(token, patterns):
    """Matching lexicon entry, or None. 'stem*' is a prefix accepting ≤5 extra letters."""
    for p in patterns:
        if p.endswith("*"):
            stem = p[:-1]
            if token.startswith(stem) and 0 <= len(token) - len(stem) <= 5:
                return p
        elif token == p:
            return p
    return None


def _classify(token, lex):
    for kind in (SPEECH, PERCEPTION, ACTION):
        hit = _match(token, lex.get(kind) or [])
        if hit:
            return kind, hit
    return AMBIGUOUS, None


def _scan_anchor(tokens, i, lex):
    """Walks forward from a PC-subject anchor to the first content word and classifies it.

    Only clitics/articles/auxiliaries/adverbs are walked over: the first word that is neither a
    skip word nor a known verb ends the scan as AMBIGUOUS, which keeps a noun further down the
    sentence from ever being read as a verb."""
    j, steps = i + 1, 0
    while j < len(tokens) and steps < 5:
        tok = tokens[j]
        if tok in lex["_hedge"]:
            return AMBIGUOUS, None
        if tok in lex["_skip"]:
            j += 1
            steps += 1
            continue
        return _classify(tok, lex)
    return AMBIGUOUS, None


def _usable_name(name, lexicons):
    """A PC name colliding with a common word would anchor on every sentence — drop it instead."""
    for lex in lexicons.values():
        if name in (lex.get("skip") or []) or name in (lex.get("hedge") or []):
            return False
        for kind in (SPEECH, PERCEPTION, ACTION):
            if _match(name, lex.get(kind) or []):
                return False
    return True


def _prepare(lexicons, pc_names):
    prepared = []
    lexicons = lexicons or LEXICONS
    names = [strip_accents(n) for n in (pc_names or []) if n and len(strip_accents(n)) >= 3]
    names = [n for n in names if _usable_name(n, lexicons)]
    for code, lex in lexicons.items():
        d = dict(lex)
        d["_code"] = code
        d["_skip"] = set(lex.get("skip") or [])
        d["_hedge"] = set(lex.get("hedge") or [])
        d["_anchors"] = set(lex.get("anchors") or []) | set(names)
        d["_conj"] = set(lex.get("conj") or [])
        prepared.append(d)
    return prepared, set(names)


def _findings_for_segment(seg_masked, seg_raw, prepared, names):
    out = []
    tokens = [strip_accents(t) for t in _TOKEN_RE.findall(seg_masked)]
    for lex in prepared:
        anchored = False
        for i, tok in enumerate(tokens):
            if tok not in lex["_anchors"]:
                # "tu hoches la tête ET tu souris" often drops the second pronoun. A conjunction
                # inherits the PC subject, but only once the sentence has established one.
                if anchored and tok in lex["_conj"]:
                    kind, entry = _scan_anchor(tokens, i, lex)
                    if kind in (ACTION, SPEECH):
                        out.append({"kind": kind, "verb": entry, "lang": lex["_code"],
                                    "extrait": _clean(seg_raw), "subject": tok})
                continue
            anchored = True
            kind, entry = _scan_anchor(tokens, i, lex)
            back, hit = _classify(tokens[i - 1], lex) if i > 0 else (AMBIGUOUS, None)
            # « … », dit Rubis. — a speech verb just BEFORE a PC name attributes the line to the PC.
            if kind is AMBIGUOUS and tok in names and back == SPEECH:
                kind, entry = SPEECH, hit
            # "si tu avances", "if you step" — a hedge introducing the clause makes it hypothetical.
            elif i > 0 and tokens[i - 1] in lex["_hedge"]:
                kind, entry = AMBIGUOUS, None
            out.append({"kind": kind, "verb": entry, "lang": lex["_code"],
                        "extrait": _clean(seg_raw), "subject": tok})
    return out


def _inverted_speech(seg_raw, prepared):
    out = []
    flat = strip_accents(seg_raw)
    for lex in prepared:
        rx = lex.get("inverted_speech")
        if not rx:
            continue
        m = re.search(rx, flat)
        if m:
            out.append({"kind": SPEECH, "verb": m.group(1), "lang": lex["_code"],
                        "extrait": _clean(seg_raw), "subject": "tu"})
    return out


def _clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def _truncate(s, n=200):
    s = _clean(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def _declaration_index(declared, prepared):
    """The verbs the player actually used, plus the normalized declaration text."""
    keys = set()
    for tok in (strip_accents(t) for t in _TOKEN_RE.findall(declared or "")):
        for lex in prepared:
            for kind in (SPEECH, ACTION):
                hit = _match(tok, lex.get(kind) or [])
                if hit:
                    keys.add(hit)
    return keys, strip_accents(declared or "")


def _has_placeholder(extrait):
    low = strip_accents(extrait)
    return any(p in low for p in PLACEHOLDERS)


def _violation(regle, extrait, pourquoi, correction):
    return {"domaine": "conduite", "regle": regle, "extrait": _truncate(extrait),
            "pourquoi": pourquoi, "correction": correction}


def analyze(draft, declared="", pc_names=(), lexicons=None):
    """Deterministic AGENCY verdict for one narration draft.

    Returns {"ok", "violations", "allowed", "actions", "ambiguous", "declared"}; `violations`
    carries the shape llm_judge.format_feedback expects."""
    text = draft or ""
    prepared, names = _prepare(lexicons, pc_names)
    masked = _mask_dialogue(text)
    decl_keys, decl_norm = _declaration_index(declared, prepared)
    draft_quotes = _quotes(text)

    findings, ambiguous = [], 0
    for s, e in _sentences(masked):
        seg_masked, seg_raw = masked[s:e], text[s:e]
        if _clean(seg_masked).endswith("?"):
            continue
        for f in _findings_for_segment(seg_masked, seg_raw, prepared, names):
            if f["kind"] is AMBIGUOUS:
                ambiguous += 1
            elif f["kind"] in (ACTION, SPEECH):
                findings.append(f)
        findings.extend(_inverted_speech(seg_raw, prepared))

    seen, uniq = set(), []
    for f in findings:
        key = (f["kind"], f["verb"], f["extrait"])
        if key not in seen:
            seen.add(key)
            uniq.append(f)

    actions = [f for f in uniq if f["kind"] == ACTION]
    speeches = [f for f in uniq if f["kind"] == SPEECH]

    for f in actions:
        f["declared_ok"] = bool(f["verb"] and f["verb"] in decl_keys)
    for f in speeches:
        f["declared_ok"] = (_has_placeholder(f["extrait"])
                            or any(q in decl_norm for q in draft_quotes if len(q) >= 4))

    bad_actions = [f for f in actions if not f["declared_ok"]]
    bad_speech = [f for f in speeches if not f["declared_ok"]]
    allowed = [f for f in actions + speeches if f["declared_ok"]]

    violations = []
    for f in bad_speech[:3]:
        violations.append(_violation(
            RULE_SPEECH, f["extrait"],
            "the GM puts words in the PC's mouth (verb « %s »)" % f["verb"],
            "Delete the PC's line. If the player gave substance without text, write "
            "[VERBATIM TO BE SUPPLIED BY THE PLAYER] and stop."))
    for f in bad_actions[:3]:
        violations.append(_violation(
            RULE_ACTION, f["extrait"],
            "the GM makes the PC act (verb « %s »): action, gesture, posture, gaze, breath or "
            "movement of the PC" % f["verb"],
            "Remove this action. Write only what the PC PERCEIVES (sight, sound, smell, touch), "
            "then stop and hand control back."))
    if len(actions) > 1 and bad_actions:
        violations.append(_violation(
            RULE_COUNT, bad_actions[0]["extrait"],
            "%d PC actions narrated in a single turn (limit: one, and only the execution of the "
            "action the player has just declared)" % len(actions),
            "Keep at most the single declared action, cite the declaration, and stop at the first STOP."))

    return {
        "ok": not violations,
        "violations": violations,
        "allowed": [{"regle": RULE_COUNT if f["kind"] == ACTION else RULE_SPEECH,
                     "extrait": _truncate(f["extrait"]), "verbe": f["verb"]} for f in allowed],
        "actions": len(actions),
        "ambiguous": ambiguous,
        "declared": _truncate(declared, 160),
    }


def enabled(env=None):
    """ON by default. MGM_AGENCY_GATE=off|0|false|no|non unblocks a live campaign."""
    env = env if env is not None else os.environ
    return str(env.get(ENV_SWITCH, "")).strip().lower() not in ("off", "0", "false", "no", "non", "disabled")


def max_attempts(default=3, env=None):
    """Rewrite budget before the loud forced pass (anti-loop). MGM_AGENCY_MAX_ATTEMPTS overrides."""
    env = env if env is not None else os.environ
    try:
        n = int(str(env.get(ENV_MAX_ATTEMPTS, "")).strip())
        return n if n >= 1 else default
    except ValueError:
        return default


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Deterministic AGENCY-01/02/03 check on a draft.")
    ap.add_argument("--declared", default=os.environ.get("MGM_DECLARED", ""))
    ap.add_argument("--draft", default=None)
    ap.add_argument("--file", default=None)
    ap.add_argument("--pc", action="append", default=[], help="player-character name (repeatable)")
    a = ap.parse_args()
    if a.draft is not None:
        txt = a.draft
    elif a.file:
        txt = open(a.file, encoding="utf-8").read()
    else:
        txt = sys.stdin.read()
    report = analyze(txt, a.declared, a.pc)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report["ok"] else 1)
