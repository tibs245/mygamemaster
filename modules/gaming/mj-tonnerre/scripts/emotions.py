#!/usr/bin/env python3
"""
emotions.py — Character emotional state with LOGICAL, event-driven evolution.

Purpose (skill `mj-tonnerre-emotions`): give the GM a compact, legible and
EXPLAINABLE emotional state per character (primarily NPCs, optionally PCs),
so portrayal stays consistent across sessions. The model is deliberately
small (no over-engineering):

  * 6 core emotions, intensities 0..1 — `joie` (joy), `confiance` (trust),
    `peur` (fear), `colere` (anger), `tristesse` (sadness), `surprise`.
    Plutchik-inspired palette: `confiance` is kept because trust drives most
    ally/hostile dynamics at the table; `surprise` is kept for shocks but
    decays much faster than the rest (it is transient by nature).
  * `temperament` — the character's baseline (who they are when nothing is
    happening). The current state DECAYS toward it as time passes.
  * `historique` — short, capped journal of every shift (event, deltas,
    reason, session) so a change is never arbitrary: it can be explained.

Evolution is deterministic: a named EVENT (betrayal, kindness, threat…) maps
to a fixed delta table (EVENT_RULES), optionally scaled by an intensity
factor; free-form `adjust` requires an explicit reason. Decay pulls each
emotion a fraction of the way back to temperament.

Persistence: the `emotions` object inside the character sheet —
`pnj.json` for NPCs (canonical), `personnages/*.json` for opt-in PCs.
Keys stay consistent with the sibling French data keys (`faits_etablis`,
`hypotheses_mj`…): `etat`, `temperament`, `historique`.

FAIL-OPEN: a character without an `emotions` object simply has no emotional
output (summary skips them, get says so); `summary` always exits 0 so the
pre_llm_call hook can never break a turn because of this module.

Usage:
  python3 emotions.py get <campagne> <nom> [--json]
  python3 emotions.py init <campagne> <nom> [emo=val ...] [--force]
  python3 emotions.py apply <campagne> <nom> --event EVENT [--intensity F]
                      [--reason TXT] [--session N]
  python3 emotions.py adjust <campagne> <nom> emo=±delta [...] --reason TXT
                      [--session N]
  python3 emotions.py decay <campagne> [<nom>] [--rate F] [--session N]
  python3 emotions.py summary <campagne> [--max N]
  python3 emotions.py list-events

Exit codes:
  0  OK (`summary` ALWAYS exits 0 — fail-open for the hook)
  1  character not found / ambiguous / unknown event / already initialized
  2  usage error (campaign or sheet file not found, bad delta syntax)

Stdlib only, no network. Importable for tests and siblings:
`from emotions import apply_event, decay_state, summary_line, …`.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
try:
    import worldlib as W  # charger_json(), chemin_campagne() — loader helpers
    _load_json = W.charger_json
    _resolve = W.chemin_campagne
except Exception:  # fail-open: standalone if worldlib is unavailable
    def _load_json(path, default=None):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except (OSError, json.JSONDecodeError, ValueError):
            return default

    def _resolve(arg):
        return Path(arg).expanduser().resolve()


# ════════════════════════════════════════════════════════════════════════════
#  Model constants
# ════════════════════════════════════════════════════════════════════════════

# The palette. Order matters only for display.
EMOTIONS = ("joie", "confiance", "peur", "colere", "tristesse", "surprise")

# Neutral disposition used when a character is initialized without explicit
# temperament: mildly warm, slightly cautious, never pre-surprised.
DEFAULT_TEMPERAMENT = {
    "joie": 0.3, "confiance": 0.3, "peur": 0.2,
    "colere": 0.1, "tristesse": 0.2, "surprise": 0.0,
}

DEFAULT_DECAY_RATE = 0.5     # one decay step ≈ one session gap / big time skip
SURPRISE_MIN_DECAY = 0.8     # surprise is transient: decays at least this fast
HISTORY_MAX = 20             # explainability journal cap (oldest dropped)
DEVIATION_THRESHOLD = 0.15   # |state − temperament| worth surfacing to the GM
SUMMARY_MAX_CHARS = 180      # one line per character, hard cap
SUMMARY_MAX_DEFAULT = 6      # characters shown in the injected summary block
DECAY_HISTORY_MIN = 0.05     # decay is journaled only if something moved

# Deterministic update rules: named event → emotion deltas (before intensity
# scaling and 0..1 clamping). The lexicon is intentionally small and additive:
# an unlisted situation is handled with `adjust` + a mandatory reason.
EVENT_RULES = {
    "betrayal":             {"confiance": -0.40, "colere": +0.30, "peur": +0.15,
                             "tristesse": +0.20, "surprise": +0.30},
    "deception_discovered": {"confiance": -0.35, "colere": +0.25, "surprise": +0.25},
    "promise_broken":       {"confiance": -0.30, "colere": +0.20, "tristesse": +0.10},
    "promise_kept":         {"confiance": +0.25, "joie": +0.10},
    "kindness":             {"confiance": +0.15, "joie": +0.10},
    "gift":                 {"joie": +0.15, "confiance": +0.10, "surprise": +0.10},
    "rescue":               {"confiance": +0.30, "joie": +0.20, "peur": -0.25},
    "threat":               {"peur": +0.30, "colere": +0.15, "confiance": -0.15},
    "attack":               {"peur": +0.40, "colere": +0.35, "confiance": -0.30,
                             "surprise": +0.20},
    "insult":               {"colere": +0.25, "confiance": -0.10, "joie": -0.10},
    "comfort":              {"tristesse": -0.20, "peur": -0.15, "confiance": +0.15},
    "loss":                 {"tristesse": +0.40, "joie": -0.25, "surprise": +0.10},
    "reunion":              {"joie": +0.25, "tristesse": -0.20, "surprise": +0.15},
    "victory":              {"joie": +0.30, "confiance": +0.10, "peur": -0.20},
    "good_news":            {"joie": +0.20, "surprise": +0.15},
    "bad_news":             {"tristesse": +0.20, "peur": +0.15, "surprise": +0.15},
}

# Dominant-emotion tone word for the one-line summary (GM-facing, English —
# it describes HOW to play the character, it is never shown to players).
TONE_LABELS = {
    "joie": "cheerful", "confiance": "trusting", "peur": "fearful",
    "colere": "angry", "tristesse": "sorrowful", "surprise": "startled",
}
TONE_THRESHOLD = 0.5  # below this, the character reads as "composed"


# ════════════════════════════════════════════════════════════════════════════
#  Pure model functions (importable, no I/O)
# ════════════════════════════════════════════════════════════════════════════

def clamp01(value) -> float:
    """Clamps to [0, 1] and rounds to 3 decimals (legible JSON)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0.0
    return round(max(0.0, min(1.0, v)), 3)


def normalize_state(raw, fallback=None) -> dict:
    """Full palette dict with clamped floats. Missing/garbage → `fallback`
    (default: DEFAULT_TEMPERAMENT) per emotion. Never raises."""
    base = dict(DEFAULT_TEMPERAMENT if fallback is None else fallback)
    src = raw if isinstance(raw, dict) else {}
    out = {}
    for emo in EMOTIONS:
        v = src.get(emo, base.get(emo, 0.0))
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            v = base.get(emo, 0.0)
        out[emo] = clamp01(v)
    return out


def apply_deltas(state: dict, deltas: dict, intensity: float = 1.0):
    """Applies raw deltas × intensity, clamped to [0, 1].
    Returns (new_state, applied) where `applied` holds the EFFECTIVE deltas
    (post-clamping) — what actually changed, for the history journal."""
    try:
        factor = float(intensity)
    except (TypeError, ValueError):
        factor = 1.0
    new = dict(state)
    applied = {}
    for emo, d in (deltas or {}).items():
        if emo not in EMOTIONS:
            continue
        if isinstance(d, bool) or not isinstance(d, (int, float)):
            continue
        before = clamp01(new.get(emo, 0.0))
        after = clamp01(before + d * factor)
        if after != before:
            applied[emo] = round(after - before, 3)
        new[emo] = after
    return new, applied


def apply_event(state: dict, event: str, intensity: float = 1.0):
    """Applies a NAMED event from EVENT_RULES. Raises KeyError if unknown
    (callers decide whether to fail or fall back)."""
    rule = EVENT_RULES[str(event)]
    return apply_deltas(state, rule, intensity)


def decay_state(state: dict, temperament: dict, rate: float = DEFAULT_DECAY_RATE) -> dict:
    """Moves each emotion a fraction `rate` of the way back to temperament
    (e ← e + rate·(baseline − e)). `surprise` decays at least at
    SURPRISE_MIN_DECAY (shock does not linger). rate is clamped to [0, 1]."""
    try:
        r = max(0.0, min(1.0, float(rate)))
    except (TypeError, ValueError):
        r = DEFAULT_DECAY_RATE
    new = {}
    for emo in EMOTIONS:
        e = clamp01(state.get(emo, 0.0))
        b = clamp01(temperament.get(emo, DEFAULT_TEMPERAMENT.get(emo, 0.0)))
        r_emo = max(r, SURPRISE_MIN_DECAY) if emo == "surprise" else r
        new[emo] = clamp01(e + r_emo * (b - e))
    return new


def _fmt(value: float) -> str:
    """0.65 → '.65', 1.0 → '1', 0.0 → '0' (compact, scene_brief style)."""
    v = clamp01(value)
    if v >= 1.0:
        return "1"
    txt = ("%.2f" % v).rstrip("0").rstrip(".")
    return txt[1:] if txt.startswith("0.") else (txt or "0")


def _last_shift(emo_obj: dict) -> str:
    """Short '«reason» (S<N>)' from the most recent history entry, or ''."""
    hist = emo_obj.get("historique")
    if not isinstance(hist, list) or not hist:
        return ""
    last = hist[-1]
    if not isinstance(last, dict):
        return ""
    reason = str(last.get("raison") or last.get("evenement") or "").strip()
    if not reason:
        return ""
    sess = last.get("session")
    suffix = " (S%s)" % sess if sess not in (None, "") else ""
    return reason + suffix


def summary_line(fiche: dict) -> str:
    """One GM-facing line: tone word + emotions deviating from temperament
    (top 3, with ▲/▼ vs baseline) + the latest journaled reason.
    Returns '' when the sheet carries no usable `emotions` object (fail-open)."""
    if not isinstance(fiche, dict):
        return ""
    emo = fiche.get("emotions")
    if not isinstance(emo, dict):
        return ""
    if not isinstance(emo.get("etat"), dict) and not isinstance(emo.get("temperament"), dict):
        return ""
    temperament = normalize_state(emo.get("temperament"))
    state = normalize_state(emo.get("etat"), fallback=temperament)
    name = (fiche.get("nom")
            or (fiche.get("meta") or {}).get("nom_perso")
            or "?")

    dominant = max(EMOTIONS, key=lambda e: state[e])
    tone = TONE_LABELS[dominant] if state[dominant] >= TONE_THRESHOLD else "composed"

    deviations = sorted(
        ((e, round(state[e] - temperament[e], 3)) for e in EMOTIONS),
        key=lambda kv: (-abs(kv[1]), EMOTIONS.index(kv[0])),
    )
    shown = [(e, d) for e, d in deviations if abs(d) >= DEVIATION_THRESHOLD][:3]

    line = "• %s — %s" % (name, tone)
    if shown:
        bits = ", ".join("%s %s%s" % (e, _fmt(state[e]), "▲" if d > 0 else "▼")
                         for e, d in shown)
        line += " (%s)" % bits
    last = _last_shift(emo)
    if last:
        line += " ; last shift: %s" % last
    if len(line) > SUMMARY_MAX_CHARS:
        line = line[:SUMMARY_MAX_CHARS - 1].rstrip() + "…"
    return line


def summary_block(fiches: list, max_chars: int | None = None,
                  max_npc: int = SUMMARY_MAX_DEFAULT) -> str:
    """Compact block for context injection: header + one line per character
    that HAS emotion data (others are skipped — fail-open, no context bloat).
    Ordering: most recently shifted first (history session desc), then by
    strongest deviation. '' when nothing to show."""
    scored = []
    for fiche in fiches or []:
        line = summary_line(fiche)
        if not line:
            continue
        emo = fiche.get("emotions") or {}
        hist = emo.get("historique") if isinstance(emo.get("historique"), list) else []
        last_sess = -1
        for entry in hist:
            s = entry.get("session") if isinstance(entry, dict) else None
            if isinstance(s, int) and not isinstance(s, bool) and s > last_sess:
                last_sess = s
        temperament = normalize_state(emo.get("temperament"))
        state = normalize_state(emo.get("etat"), fallback=temperament)
        max_dev = max(abs(state[e] - temperament[e]) for e in EMOTIONS)
        scored.append((last_sess, max_dev, line))
    if not scored:
        return ""
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    lines = [line for _, _, line in scored[:max(1, int(max_npc))]]
    header = ("🎭 NPC EMOTIONS — play these through behavior, tone and word "
              "choice; NEVER state feelings or numbers to players:")
    block = header + "\n" + "\n".join(lines)
    if max_chars and len(block) > max_chars:
        block = block[:max_chars - 1].rstrip() + "…"
    return block


# ════════════════════════════════════════════════════════════════════════════
#  Sheet location & persistence (NPCs in pnj.json, opt-in PCs in personnages/)
# ════════════════════════════════════════════════════════════════════════════

def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _pnj_list(data) -> list:
    """Normalises pnj.json into a list of sheets (bare list or {'pnj': [...]})."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict) and isinstance(data.get("pnj"), list):
        return [x for x in data["pnj"] if isinstance(x, dict)]
    return []


def _match(sheets, name: str):
    """(sheet, None) on exact/unique-substring match, else (None, candidates)."""
    target = str(name).strip().lower()
    for sheet in sheets:
        if str(sheet.get("_nom_recherche", "")).lower() == target:
            return sheet, None
    partial = [s for s in sheets
               if target in str(s.get("_nom_recherche", "")).lower()]
    if len(partial) == 1:
        return partial[0], None
    return None, partial


class CharacterRef:
    """A located character sheet + how to write it back (single writer here)."""

    def __init__(self, path: Path, container, fiche: dict, kind: str):
        self.path = path          # file to rewrite
        self.container = container  # full JSON document of that file
        self.fiche = fiche        # the character dict INSIDE the container
        self.kind = kind          # 'pnj' | 'personnage'

    @property
    def name(self) -> str:
        return (self.fiche.get("nom")
                or (self.fiche.get("meta") or {}).get("nom_perso") or "?")

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self.container, fh, ensure_ascii=False, indent=2)
            fh.write("\n")


def find_character(camp: Path, name: str) -> CharacterRef | None:
    """Locates `name`: pnj.json first (canonical home of NPC emotions), then
    opt-in PC sheets in personnages/ (matched on meta.nom_perso).
    Prints a helpful error and returns None when not found / ambiguous."""
    candidates = []  # search views: dicts with _nom_recherche + backrefs

    pnj_path = camp / "pnj.json"
    pnj_doc = _load_json(pnj_path)
    for fiche in _pnj_list(pnj_doc):
        candidates.append({"_nom_recherche": str(fiche.get("nom", "")),
                           "_ref": (pnj_path, pnj_doc, fiche, "pnj")})

    pdir = camp / "personnages"
    if pdir.is_dir():
        for p in sorted(pdir.glob("*.json")):
            fiche = _load_json(p)
            if not isinstance(fiche, dict):
                continue
            nom = (fiche.get("meta") or {}).get("nom_perso") or fiche.get("nom")
            if nom:
                candidates.append({"_nom_recherche": str(nom),
                                   "_ref": (p, fiche, fiche, "personnage")})

    if not candidates:
        _err("❌ no character sheet found in %s (pnj.json / personnages/)" % camp)
        return None
    hit, ambiguous = _match(candidates, name)
    if hit is None:
        if ambiguous:
            names = ", ".join(c["_nom_recherche"] for c in ambiguous)
            _err('❌ "%s" is ambiguous — candidates: %s' % (name, names))
        else:
            names = ", ".join(c["_nom_recherche"] for c in candidates)
            _err('❌ character "%s" not found. Available: %s' % (name, names))
        return None
    return CharacterRef(*hit["_ref"])


def ensure_emotions(fiche: dict, temperament: dict | None = None) -> dict:
    """Returns the sheet's `emotions` object, creating it (state = temperament)
    if absent. Idempotent on existing data (only fills missing sub-keys)."""
    emo = fiche.get("emotions")
    if not isinstance(emo, dict):
        emo = {}
        fiche["emotions"] = emo
    base = normalize_state(temperament if temperament is not None
                           else emo.get("temperament"))
    if not isinstance(emo.get("temperament"), dict):
        emo["temperament"] = dict(base)
    if not isinstance(emo.get("etat"), dict):
        emo["etat"] = dict(normalize_state(emo.get("etat"), fallback=base))
    if not isinstance(emo.get("historique"), list):
        emo["historique"] = []
    return emo


def record_history(emo: dict, event: str, deltas: dict, reason: str,
                   session=None) -> None:
    """Appends an explainability entry; keeps the journal capped."""
    entry = {"evenement": str(event), "deltas": dict(deltas or {}),
             "raison": str(reason or event)}
    if session not in (None, ""):
        entry["session"] = session
    entry["ts"] = datetime.now().isoformat(timespec="seconds")
    hist = emo.setdefault("historique", [])
    hist.append(entry)
    del hist[:-HISTORY_MAX]


# ════════════════════════════════════════════════════════════════════════════
#  Commands
# ════════════════════════════════════════════════════════════════════════════

def _campaign_or_exit(arg: str) -> Path | None:
    camp = _resolve(arg)
    if not Path(camp).is_dir():
        _err("❌ Campaign not found: %s" % camp)
        return None
    return Path(camp)


def _parse_pairs(pairs: list[str], signed: bool):
    """['peur=0.4', 'confiance=-0.2'] → dict. None + message on bad syntax.
    `signed=False` (init): absolute values 0..1; `signed=True` (adjust): deltas."""
    out = {}
    for raw in pairs or []:
        if "=" not in raw:
            _err("❌ bad pair %r (expected emotion=value)" % raw)
            return None
        key, _, val = raw.partition("=")
        key = key.strip().lower()
        if key not in EMOTIONS:
            _err("❌ unknown emotion %r — palette: %s" % (key, ", ".join(EMOTIONS)))
            return None
        try:
            num = float(val)
        except ValueError:
            _err("❌ bad value %r for %s (number expected)" % (val, key))
            return None
        out[key] = num if signed else clamp01(num)
    return out


def _print_state(ref: CharacterRef) -> None:
    emo = ref.fiche.get("emotions") or {}
    temperament = normalize_state(emo.get("temperament"))
    state = normalize_state(emo.get("etat"), fallback=temperament)
    print("=== %s — emotional state ===" % ref.name)
    for e in EMOTIONS:
        dev = round(state[e] - temperament[e], 3)
        arrow = " ▲" if dev >= DEVIATION_THRESHOLD else (" ▼" if dev <= -DEVIATION_THRESHOLD else "")
        print("  %-10s %s  (temperament %s)%s" % (e, _fmt(state[e]), _fmt(temperament[e]), arrow))
    line = summary_line(ref.fiche)
    if line:
        print("summary: %s" % line.lstrip("• "))
    hist = emo.get("historique") or []
    if hist:
        print("history (%d, newest last):" % len(hist))
        for h in hist[-5:]:
            if isinstance(h, dict):
                sess = ("S%s " % h.get("session")) if h.get("session") not in (None, "") else ""
                print("  - %s%s: %s" % (sess, h.get("evenement", "?"), h.get("raison", "")))


def cmd_get(args) -> int:
    camp = _campaign_or_exit(args.campagne)
    if camp is None:
        return 2
    ref = find_character(camp, args.nom)
    if ref is None:
        return 1
    emo = ref.fiche.get("emotions")
    if not isinstance(emo, dict):
        if args.as_json:
            print("null")
        else:
            print("ℹ %s has no emotions data (fail-open: no behavior change). "
                  "Use `init` or `apply` to start tracking." % ref.name)
        return 0
    if args.as_json:
        print(json.dumps(emo, ensure_ascii=False, indent=2))
    else:
        _print_state(ref)
    return 0


def cmd_init(args) -> int:
    camp = _campaign_or_exit(args.campagne)
    if camp is None:
        return 2
    ref = find_character(camp, args.nom)
    if ref is None:
        return 1
    if isinstance(ref.fiche.get("emotions"), dict) and not args.force:
        _err("❌ %s already has emotions data (use --force to reset)." % ref.name)
        return 1
    temperament = _parse_pairs(args.pairs, signed=False)
    if temperament is None:
        return 2
    base = normalize_state(temperament, fallback=DEFAULT_TEMPERAMENT)
    ref.fiche["emotions"] = {"etat": dict(base), "temperament": dict(base),
                             "historique": []}
    ref.save()
    print("✅ %s initialized — temperament: %s" % (
        ref.name, ", ".join("%s %s" % (e, _fmt(base[e])) for e in EMOTIONS)))
    return 0


def _apply_and_save(ref: CharacterRef, event: str, deltas: dict, intensity,
                    reason: str, session) -> dict:
    """Shared by apply/adjust: ensure → apply → journal → save. Returns applied."""
    emo = ensure_emotions(ref.fiche)
    temperament = normalize_state(emo.get("temperament"))
    state = normalize_state(emo.get("etat"), fallback=temperament)
    new_state, applied = apply_deltas(state, deltas, intensity)
    emo["etat"] = new_state
    if applied:
        record_history(emo, event, applied, reason, session)
    ref.save()
    return applied


def cmd_apply(args) -> int:
    camp = _campaign_or_exit(args.campagne)
    if camp is None:
        return 2
    if args.event not in EVENT_RULES:
        _err("❌ unknown event %r — known events: %s"
             % (args.event, ", ".join(sorted(EVENT_RULES))))
        return 1
    ref = find_character(camp, args.nom)
    if ref is None:
        return 1
    reason = args.reason or args.event
    applied = _apply_and_save(ref, args.event, EVENT_RULES[args.event],
                              args.intensity, reason, args.session)
    if applied:
        moved = ", ".join("%s %+.2f" % (e, d) for e, d in sorted(applied.items()))
        print("✅ %s ← %s (×%.2g): %s" % (ref.name, args.event, args.intensity, moved))
    else:
        print("ℹ %s ← %s: no effective change (already at bounds)." % (ref.name, args.event))
    line = summary_line(ref.fiche)
    if line:
        print(line)
    return 0


def cmd_adjust(args) -> int:
    camp = _campaign_or_exit(args.campagne)
    if camp is None:
        return 2
    deltas = _parse_pairs(args.pairs, signed=True)
    if deltas is None or not deltas:
        _err("❌ at least one emotion=±delta pair is required.")
        return 2
    ref = find_character(camp, args.nom)
    if ref is None:
        return 1
    applied = _apply_and_save(ref, "adjust", deltas, 1.0, args.reason, args.session)
    if applied:
        moved = ", ".join("%s %+.2f" % (e, d) for e, d in sorted(applied.items()))
        print("✅ %s adjusted: %s — %s" % (ref.name, moved, args.reason))
    else:
        print("ℹ %s: no effective change (already at bounds)." % ref.name)
    return 0


def cmd_decay(args) -> int:
    camp = _campaign_or_exit(args.campagne)
    if camp is None:
        return 2
    if args.nom:
        refs = [find_character(camp, args.nom)]
        if refs[0] is None:
            return 1
    else:
        # All NPCs carrying emotions (PC sheets are never decayed in bulk:
        # their emotional life belongs to the players).
        pnj_path = camp / "pnj.json"
        pnj_doc = _load_json(pnj_path)
        sheets = [f for f in _pnj_list(pnj_doc) if isinstance(f.get("emotions"), dict)]
        if not sheets:
            print("ℹ no NPC with emotions data — nothing to decay.")
            return 0
        refs = [CharacterRef(pnj_path, pnj_doc, f, "pnj") for f in sheets]

    label = args.label or "time passes"
    for ref in refs:
        emo = ref.fiche.get("emotions")
        if not isinstance(emo, dict):
            print("ℹ %s has no emotions data — skipped." % ref.name)
            continue
        emo = ensure_emotions(ref.fiche)
        temperament = normalize_state(emo.get("temperament"))
        state = normalize_state(emo.get("etat"), fallback=temperament)
        new_state = decay_state(state, temperament, args.rate)
        moved = {e: round(new_state[e] - state[e], 3)
                 for e in EMOTIONS if new_state[e] != state[e]}
        emo["etat"] = new_state
        if moved and max(abs(d) for d in moved.values()) >= DECAY_HISTORY_MIN:
            record_history(emo, "decay", moved, label, args.session)
        print("✅ %s decayed toward temperament (rate %.2g)%s"
              % (ref.name, args.rate,
                 "" if moved else " — already settled"))
    # All refs in bulk mode share the same container → one save is enough,
    # but saving per ref stays correct (idempotent rewrite of the same doc).
    refs[-1].save()
    return 0


def cmd_summary(args) -> int:
    """ALWAYS exits 0 and prints '' when no data: the pre_llm_call hook relies
    on this fail-open contract."""
    try:
        camp = _resolve(args.campagne)
        fiches = _pnj_list(_load_json(Path(camp) / "pnj.json"))
        block = summary_block(fiches, max_npc=args.max_npc)
        if block:
            print(block)
    except Exception:
        pass
    return 0


def cmd_list_events(_args) -> int:
    print("Known events (deltas before ×intensity and clamping to [0,1]):")
    for event in sorted(EVENT_RULES):
        deltas = ", ".join("%s %+.2f" % (e, d)
                           for e, d in sorted(EVENT_RULES[event].items()))
        print("  %-22s %s" % (event, deltas))
    print("\nUnlisted situation → `adjust <campagne> <nom> emo=±delta --reason \"…\"`.")
    return 0


# ════════════════════════════════════════════════════════════════════════════
#  CLI
# ════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="emotions.py",
        description=("Character emotional state (6 emotions 0..1 + temperament): "
                     "deterministic event-driven evolution, decay, explainable "
                     "history. NPCs in pnj.json, opt-in PCs in personnages/."),
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("get", help="show a character's emotional state")
    p.add_argument("campagne")
    p.add_argument("nom")
    p.add_argument("--json", action="store_true", dest="as_json")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("init", help="initialize emotions (temperament = state)")
    p.add_argument("campagne")
    p.add_argument("nom")
    p.add_argument("pairs", nargs="*", metavar="emotion=val",
                   help="temperament values 0..1 (missing ones → neutral default)")
    p.add_argument("--force", action="store_true",
                   help="reset existing emotions data")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("apply", help="apply a named event (see list-events)")
    p.add_argument("campagne")
    p.add_argument("nom")
    p.add_argument("--event", required=True, help="event name (e.g. betrayal)")
    p.add_argument("--intensity", type=float, default=1.0,
                   help="delta multiplier, 0..1 typical (default 1.0)")
    p.add_argument("--reason", default="",
                   help="short in-fiction reason (journaled; default: event name)")
    p.add_argument("--session", type=int, default=None,
                   help="session number for traceability (like faits_etablis)")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("adjust", help="free-form deltas (reason REQUIRED)")
    p.add_argument("campagne")
    p.add_argument("nom")
    p.add_argument("pairs", nargs="+", metavar="emotion=±delta")
    p.add_argument("--reason", required=True,
                   help="why — journaled so the shift is never arbitrary")
    p.add_argument("--session", type=int, default=None)
    p.set_defaults(func=cmd_adjust)

    p = sub.add_parser("decay", help="decay toward temperament (one NPC or all)")
    p.add_argument("campagne")
    p.add_argument("nom", nargs="?", default=None,
                   help="character name (default: every NPC with emotions)")
    p.add_argument("--rate", type=float, default=DEFAULT_DECAY_RATE,
                   help="fraction of the gap closed (default %s ≈ one session)"
                        % DEFAULT_DECAY_RATE)
    p.add_argument("--label", default="",
                   help="journal label (default: 'time passes')")
    p.add_argument("--session", type=int, default=None)
    p.set_defaults(func=cmd_decay)

    p = sub.add_parser("summary", help="compact GM block (used by pre_llm_call)")
    p.add_argument("campagne")
    p.add_argument("--max", type=int, default=SUMMARY_MAX_DEFAULT, dest="max_npc",
                   help="max characters shown (default %s)" % SUMMARY_MAX_DEFAULT)
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("list-events", help="show the event → deltas rule table")
    p.set_defaults(func=cmd_list_events)

    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
