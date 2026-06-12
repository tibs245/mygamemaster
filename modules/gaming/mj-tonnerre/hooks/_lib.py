#!/usr/bin/env python3
"""
_lib.py — Common library for MJ Tonnerre runtime hooks.

Stdlib only (no pip dependencies). All hooks import this module.

Guiding principle: FAIL-OPEN. A hook must NEVER break a game session. On any
unexpected error, emit `{}` (no-op) rather than raising. See run().

The payload is read from stdin (JSON). Campaign files are anchored on
`cwd` from the payload (= terminal.cwd Hermes = campaign directory).
See specs/hooks-runtime.md.
"""

import csv
import fcntl
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# ─── Payload & output ────────────────────────────────────────────────────────


def read_payload():
    """Reads JSON from stdin. Tolerant: returns {} if empty/unreadable."""
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def emit(obj):
    """Writes output JSON to stdout then exits cleanly (exit 0)."""
    try:
        sys.stdout.write(json.dumps(obj or {}, ensure_ascii=False))
        sys.stdout.flush()
    except Exception:
        pass


def noop():
    emit({})


def run(handler):
    """Executes handler(payload) and emits its return value. Any exception → safe no-op."""
    try:
        payload = read_payload()
        result = handler(payload)
        emit(result if isinstance(result, dict) else {})
    except SystemExit:
        raise
    except Exception:
        # FAIL-OPEN: never break the game session for a hook bug.
        noop()


def first_present(d, keys, default=None):
    """Returns the first non-empty value among `keys`, also searching in 'extra'."""
    if not isinstance(d, dict):
        return default
    extra = d.get("extra") if isinstance(d.get("extra"), dict) else {}
    for k in keys:
        for src in (d, extra):
            v = src.get(k)
            if v not in (None, "", [], {}):
                return v
    return default


# ─── Campaign location & state loading ───────────────────────────────────────


def campaign_dir(payload):
    """Campaign directory (file anchor). Default: process cwd."""
    cwd = payload.get("cwd") or first_present(payload, ["cwd", "working_dir"]) or "."
    try:
        return Path(cwd)
    except Exception:
        return Path(".")


def load_json(path):
    """Loads a JSON file. None if missing/broken (tolerant)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def load_monde(camp):
    return load_json(camp / "monde.json") or {}


def load_pnj_list(camp):
    """Returns the list of NPC sheets (tolerates [...] or {"pnj":[...]})."""
    data = load_json(camp / "pnj.json")
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("pnj"), list):
        return data["pnj"]
    return []


def iter_personnages(camp):
    """Iterates (path, sheet) over player characters."""
    pdir = camp / "personnages"
    if not pdir.is_dir():
        return
    for p in sorted(pdir.glob("*.json")):
        fiche = load_json(p)
        if isinstance(fiche, dict):
            yield p, fiche


def meta(monde):
    m = monde.get("meta") if isinstance(monde, dict) else None
    return m if isinstance(m, dict) else {}


def verbosite(monde):
    lvl = str(meta(monde).get("verbosite", "INFO")).upper()
    return lvl if lvl in ("TRACE", "DEBUG", "INFO", "WARN", "ERROR") else "INFO"


def diagnostic_cfg(monde):
    d = meta(monde).get("diagnostic")
    return d if isinstance(d, dict) else {}


# ─── Unified feature flags (meta.features) ───────────────────────────────────
#
# Six main axes, ALL enabled by default. Resolution cascades from most
# specific to most general:
#     meta.features.<axis> (monde.json)  >  env MJ_FEATURE_<AXIS>  >  default True
# The world (monde.json) has the final say; env sets the instance/deployment default.
# Effects remain fail-open: an ON axis with missing data (e.g. living world
# without geo.json) is a simple no-op, never an error.
# Wiring details: docs/monde-vivant/10-features.md.

FEATURES = ("tracabilite", "verbosite", "pnj_faction_vivants", "temporalite", "images", "tts")


def as_bool(val, default):
    """Coerces a JSON bool / env string ('1','true','on','oui'…) → bool. `default` if None/unknown."""
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    s = str(val).strip().lower()
    if s in ("1", "true", "yes", "on", "oui"):
        return True
    if s in ("0", "false", "no", "off", "non"):
        return False
    return default


def features(monde):
    """Resolves the 5 feature flags. Cascade: meta.features.<axis> > env MJ_FEATURE_<AXIS> > True.

    All enabled by default. A campaign without a meta.features block behaves as
    "all ON" — safe, because each effect is fail-open when its data is missing."""
    f = meta(monde).get("features")
    f = f if isinstance(f, dict) else {}
    out = {}
    for axe in FEATURES:
        env_default = as_bool(os.environ.get("MJ_FEATURE_" + axe.upper()), True)
        out[axe] = as_bool(f.get(axe), env_default)
    return out


def hooks_cfg(monde):
    """Effective meta.hooks toggles (all enabled by default).

    Feature flags (meta.features) are the MAIN SWITCHES: if an axis is OFF,
    the fine-grained toggles it governs are forced OFF. Otherwise the fine toggle
    meta.hooks.<x> decides (default ON). Detailed mapping: docs/monde-vivant/10-features.md.
    """
    h = meta(monde).get("hooks")
    h = h if isinstance(h, dict) else {}
    feat = features(monde)

    def gated(name, default, axe_on):
        # axe_on = the feature governing this toggle; if False → force OFF.
        return bool(axe_on) and bool(h.get(name, default))

    return {
        # Core, always available (not governed by any axis):
        "injection_etat": h.get("injection_etat", True),
        "garde_json_strict": h.get("garde_json_strict", False),
        # Axis "verbosite" → Steward "Persisted" block:
        "banquier_persiste": gated("banquier_persiste", True, feat["verbosite"]),
        # Axis "tracabilite" → session snapshots + git auto-commit:
        "snapshot_fin_session": gated("snapshot_fin_session", True, feat["tracabilite"]),
        "auto_commit": gated("auto_commit", True, feat["tracabilite"]),
        # Axis "temporalite" → living world engine (default ON; no-op if geo/actors missing):
        "brief_scene": gated("brief_scene", True, feat["temporalite"]),
        "tick_pre": gated("tick_pre", True, feat["temporalite"]),
        "tick_post": gated("tick_post", True, feat["temporalite"]),
        # Axis "pnj_faction_vivants" → exposed for the tick (actors that "think"):
        "pnj_faction_vivants": bool(feat["pnj_faction_vivants"]),
        # Axis "tts" → automatic narrative voice (Minimax) in transform_llm_output:
        "tts_auto": gated("tts_auto", True, feat["tts"]),
        # The 6 raw axes, for direct consumers:
        "features": feat,
    }


# ─── Admin bypass / pause ────────────────────────────────────────────────────

PAUSE = "⏸"  # ⏸️ (with or without variation selector)
PAUSE_CMD = "!pause"  # ASCII text alias
RESUME = "▶"  # ▶️ lifts persistent pause mode
RESUME_CMD = "!reprise"  # ASCII text alias (≠ !reprendre, which reloads the session)


def admins(monde):
    ids = set()
    for x in meta(monde).get("admins", []) or []:
        ids.add(str(x))
    for x in (os.environ.get("MJ_ADMIN_IDS", "") or "").split(","):
        x = x.strip()
        if x:
            ids.add(x)
    return ids


def incoming_message(payload):
    v = first_present(
        payload,
        ["message", "text", "content", "prompt", "user_message", "input", "body"],
        default="",
    )
    return v if isinstance(v, str) else ""


def author_id(payload):
    v = first_present(
        payload, ["author_id", "user_id", "author", "sender_id", "discord_id"]
    )
    return str(v) if v not in (None, "") else None


def model_name(payload):
    v = first_present(payload, ["model", "model_name", "llm_model"], default="")
    return str(v)


def _pause_mode_get(camp, payload):
    """PERSISTENT pause flag for the turn (stored in snap-<sid>.json)."""
    return bool(snap_get(camp, payload, "pause_mode"))


def _pause_mode_set(camp, payload, on):
    snap_set(camp, payload, "pause_mode", bool(on))


def pause_active(payload, monde, camp=None):
    """EXPLICIT pause — ⏸️/!pause on THIS message, or persistent mode not yet lifted.
    NOT the admin bypass. If `camp` is provided, manages persistent mode ⏸️ … ▶️:
    ⏸️/!pause arms the mode, ▶️/!reprise lifts it (the ▶️ message is no longer paused).
    Without `camp`: original per-message behavior (the marker lasts only one turn)."""
    msg = incoming_message(payload)
    msg_l = msg.lower()
    paused = PAUSE in msg or PAUSE_CMD in msg_l
    resumed = RESUME in msg or RESUME_CMD in msg_l
    if camp is None:
        return paused and not resumed
    # ▶️ takes priority over ⏸️ if both are present (resume wins).
    if resumed:
        _pause_mode_set(camp, payload, False)
    elif paused:
        _pause_mode_set(camp, payload, True)
    return _pause_mode_get(camp, payload)


def is_bypassed(payload, monde, camp=None):
    """True if explicit pause (⏸️/!pause or persistent mode ▶️) OR admin author.
    NB: the LLM judge uses `pause_active` (without the admin guard) so it also runs
    on admin turns — only an explicit pause suspends it."""
    if pause_active(payload, monde, camp):
        return True
    aid = author_id(payload)
    return bool(aid and aid in admins(monde))


# ─── Response text (transform_llm_output) ────────────────────────────────────


def response_text(payload):
    """Retrieves the response text. None if not found → safe no-op fallback."""
    v = first_present(
        payload, ["response", "output", "content", "text", "message", "llm_output"]
    )
    return v if isinstance(v, str) else None


# ─── Active session number ───────────────────────────────────────────────────


def active_session_number(camp):
    sdir = camp / "sessions"
    best = None
    if sdir.is_dir():
        for p in sdir.glob("*.json"):
            stem = p.stem.lstrip("0") or "0"
            try:
                n = int(stem)
            except ValueError:
                continue
            if best is None or n > best:
                best = n
    return best


# ─── .banquier workspace (ledger, snapshots, sample) ─────────────────────────


def _bq_dir(camp):
    d = camp / ".banquier"
    try:
        d.mkdir(exist_ok=True)
    except Exception:
        pass
    return d


def _sid(payload):
    return str(payload.get("session_id") or first_present(payload, ["session_id"]) or "default")


def _locked_rw(path, mutate):
    """Opens `path` (created if needed), applies mutate(data)->data under flock."""
    try:
        path.parent.mkdir(exist_ok=True, parents=True)
        with open(path, "a+", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                fh.seek(0)
                raw = fh.read()
                data = json.loads(raw) if raw.strip() else None
                data = mutate(data)
                fh.seek(0)
                fh.truncate()
                fh.write(json.dumps(data, ensure_ascii=False))
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
        return data
    except Exception:
        return None


def ledger_append(camp, payload, entry):
    """Appends an entry (dict) to the current turn's ledger."""
    path = _bq_dir(camp) / ("ledger-%s.json" % _sid(payload))

    def mut(data):
        lst = data if isinstance(data, list) else []
        lst.append(entry)
        return lst

    _locked_rw(path, mut)


def ledger_read_clear(camp, payload):
    """Reads and then CLEARS the turn ledger (idempotent: no double-reporting)."""
    path = _bq_dir(camp) / ("ledger-%s.json" % _sid(payload))
    out = {"box": []}

    def mut(data):
        out["box"] = data if isinstance(data, list) else []
        return []

    _locked_rw(path, mut)
    return out["box"]


def snap_get(camp, payload, key):
    path = _bq_dir(camp) / ("snap-%s.json" % _sid(payload))
    data = load_json(path)
    if isinstance(data, dict):
        return data.get(key)
    return None


def snap_set(camp, payload, key, value):
    path = _bq_dir(camp) / ("snap-%s.json" % _sid(payload))

    def mut(data):
        d = data if isinstance(data, dict) else {}
        d[key] = value
        return d

    _locked_rw(path, mut)


# ─── Classification & counters of campaign files ─────────────────────────────


def classify(path, camp):
    """Returns a logical campaign file type, or None if out of scope."""
    try:
        p = Path(path)
        if not p.is_absolute():
            p = (camp / p)
        p = p.resolve()
    except Exception:
        return None, None
    name = p.name
    parent = p.parent.name
    if p.suffix != ".json":
        return None, p
    if name == "monde.json":
        return "monde", p
    if name == "pnj.json":
        return "pnj", p
    if name == "evenements.json":
        return "evenements", p
    if parent == "personnages":
        return "personnage", p
    if parent == "sessions":
        return "session", p
    return None, p


def file_counts(kind, path):
    """Key counters for a file (for computing deltas). {} if unreadable."""
    data = load_json(path)
    if data is None:
        return {}
    c = {}
    try:
        if kind == "session" and isinstance(data, dict):
            c["actions"] = len(data.get("actions") or [])
            c["pnj_rencontres"] = len(data.get("pnj_rencontres") or [])
            c["lieux_visites"] = len(data.get("lieux_visites") or [])
            c["cloturee"] = bool(data.get("heure_fin"))
        elif kind == "personnage" and isinstance(data, dict):
            c["inventaire"] = len(data.get("inventaire") or [])
            c["equipement"] = len(data.get("equipement") or [])
            sante = data.get("sante") or {}
            if isinstance(sante, dict) and "pv_actuels" in sante:
                c["pv"] = sante.get("pv_actuels")
            c["nom"] = (data.get("meta") or {}).get("nom_perso")
        elif kind == "pnj":
            lst = data if isinstance(data, list) else (data.get("pnj") if isinstance(data, dict) else [])
            total = 0
            for f in lst or []:
                if isinstance(f, dict):
                    total += len(f.get("faits_etablis") or [])
                    total += len(f.get("connaissances_privees") or [])
            c["faits_total"] = total
        elif kind == "monde" and isinstance(data, dict):
            suivi = (((data.get("regles") or {}).get("temps") or {}).get("suivi")) or {}
            if isinstance(suivi, dict):
                c["jour"] = suivi.get("jour_courant")
                c["heure"] = suivi.get("heure_courante")
    except Exception:
        return {}
    return c


# ─── CSV traceability ────────────────────────────────────────────────────────

DEFAULT_COLUMNS = [
    "timestamp", "session", "verbosite", "origine_type", "origine_detail",
    "action_type", "prompt_resume", "sortie", "consequence", "erreur",
    "type_erreur", "correction_immediate", "exactitude", "completude",
    "conteste", "modele", "notes",
]


def csv_append(camp, monde, payload, row, has_error=False):
    """Appends a row to collecte.csv according to the sampling policy."""
    if not features(monde).get("tracabilite", True):
        return False  # axis "tracabilite" OFF → no CSV logging
    cfg = diagnostic_cfg(monde)
    if not cfg.get("actif"):
        return False
    columns = cfg.get("colonnes") or DEFAULT_COLUMNS
    fname = cfg.get("fichier") or "collecte.csv"
    path = camp / fname

    # Sampling decision (persistent counter under flock).
    if not _decide_sample(camp, payload, monde, has_error):
        return False

    line = {col: row.get(col, "") for col in columns}
    try:
        new = not path.exists() or path.stat().st_size == 0
        with open(path, "a", encoding="utf-8", newline="") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
                if new:
                    writer.writeheader()
                writer.writerow(line)
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
        return True
    except Exception:
        return False


def _decide_sample(camp, payload, monde, has_error):
    cfg = diagnostic_cfg(monde)
    if has_error:
        return True
    lvl = verbosite(monde)
    regles = cfg.get("regles") or {}
    if lvl in (regles.get("log_systematique") or ["TRACE", "DEBUG"]):
        return True
    if lvl in (regles.get("log_erreurs_uniquement") or ["ERROR"]):
        return False
    freq = int(regles.get("echantillon_frequence", 5) or 5)
    if freq <= 1:
        return True
    path = _bq_dir(camp) / "sample.json"
    out = {"hit": False}

    def mut(data):
        d = data if isinstance(data, dict) else {}
        n = int(d.get("n", 0)) + 1
        d["n"] = n
        out["hit"] = (n % freq == 0)
        return d

    _locked_rw(path, mut)
    return out["hit"]


# ─── Compact state (judge context + injection) ───────────────────────────────


def etat_brief(camp, monde, for_judge=False):
    """Authoritative state summary. Reused by injection and the judge."""
    lines = []
    suivi = (((monde.get("regles") or {}).get("temps") or {}).get("suivi")) or {}
    if suivi.get("jour_courant") or suivi.get("heure_courante"):
        lines.append("Time: day %s, %s" % (suivi.get("jour_courant", "?"), suivi.get("heure_courante", "?")))
    else:
        regime = (meta(monde).get("temps") or {}).get("regime", "Narratif")
        lines.append("Time: regime %s (estimated durations)" % regime)
    for _, fiche in iter_personnages(camp):
        nom = (fiche.get("meta") or {}).get("nom_perso") or "?"
        sante = fiche.get("sante") or {}
        inv = fiche.get("inventaire") or []
        equ = fiche.get("equipement") or []
        head = "PC %s" % nom
        if sante.get("pv_actuels") is not None:
            head += " (❤️ %s/%s PV)" % (sante.get("pv_actuels"), sante.get("pv_max", "?"))
        lines.append(head)
        objets = [str(x) for x in (list(inv) + list(equ))]
        if objets:
            lines.append("  has: " + truncate(", ".join(objets), 400))
    pnj = load_pnj_list(camp)
    if pnj:
        noms = [str(f.get("nom")) for f in pnj if isinstance(f, dict) and f.get("nom")]
        if noms:
            lines.append("Existing NPCs: " + truncate(", ".join(noms), 300))
    return "\n".join(lines)


# ─── LLM call (judge) — urllib, stdlib only ──────────────────────────────────


def http_json(url, payload, headers=None, timeout=8):
    """POST JSON → dict, or None (fail-open). No external dependencies."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def judge_config(monde):
    """meta.hooks.judge — LLM judge config (Steward + conduct). Default: inactive."""
    h = meta(monde).get("hooks")
    h = h if isinstance(h, dict) else {}
    j = h.get("judge")
    j = j if isinstance(j, dict) else {}
    # Model: explicit (monde.json), otherwise deployment env MJ_JUDGE_MODEL.
    modele = j.get("modele") or os.environ.get("MJ_JUDGE_MODEL") or ""
    # Activation: monde.json takes priority; otherwise deployment env MJ_JUDGE_ACTIF decides.
    actif_env = str(os.environ.get("MJ_JUDGE_ACTIF", "")).lower() in ("1", "true", "yes", "on")
    return {
        "actif": bool(j.get("actif", actif_env)),
        "modele": modele,
        "base_url": j.get("base_url") or os.environ.get("MJ_JUDGE_BASE_URL") or "https://openrouter.ai/api/v1",
        "timeout": int(j.get("timeout", 8) or 8),
        "echantillon": int(j.get("echantillon", 1) or 1),
        "min_chars": int(j.get("min_chars", 40) or 40),
        "gate_max_tentatives": int(j.get("gate_max_tentatives", 2) or 2),
    }


# ─── Deferred feedback (feed-forward) ────────────────────────────────────────


def set_pending(camp, payload, text):
    """Stores a corrective feedback to be re-injected on the next turn."""
    path = _bq_dir(camp) / ("pending-%s.json" % _sid(payload))

    def mut(_):
        return {"text": text, "ts": now_iso()}

    _locked_rw(path, mut)


def take_pending(camp, payload):
    """Reads AND clears the deferred feedback (idempotent: injected only once)."""
    path = _bq_dir(camp) / ("pending-%s.json" % _sid(payload))
    out = {"text": ""}

    def mut(data):
        if isinstance(data, dict):
            out["text"] = data.get("text", "")
        return {}

    _locked_rw(path, mut)
    return out["text"]


# ─── Anti-loop budget (gate) ─────────────────────────────────────────────────


def attempts_get(camp, payload):
    v = snap_get(camp, payload, "checkpoint_attempts")
    return int(v) if isinstance(v, int) else 0


def attempts_inc(camp, payload):
    n = attempts_get(camp, payload) + 1
    snap_set(camp, payload, "checkpoint_attempts", n)
    return n


def attempts_reset(camp, payload):
    snap_set(camp, payload, "checkpoint_attempts", 0)


# ─── Per-model scoreboard ────────────────────────────────────────────────────


def scoreboard_update(camp, modele, clean, banquier_n, conduite_n, by_rule, forced=0):
    """Increments a model's counters in .banquier/scoreboard.json."""
    path = _bq_dir(camp) / "scoreboard.json"
    key = modele or "inconnu"

    def mut(data):
        d = data if isinstance(data, dict) else {}
        m = d.get(key) if isinstance(d.get(key), dict) else {}
        m["tours"] = int(m.get("tours", 0)) + 1
        m["propres"] = int(m.get("propres", 0)) + (1 if clean else 0)
        m["interventions_banquier"] = int(m.get("interventions_banquier", 0)) + int(banquier_n)
        m["infractions_conduite"] = int(m.get("infractions_conduite", 0)) + int(conduite_n)
        m["forces"] = int(m.get("forces", 0)) + int(forced)
        rules = m.get("par_regle") if isinstance(m.get("par_regle"), dict) else {}
        for r in (by_rule or []):
            rules[r] = int(rules.get(r, 0)) + 1
        m["par_regle"] = rules
        d[key] = m
        return d

    _locked_rw(path, mut)


def load_scoreboard(camp):
    return load_json(camp / ".banquier" / "scoreboard.json") or {}


# ─── Git auto-commit (systematic versioned persistence) ──────────────────────
#
# The post_tool_call hook commits the campaign after EACH validated write. Goal:
# relieve the model of manual `git add/commit` (which it often forgets). Fully
# fail-open: git absent / not configured / error → no commit, never an exception.
# Inline identity (no infra dependency); lazy repo init; the runtime workspace
# (.banquier/, collecte.csv) is excluded so only game CONTENT is versioned.
# `git -C <campaign>` always operates in the campaign repo (not the parent)
# → avoids the pitfall of nested git repos.

_GIT_IDENTITY = [
    "-c", "user.name=MJ Tonnerre",
    "-c", "user.email=mj-tonnerre@hermes.local",
]
_GITIGNORE_PATTERNS = ["._*", ".banquier/", "collecte.csv"]


def _git(camp, args, timeout=8):
    """`git -C camp args` → (returncode, output). (None, '') on failure. Fail-open."""
    try:
        r = subprocess.run(
            ["git", "-C", str(camp)] + list(args),
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception:
        return None, ""


def _git_ensure_repo(camp):
    """Ensures a git repo is ready (lazy init) + .gitignore up to date. True if ready."""
    if not (camp / ".git").exists():
        rc, _ = _git(camp, ["init", "-q"])
        if rc != 0:
            return False
    # Idempotent top-up of .gitignore: do not version the runtime workspace.
    try:
        gi = camp / ".gitignore"
        existing = gi.read_text(encoding="utf-8") if gi.exists() else ""
        missing = [p for p in _GITIGNORE_PATTERNS if p not in existing]
        if missing:
            with open(gi, "a", encoding="utf-8") as fh:
                if existing and not existing.endswith("\n"):
                    fh.write("\n")
                fh.write("\n".join(missing) + "\n")
            # Best-effort untrack if the runtime workspace was already tracked (pre-existing repo).
            _git(camp, ["rm", "-r", "--cached", "--ignore-unmatch", "-q",
                        ".banquier", "collecte.csv"])
    except Exception:
        pass
    return True


def git_autocommit(camp, message, timeout=8):
    """Commits all campaign changes (fail-open). Never emits an empty commit.
    Returns an OBSERVABLE status (the historical default was silent failure):
    'committed' | 'nothing' | 'no-git' | 'failed' | 'error'."""
    try:
        camp = Path(camp)
        if not camp.is_dir():
            return "no-git"
        if not _git_ensure_repo(camp):
            return "no-git"
        rc, _ = _git(camp, ["add", "-A"], timeout=timeout)
        if rc != 0:
            return "failed"
        rc, _ = _git(camp, ["diff", "--cached", "--quiet"], timeout=timeout)
        if rc == 0:  # nothing staged → no empty commit
            return "nothing"
        msg = truncate(message or "auto: campaign update", 200)
        rc, _ = _git(camp, _GIT_IDENTITY + ["commit", "-q", "-m", msg], timeout=timeout)
        return "committed" if rc == 0 else "failed"
    except Exception:
        return "error"


# ─── Miscellaneous ───────────────────────────────────────────────────────────


def now_iso():
    try:
        return datetime.now().astimezone().isoformat(timespec="seconds")
    except Exception:
        return datetime.now().isoformat()


def truncate(s, n):
    s = "" if s is None else str(s)
    s = s.replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"
