#!/usr/bin/env python3
"""
turn_state.py — Turn state machine for pacing: the fast-forward grant (TURN-01/02/06).

WHY THIS EXISTS
    The pacing protocol was written by the player himself, and until this module the
    fast-forward marker `⏩` had zero occurrence in the product: the single most repeated
    pacing failure of the 34-session corpus was unenforced and even undeclared
    (`docs/10-field-report.md` §2, §7 P0-2). A rule that is only written down gets
    violated again — so the part of TURN-01/02/06 that a machine can decide is decided
    here, deterministically, and the refusal is not fail-open.

    Rules enforced (verbatim IDs from `references/locked-lessons.md`):
      • TURN-01  one non-ordinary moment = one STOP = one logged action.
      • TURN-02  advance in time or space ONLY after an explicit fast-forward signal —
                 a discussion, a question or an intention is NOT one — and ask before
                 any ellipse longer than about an hour of game time.
      • TURN-06  a fast-forward lands on ONE focal event: never two ellipses in a row.
    TURN-04 (silence is a decision) and TURN-05 (decision-STOP vs event-STOP) shape the
    transitions below but stay prompt-applied: no machine can read a silence's intent.

STATE TABLE
    The state and the grant are persisted per turn, with the rest of the turn state,
    in `.banquier/snap-<session_id>.json` (same store as `attempts_inc`/`set_pending`).

      state                  meaning
      ─────────────────────  ──────────────────────────────────────────────────────────
      awaiting_input         turn boundary: the player has spoken, nothing narrated yet
      decision_stop          narration delivered, the GM waits for the player  (TURN-05)
      event_stop             narration delivered, the world acts on its own    (TURN-05)
      fast_forward_granted   an explicit signal is armed; ONE narration may ellipse

TRANSITIONS
      from                   event                                → to                    side effect
      ─────────────────────  ───────────────────────────────────  ─────────────────────  ─────────────
      any                    input classified `fast_forward`      → fast_forward_granted  grant armed
      any                    input `question`/`intention`/        → awaiting_input        grant CLEARED
                             `discussion`/`action`                                        (TURN-02)
      any                    input `silence`                      → unchanged stop state  grant CLEARED
                                                                    (or awaiting_input)   (TURN-04)
      fast_forward_granted   narration ACCEPTED                   → decision_stop |        grant CONSUMED
                                                                    event_stop
      awaiting_input |       narration ACCEPTED                   → decision_stop |        —
      decision_stop |                                               event_stop
      event_stop
      any                    narration REFUSED                    → unchanged             grant kept
                                                                                          (rewrite may retry)

    Two invariants the tests pin down:
      1. the grant is consumed by the turn that uses it — an accepted narration always
         consumes it, used or not, so it can never silently authorise the next turn;
      2. a refusal never consumes it — the GM rewrites and resubmits the same turn.

WHAT COUNTS AS A SIGNAL (the grant is EXPLICIT, or it is not a grant)
    `⏩` and the `!ff`/`!ellipse` commands are read anywhere in the message. Everything
    else — "avance rapide", "passe à la suite", "fast forward", "skip ahead" — must OPEN
    the message (its first clause), because that is the only way to tell an instruction
    addressed to the GM from an action declared by the player. A verb alone can never be
    a signal: "j'avance vers la porte", "on avance prudemment dans le couloir", "je saute
    la barrière", "I move on to the next room" are ORDINARY ACTIONS and are classified as
    such — matching them as a substring is exactly the fail-open this module exists to
    remove, since it would hand a three-hour ellipse to a two-metre walk. When in doubt
    the message is an action: an ellipse then costs one refusal, where a wrong grant
    costs a silent violation of the rule the player wrote himself.

WHAT IS ENFORCED, AND WHAT IS NOT (do not overclaim)
    Enforced deterministically, on the narration draft, dialogue masked out:
      • temporal ellipse markers resolving to MORE than ~1 hour of game time
        ("trois heures plus tard", "une heure et demie plus tard", "2h plus tard",
        "le lendemain", "the next morning", "days pass"), and ONLY when the marker opens
        a sentence, which is where an ellipse sits — mid-sentence the same words are
        backstory or distance ("le village a brûlé deux ans après la guerre", "à quelques
        jours de marche d'ici") and refusing those refuses legitimate world-building;
        an explicit sub-hour jump ("quelques instants plus tard", "une heure plus tard")
        is deliberately NOT an ellipse — TURN-02 sets the bar at about an hour;
      • space advance markers (arrival / return / setting out) — the modal French
        "arriver à + infinitif" ("vous arrivez à ouvrir la porte" = you manage to) is
        excluded: it is not movement;
      • the count of those moments in a single narration (TURN-01) and the
        "never two ellipses in a row" clause (TURN-06).
    NOT enforced here, and left to the prompt or to another gate:
      • whether a moment is "non-ordinary" in the narrative sense — only its marker is read;
      • an ellipse carried by pure implication, with no marker at all;
      • an UNQUANTIFIED "plus tard" / "later": it cannot be placed against the one-hour
        bar ("un peu plus tard" is minutes, "plus tard" alone can be a day), so it is
        deliberately let through — a narrow check that is honest beats a broad one that
        refuses legitimate turns;
      • a duration marker that does NOT open a sentence ("vous repartez après deux jours
        de repos") — see above: the position is what distinguishes a jump from a fact;
      • a plain-language fast-forward request buried mid-message ("bon, je réfléchis, et
        sinon avance rapide") — use `⏩`, it is read anywhere;
      • stacked PC actions and PC dialogue — that is AGENCY-01/02/03, owned by the
        agency gate in `hooks/mj_checkpoint.py`;
      • decision-STOP vs event-STOP (TURN-05): the caller declares it, nothing reads it.

NEVER LOOPS (same contract as `hooks/mj_checkpoint.py`)
    A refusal costs one attempt. After `gate_max_tentatives` attempts on the same turn
    the narration is FORCED through (`ok` stays True, `forced` is set): the remaining
    violations are logged to `.banquier/scoreboard.json` under the `turn_gate` key and
    re-injected next turn via `set_pending`. A false refusal therefore costs at most N
    rewrites, never a dead campaign. The attempt counter is this module's own
    (`turn_gate_attempts`) — sharing `checkpoint_attempts` would let one gate reset the
    other's budget.

OPERATOR ESCAPE HATCH
    `MGM_TURN_GATE=0` (or world.json > `meta.hooks.turn_gate: false`) disables the
    refusal for a live campaign; the verdict then carries `_skipped` and the state is
    still tracked. Default: ON. Budget: `meta.hooks.turn_gate_max_tentatives`
    (falls back to the judge's `gate_max_tentatives`, default 2).

USAGE (from the campaign cwd)
    echo "<narration draft>" | python3 .../turn_state.py check --declared "<player input>"
    python3 .../turn_state.py signal --message "⏩"     # arm/clear the grant explicitly
    python3 .../turn_state.py state                    # inspect, prints JSON
    python3 .../turn_state.py reset                    # clear state + grant
  Exit codes for `check`: 0 = deliver, 1 = refused (rewrite, then resubmit).

INTEGRATION (read this before wiring it in)
    Today this module is a SECOND command the GM runs alongside `mj_checkpoint.py`; it is
    not called from anywhere in the repository yet. The one-line hand-off, for whoever
    merges the two gates:

        v = turn_state.check_narration(camp, payload, draft, args.declared)
        violations = v["violations"] + violations   # deterministic first, judge after

    put right before `mj_checkpoint.main()` computes `n = L.attempts_inc(...)`, and its
    own attempt budget dropped in favour of the checkpoint's. `declared` MUST be the
    player's VERBATIM message: it is the only thing that can arm a grant — omit it and
    no `⏩` is ever seen, so every ellipse is refused.
    Violations use the SAME shape as `hooks/llm_judge.py`
    ({"domaine","regle","extrait","pourquoi","correction"}) so the checkpoint can feed
    them to its existing `format_feedback` / `scoreboard_update` without adaptation.
"""
import argparse
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402

# ── States, thresholds, snapshot keys ───────────────────────────────────────

AWAITING_INPUT = "awaiting_input"
DECISION_STOP = "decision_stop"
EVENT_STOP = "event_stop"
FF_GRANTED = "fast_forward_granted"
STATES = (AWAITING_INPUT, DECISION_STOP, EVENT_STOP, FF_GRANTED)

K_STATE = "turn_state"
K_GRANT = "turn_ff_grant"
K_ATTEMPTS = "turn_gate_attempts"    # this gate's own budget, NOT the checkpoint's
SCOREBOARD_KEY = "turn_gate"

ELLIPSE_THRESHOLD_MIN = 60          # TURN-02: "about an hour of game time"
MAX_MOMENTS_WITHOUT_GRANT = 1       # TURN-01: one moment = one STOP
DEFAULT_MAX_ATTEMPTS = 2

# ── Player input signals — data-driven, bilingual, matched on folded text ────

FF_MARKERS = ("⏩",)
FF_COMMANDS = ("!ff", "!avance", "!fast-forward", "!fastforward", "!ellipse")

# Anchored at the start of the first clause (see `_leading_clause`), never as a
# substring: no bare verb can be listed here, "on avance" is an action, not a request.
FF_PHRASES = (
    # FR
    r"avanc(?:e|ons)\s+rapide\b",
    r"ellipse\b",
    r"fais(?:ons)?\s+une\s+ellipse\b",
    r"pass(?:e|ons)\s+a\s+la\s+suite\b",
    r"saut(?:e|ons)\s+jusqu",
    # EN
    r"fast[-\s]?forward\b",
    r"skip\s+(?:ahead|forward|to)\b",
    r"jump\s+(?:ahead|forward|to)\b",
    r"time\s+skip\b",
)

# Discourse openers stripped before anchoring, so "ok, avance rapide" still reads as one.
_RE_LEAD_FILLER = re.compile(
    r"^[\s\W_]*(?:(?:ok|okay|bon|bien|d'accord|alors|allez|allons|et|puis|donc|"
    r"please|stp|svp|mj|gm)\b[\s,]*)*")
_RE_CLAUSE_END = re.compile(r"[.!?;:\n]")

# Checked BEFORE FF_PHRASES, so "je vais passer à la suite" stays an intention (TURN-02).
INTENTION_PATTERNS = (
    r"\bje\s+(?:vais|voudrais|veux|compte|comptais|pense|souhaite|aimerais|prevois)\b",
    r"\bj'(?:aimerais|irai|irais|envisage)\b",
    r"\bon\s+(?:pourrait|devrait|va\s+peut-etre)\b",
    r"\bi(?:'m|\s+am)\s+going\s+to\b",
    r"\bi\s+(?:will|want|plan|intend|would\s+like|wanna|think\s+i)\b",
    r"\bi'd\s+like\b",
    r"\bwe\s+(?:could|should)\b",
    r"\bmaybe\s+i\b",
)

INPUT_KINDS = ("fast_forward", "question", "intention", "action", "discussion", "silence")

# ── Non-ordinary moment markers, read on the narration draft ─────────────────

_QTY = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6,
    "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "douze": 12, "quinze": 15,
    "quelques": 3, "plusieurs": 3, "de longues": 3, "de longs": 3,
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "several": 3, "a few": 3,
}

_UNITS_MIN = {
    "seconde": 1 / 60.0, "secondes": 1 / 60.0, "second": 1 / 60.0, "seconds": 1 / 60.0,
    "instant": 0.5, "instants": 0.5, "moment": 0.5, "moments": 0.5,
    "minute": 1, "minutes": 1, "min": 1, "mn": 1,
    "heure": 60, "heures": 60, "hour": 60, "hours": 60, "h": 60, "hr": 60, "hrs": 60,
    "jour": 1440, "jours": 1440, "journee": 1440, "journees": 1440, "j": 1440,
    "day": 1440, "days": 1440,
    "semaine": 10080, "semaines": 10080, "week": 10080, "weeks": 10080,
    "mois": 43200, "month": 43200, "months": 43200,
    "annee": 525600, "annees": 525600, "an": 525600, "ans": 525600,
    "year": 525600, "years": 525600,
}

_HALF_FRAC = {"demi": 0.5, "demie": 0.5, "demis": 0.5, "demies": 0.5,
              "quart": 0.25, "quarts": 0.25}

_ALT_QTY = "|".join(re.escape(k) for k in sorted(_QTY, key=len, reverse=True))
_ALT_UNIT = "|".join(re.escape(k) for k in sorted(_UNITS_MIN, key=len, reverse=True))
_ALT_HALF = "|".join(re.escape(k) for k in sorted(_HALF_FRAC, key=len, reverse=True))
_ALT_AFTER = r"plus\s+tard|ecoulen?t|s'ecoulen?t|passent|passerent|later|" \
             r"pass|passed|go\s+by|went\s+by|elapse[ds]?"
_ALT_BEFORE = r"apres|au\s+bout\s+de|after|following"

# An ellipse OPENS a sentence. Mid-sentence, the same duration is backstory or a
# distance ("le village a brûlé deux ans après la guerre") and moves no clock.
_SENT_START = r"(?:^|(?<=[.!?…\n]))[\s\"«»“”'\-—–*_]*"
_QTY_UNIT = (r"\b(?P<q>\d+|" + _ALT_QTY + r")\s*(?P<u>" + _ALT_UNIT + r")\b"
             r"(?:\s+et\s+(?P<h>" + _ALT_HALF + r")\b)?")

RE_DUREE_POST = re.compile(          # "Trois heures plus tard", "Quelques jours passent"
    _SENT_START + _QTY_UNIT + r"[^.!?\n]{0,30}?\b(?:" + _ALT_AFTER + r")\b")
RE_DUREE_PRE = re.compile(           # "Après trois heures de marche", "After two days"
    _SENT_START + r"\b(?:" + _ALT_BEFORE + r")\s+" + _QTY_UNIT)

# Jumps of more than an hour that carry no quantity of their own.
NAMED_ELLIPSES = (
    r"\ble\s+lendemain\b",
    r"\ble\s+surlendemain\b",
    r"\ble\s+jour\s+suivant\b",
    r"\bla\s+(?:semaine|nuit)\s+suivante\b",
    r"\bau\s+petit\s+matin\b",
    r"\b(?:des|les)\s+jours\s+passent\b",
    r"\bla\s+nuit\s+passe\b",
    r"\bthe\s+next\s+(?:morning|day)\b",
    r"\bthe\s+following\s+(?:morning|day|week)\b",
    r"\bdays\s+pass\b",
    r"\bovernight\b",
    r"\bby\s+(?:nightfall|dawn|morning)\b",
)

TRAVEL_MARKERS = (                   # space advance: arrival, return, setting out
    # "arriver à + infinitif" = to manage to, not to move: excluded by the lookahead.
    r"\b(?:vous|tu)\s+arriv(?:ez|es)\b(?!\s+a\s+\w+(?:er|ir|re)\b)",
    r"\b(?:vous|tu)\s+atteign(?:ez|s)\b",
    r"\bde\s+retour\s+(?:a|au|aux|chez|dans|sur)\b",
    r"\bvous\s+voila\s+(?:a|au|devant|dans)\b",
    r"\ble\s+(?:chemin|sentier|la\s+route)\s+(?:vous|te)\s+mene\b",
    r"\bvous\s+(?:reprenez|prenez)\s+la\s+route\b",
    r"\byou\s+(?:arrive|reach)\b",
    r"\bback\s+(?:at|in|on)\s+the\b",
    r"\bthe\s+road\s+(?:takes|leads|brings)\s+you\b",
)

_RE_NAMED = [re.compile(p) for p in NAMED_ELLIPSES]
_RE_TRAVEL = [re.compile(p) for p in TRAVEL_MARKERS]
_RE_INTENTION = [re.compile(p) for p in INTENTION_PATTERNS]
_RE_FF = [re.compile(p) for p in FF_PHRASES]

_RE_QUOTED = re.compile(r"«[^»]*»|“[^”]*”|\"[^\"\n]*\"")
_RE_DASHLINE = re.compile(r"(?m)^[ \t]*[—–][ \t].*$")


# ── Text folding (accents, case, apostrophes) with an index map back ─────────


def _mask_dialogue(text):
    """Blanks quoted/dashed dialogue, preserving length so offsets stay valid.

    What a character SAYS about tomorrow does not move the clock — masking dialogue is
    what keeps "je partirai le lendemain" from reading as an ellipse. The blank ends on a
    "." so that a line of dialogue still closes a sentence for the ellipse anchor.
    """
    def blank(m):
        return " " * (m.end() - m.start() - 1) + "."
    return _RE_DASHLINE.sub(blank, _RE_QUOTED.sub(blank, text or ""))


def _fold(text):
    """Lowercase + strip diacritics. Returns (folded, index map folded→original)."""
    out, idx = [], []
    for i, ch in enumerate(text or ""):
        if ch in "’ʼ‘":
            ch = "'"
        for c in unicodedata.normalize("NFD", ch):
            if unicodedata.category(c) == "Mn":  # accents AND the ⏩️ variation selector
                continue
            out.append(c.lower())
            idx.append(i)
    return "".join(out), idx


def _excerpt(original, idx, start, end, pad=28):
    """Readable excerpt of the ORIGINAL text around a match found on the folded one."""
    if not idx:
        return ""
    a = idx[max(0, start)] if start < len(idx) else len(original)
    b = (idx[end - 1] + 1) if 0 < end <= len(idx) else len(original)
    frag = original[max(0, a - pad):min(len(original), b + pad)]
    return L.truncate(frag, 160)


# ── Player input classification ──────────────────────────────────────────────


def _leading_clause(folded):
    """The message's first clause, stripped of punctuation and discourse openers."""
    return _RE_LEAD_FILLER.sub("", _RE_CLAUSE_END.split(folded, maxsplit=1)[0]).strip()


def classify_input(message):
    """Classifies a player input → (kind, matched signal). See INPUT_KINDS.

    Order matters and encodes TURN-02: the canonical marker wins, then a question or an
    intention DISQUALIFIES the message whatever else it contains, then the explicit
    phrases — and those only when they OPEN the message, so an action declared in the
    present tense ("j'avance vers la porte") can never pass for a grant.
    """
    raw = message if isinstance(message, str) else ""
    if not raw.strip():
        return "silence", ""
    folded, _ = _fold(raw)
    for mk in FF_MARKERS:
        if mk in folded:
            return "fast_forward", mk
    for cmd in FF_COMMANDS:
        if cmd in folded:
            return "fast_forward", cmd
    if "?" in raw:
        return "question", "?"
    for rx in _RE_INTENTION:
        m = rx.search(folded)
        if m:
            return "intention", m.group(0)
    clause = _leading_clause(folded)
    for rx in _RE_FF:
        m = rx.match(clause)
        if m:
            return "fast_forward", m.group(0)
    return "action", ""


# ── Non-ordinary moment detection ────────────────────────────────────────────


def _duration_minutes(qty, unit, half=None):
    try:
        q = float(qty) if str(qty).isdigit() else float(_QTY.get(qty, 1))
    except Exception:
        q = 1.0
    return (q + _HALF_FRAC.get(half or "", 0.0)) * float(_UNITS_MIN.get(unit, 0))


def detect_moments(draft):
    """Marker-level detection of non-ordinary moments in a narration draft.

    Returns a list of {"kind": "ellipse"|"travel", "marker", "excerpt", "minutes"},
    ordered by position, overlapping matches collapsed. Scope and known misses are
    stated in the module docstring — this reads MARKERS, not meaning.
    """
    original = draft if isinstance(draft, str) else ""
    folded, idx = _fold(_mask_dialogue(original))
    found = []

    def add(kind, m, minutes=None):
        found.append({
            "kind": kind, "marker": m.group(0).strip(),
            "start": m.start(), "end": m.end(),
            "excerpt": _excerpt(original, idx, m.start(), m.end()),
            "minutes": minutes,
        })

    for rx in (RE_DUREE_POST, RE_DUREE_PRE):
        for m in rx.finditer(folded):
            minutes = _duration_minutes(m.group("q"), m.group("u"), m.group("h"))
            # TURN-02 sets the bar at "about an hour": below it, no grant is needed.
            if minutes > ELLIPSE_THRESHOLD_MIN:
                add("ellipse", m, minutes)
    for rx in _RE_NAMED:
        for m in rx.finditer(folded):
            add("ellipse", m, None)
    for rx in _RE_TRAVEL:
        for m in rx.finditer(folded):
            add("travel", m, None)

    found.sort(key=lambda d: (d["start"], -d["end"]))
    out, last_end = [], -1
    for d in found:
        if d["start"] < last_end:  # overlapping markers = one moment
            continue
        last_end = d["end"]
        out.append({k: d[k] for k in ("kind", "marker", "excerpt", "minutes")})
    return out


# ── Persisted state & grant (.banquier/snap-<sid>.json, via _lib) ────────────


def get_state(camp, payload):
    v = L.snap_get(camp, payload, K_STATE)
    return v if v in STATES else AWAITING_INPUT


def set_state(camp, payload, state):
    L.snap_set(camp, payload, K_STATE, state if state in STATES else AWAITING_INPUT)


def grant_get(camp, payload):
    """The armed, unconsumed grant, or None."""
    g = L.snap_get(camp, payload, K_GRANT)
    if isinstance(g, dict) and g.get("armed"):
        return g
    return None


def grant_arm(camp, payload, signal):
    g = {"armed": True, "signal": signal or "⏩", "ts": L.now_iso()}
    L.snap_set(camp, payload, K_GRANT, g)
    return g


def grant_clear(camp, payload, reason=""):
    L.snap_set(camp, payload, K_GRANT, {"armed": False, "reason": reason,
                                        "ts": L.now_iso()})


def attempts_get(camp, payload):
    v = L.snap_get(camp, payload, K_ATTEMPTS)
    return int(v) if isinstance(v, int) else 0


def attempts_inc(camp, payload):
    n = attempts_get(camp, payload) + 1
    L.snap_set(camp, payload, K_ATTEMPTS, n)
    return n


def attempts_reset(camp, payload):
    L.snap_set(camp, payload, K_ATTEMPTS, 0)


def reset(camp, payload):
    set_state(camp, payload, AWAITING_INPUT)
    grant_clear(camp, payload, "reset")
    attempts_reset(camp, payload)


# ── Transitions ──────────────────────────────────────────────────────────────


def observe_input(camp, payload, message):
    """Applies a player input to the machine. Arms or CLEARS the grant, never keeps it.

    A question, an intention, a discussion, an action or a silence all clear a pending
    grant: a permission granted for one turn cannot survive into the next (TURN-02),
    and a silence is a decision to follow the default flow, not permission (TURN-04).
    """
    kind, signal = classify_input(message)
    if kind == "fast_forward":
        grant_arm(camp, payload, signal)
        state = FF_GRANTED
    else:
        grant_clear(camp, payload, kind)
        current = get_state(camp, payload)
        # TURN-04: a silence leaves the player exactly where he was — at the STOP.
        if kind == "silence" and current in (DECISION_STOP, EVENT_STOP):
            state = current
        else:
            state = AWAITING_INPUT
    set_state(camp, payload, state)
    return {"input": kind, "signal": signal, "state": state,
            "grant": kind == "fast_forward"}


# ── Verdict ──────────────────────────────────────────────────────────────────


def gate_enabled(monde):
    """Operator escape hatch. world.json > meta.hooks.turn_gate > env MGM_TURN_GATE > True."""
    h = L.meta(monde).get("hooks")
    h = h if isinstance(h, dict) else {}
    env_default = L.as_bool(os.environ.get("MGM_TURN_GATE"), True)
    return L.as_bool(h.get("turn_gate"), env_default)


def gate_max_attempts(monde):
    """Anti-loop budget, mirroring the checkpoint's `gate_max_tentatives`."""
    h = L.meta(monde).get("hooks")
    h = h if isinstance(h, dict) else {}
    try:
        n = int(h.get("turn_gate_max_tentatives")
                or L.judge_config(monde).get("gate_max_tentatives")
                or DEFAULT_MAX_ATTEMPTS)
    except Exception:
        n = DEFAULT_MAX_ATTEMPTS
    return max(1, n)


def _violation(regle, extrait, pourquoi, correction):
    return {"domaine": "conduite", "regle": regle, "extrait": L.truncate(extrait, 160),
            "pourquoi": pourquoi, "correction": correction}


def _pair(a, b):
    """Two excerpts in one 160-char field — halved, so the second one survives."""
    return "1) %s — 2) %s" % (L.truncate(a["excerpt"], 70), L.truncate(b["excerpt"], 70))


def evaluate(moments, granted):
    """Pure rule evaluation: moments + grant → violations. No I/O, no state."""
    ellipses = [m for m in moments if m["kind"] == "ellipse"]
    violations = []
    if not granted:
        rest = list(moments)
        if ellipses:
            e = ellipses[0]
            rest.remove(e)
            violations.append(_violation(
                "TURN-02", e["excerpt"],
                "you advance time by more than about an hour without an explicit "
                "fast-forward signal (⏩ or its plain-language equivalent) — a discussion, "
                "a question or an intention is not one",
                "stay in the current moment and end on the state of the world, or ask "
                "\"what do you do?\" before the ellipse"))
        # Counted on what is left once the ellipse TURN-02 already named is cut:
        # otherwise the GM reads two numbered items for one single fault.
        if len(rest) > MAX_MOMENTS_WITHOUT_GRANT:
            a, b = rest[0], rest[1]
            violations.append(_violation(
                "TURN-01", _pair(a, b),
                "two non-ordinary moments crossed in one narration (%s: « %s » then "
                "%s: « %s ») — one moment = one STOP = one logged action"
                % (a["kind"], a["marker"], b["kind"], b["marker"]),
                "keep the first moment, cut everything after it, and STOP there"))
    elif len(ellipses) > 1:
        a, b = ellipses[0], ellipses[1]
        violations.append(_violation(
            "TURN-06", _pair(a, b),
            "the fast-forward is granted for ONE focal event, and you chained two "
            "ellipses (« %s » then « %s ») — never two ellipses in a row"
            % (a["marker"], b["marker"]),
            "summarise the routine, land on the FIRST meaningful event in a few "
            "sentences, then STOP"))
    return violations


def check_narration(camp, payload, draft, declared="", stop=DECISION_STOP, monde=None):
    """ENTRY POINT for the in-turn gate (`hooks/mj_checkpoint.py`).

    `declared` is the player input this narration answers: when given, it is run through
    the machine first, so the grant is armed by a `⏩` and cleared by a question or an
    intention in the very same call.

    Returns {"ok", "violations", "moments", "state", "input", "granted",
             "grant_consumed", "feedback", "attempts"} (+ "_skipped" when the gate is
     disabled, + "forced" when the budget ran out).
    A refusal NEVER consumes the grant — the GM rewrites and resubmits the same turn.
    """
    if monde is None:
        monde = L.load_monde(camp)
    obs = observe_input(camp, payload, declared) if declared else None
    granted = grant_get(camp, payload) is not None
    moments = detect_moments(draft)
    verdict = {
        "ok": True, "violations": [], "moments": moments,
        "input": (obs or {}).get("input", ""), "granted": granted,
        "grant_consumed": False, "state": get_state(camp, payload), "feedback": "",
        "attempts": 0, "max_attempts": gate_max_attempts(monde),
    }
    if not gate_enabled(monde):
        verdict["_skipped"] = "MGM_TURN_GATE off"
        return verdict

    violations = evaluate(moments, granted)
    if violations:
        n = attempts_inc(camp, payload)
        forced = n >= verdict["max_attempts"]
        L.scoreboard_update(camp, SCOREBOARD_KEY, False, 0, len(violations),
                            [v.get("regle", "?") for v in violations],
                            forced=1 if forced else 0)
        verdict["violations"] = violations
        verdict["attempts"] = n
        verdict["feedback"] = format_feedback(violations)
        if not forced:
            verdict["ok"] = False
            return verdict
        # Budget exhausted: the house rule is that a gate NEVER loops. The narration
        # goes out, the violations are logged and re-injected on the next turn.
        attempts_reset(camp, payload)
        verdict["forced"] = n
        L.set_pending(camp, payload, verdict["feedback"])
    else:
        attempts_reset(camp, payload)
        L.scoreboard_update(camp, SCOREBOARD_KEY, True, 0, 0, [])

    # The grant belonged to THIS turn: consume it used or not, so an unused grant can
    # never silently authorise the next narration.
    if granted:
        grant_clear(camp, payload, "consumed")
        verdict["grant_consumed"] = True
    new_state = stop if stop in (DECISION_STOP, EVENT_STOP) else DECISION_STOP
    set_state(camp, payload, new_state)
    verdict["state"] = new_state
    return verdict


def format_feedback(violations, prefix="⛔ PACING"):
    """Numbered, actionable feedback naming the rule ID and the moments detected."""
    if not violations:
        return ""
    lines = ["%s — narration refused. Correct it, then resubmit :" % prefix]
    for i, v in enumerate(violations, 1):
        lines.append("%d. [%s] Detected: %s. Problem: %s. Instead: %s"
                     % (i, v.get("regle", "?"), v.get("extrait", ""),
                        v.get("pourquoi", ""), v.get("correction", "")))
    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────────────────


def _payload(args):
    return {"cwd": os.getcwd(), "session_id": args.session}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Turn state machine — fast-forward grant.")
    ap.add_argument("--session", default=os.environ.get("MGM_SESSION_ID", "gate"),
                    help="turn state key (default: gate, like mj_checkpoint.py)")
    sub = ap.add_subparsers(dest="cmd")

    p_sig = sub.add_parser("signal", help="classify a player input, arm/clear the grant")
    p_sig.add_argument("--message", default="")

    p_chk = sub.add_parser("check", help="check a narration draft (stdin by default)")
    p_chk.add_argument("--declared", default=os.environ.get("MGM_DECLARED", ""))
    p_chk.add_argument("--file", default=None)
    p_chk.add_argument("--draft", default=None)
    p_chk.add_argument("--stop", choices=["decision", "event"], default="decision",
                       help="TURN-05: kind of STOP this narration ends on")
    p_chk.add_argument("--json", action="store_true", help="print the raw verdict")

    sub.add_parser("state", help="print the persisted state and grant")
    sub.add_parser("reset", help="clear the state and the grant")

    args = ap.parse_args(argv)
    camp = L.campaign_dir({"cwd": os.getcwd()})
    payload = _payload(args)

    if args.cmd == "signal":
        out = observe_input(camp, payload, args.message)
        print(json.dumps(out, ensure_ascii=False))
        return 0

    if args.cmd == "state":
        print(json.dumps({"state": get_state(camp, payload),
                          "grant": grant_get(camp, payload)}, ensure_ascii=False))
        return 0

    if args.cmd == "reset":
        reset(camp, payload)
        print("state reset")
        return 0

    if args.cmd != "check":
        ap.print_help()
        return 2

    if args.draft is not None:
        draft = args.draft
    elif args.file:
        try:
            draft = open(args.file, encoding="utf-8").read()
        except Exception:
            print("⚠️ TURN: unreadable draft — deliver your narration.")
            return 0
    else:
        draft = sys.stdin.read()

    stop = EVENT_STOP if args.stop == "event" else DECISION_STOP
    verdict = check_narration(camp, payload, draft, args.declared, stop)
    if args.json:
        print(json.dumps(verdict, ensure_ascii=False))
        return 0 if verdict["ok"] else 1
    if "_skipped" in verdict:
        print("✅ TURN (gate off: %s) — deliver your narration." % verdict["_skipped"])
        return 0
    if "forced" in verdict:
        print("⚠️ TURN FORCED after %d attempts — correct as best you can and DELIVER "
              "(remaining violations logged):\n%s" % (verdict["forced"],
                                                      verdict["feedback"]))
        return 0
    if verdict["ok"]:
        detail = " (⏩ grant consumed)" if verdict["grant_consumed"] else ""
        print("✅ TURN OK — pacing rules respected%s. Deliver your narration." % detail)
        return 0
    print("%s\n\n➡️ Rewrite your narration then re-run the check (attempt %d/%d)."
          % (verdict["feedback"], verdict["attempts"], verdict["max_attempts"]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
