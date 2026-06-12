#!/usr/bin/env python3
"""
on_session_end — timestamped snapshot of campaign JSON files (safety net).

Copies monde.json / pnj.json / evenements.json / personnages/* / sessions/*
under .banquier/snapshots/<timestamp>/ and keeps the KEEP most recent ones.
Best-effort: never causes session end to fail.
"""
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402

KEEP = 10


def handle(payload):
    camp = L.campaign_dir(payload)
    monde = L.load_monde(camp)
    if not L.hooks_cfg(monde)["snapshot_fin_session"]:
        return {}

    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    dest = camp / ".banquier" / "snapshots" / stamp
    try:
        dest.mkdir(parents=True, exist_ok=True)
        for name in ("monde.json", "pnj.json", "evenements.json"):
            src = camp / name
            if src.exists():
                shutil.copy2(src, dest / name)
        for sub in ("personnages", "sessions"):
            srcdir = camp / sub
            if srcdir.is_dir():
                (dest / sub).mkdir(exist_ok=True)
                for f in srcdir.glob("*.json"):
                    shutil.copy2(f, dest / sub / f.name)
        _prune(camp / ".banquier" / "snapshots")
    except Exception:
        pass
    return {}


def _prune(root):
    try:
        snaps = sorted(p for p in root.iterdir() if p.is_dir())
        for old in snaps[:-KEEP]:
            shutil.rmtree(old, ignore_errors=True)
    except Exception:
        pass


if __name__ == "__main__":
    L.run(handle)
