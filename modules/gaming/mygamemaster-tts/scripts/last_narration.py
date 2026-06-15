#!/usr/bin/env python3
"""
last_narration.py — Retrieves the LAST GM narration for the !raconte command.

The transform_llm_output hook stores each narration (full text, untruncated)
in a snapshot `.banquier/snap-<session>.json` under the key `last_narration`. This script
retrieves it deterministically without depending on the runtime session_id:

  1. most recently modified snapshot containing `last_narration` (FULL text);
  2. failing that, the last GM line from `collecte.csv` (column `sortie`, truncated to 500).

Prints the narration to stdout (empty if nothing found -> the caller signals this).

Usage: python3 last_narration.py <dossier_campagne>
"""
import csv
import glob
import json
import os
import sys


def from_snapshots(camp):
    snaps = glob.glob(os.path.join(camp, ".banquier", "snap-*.json"))
    best = None
    best_mtime = -1
    for path in snaps:
        try:
            mtime = os.path.getmtime(path)
            if mtime <= best_mtime:
                continue
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            val = data.get("last_narration") if isinstance(data, dict) else None
            if isinstance(val, str) and val.strip():
                best, best_mtime = val, mtime
        except (OSError, ValueError):
            continue
    return best


def from_csv(camp):
    path = os.path.join(camp, "collecte.csv")
    if not os.path.isfile(path):
        return None
    last = None
    try:
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if (row.get("origine_type") == "MJ") and (row.get("sortie") or "").strip():
                    last = row["sortie"]
    except (OSError, ValueError):
        return None
    return last


def main():
    if len(sys.argv) < 2:
        print("usage: last_narration.py <dossier_campagne>", file=sys.stderr)
        return 2
    camp = sys.argv[1]
    text = from_snapshots(camp) or from_csv(camp)
    if not text:
        return 1
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
