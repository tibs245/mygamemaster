#!/usr/bin/env python3
"""Dynamic Ansible inventory built from a single declarative table.

Reads `games.yml` (your real table, git-ignored) — or falls back to
`games.example.yml` if it does not exist yet — and turns every entry under
`games:` into a host of the `campaigns` group. Each game's fields are mapped to
the variables the `hermes_deploy` role already expects, so the playbooks and the
role stay unchanged.

To add a game: append ONE entry to games.yml. Nothing else to edit.

Usage (called automatically by Ansible via ansible.cfg `inventory =`):
    ./hermes_inventory.py --list
    ./hermes_inventory.py --host <slug>
"""
import json
import os
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML ships with Ansible
    sys.stderr.write("PyYAML is required (it ships with Ansible).\n")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))

# Map a game-table field -> the variable name the role/templates consume.
FIELD_TO_VAR = {
    "slug": "campaign_slug",
    "data_dir": "campaign_data_dir",
    "title": "campaign_title",
    "model": "model",
    "provider": "provider",
    "language": "default_language",
    "discord_secret_key": "discord_secret_key",
    "soul_extra": "soul_extra",
}

# Map the shared connection block -> Ansible connection facts (group vars).
CONNECTION_TO_VAR = {
    "host": "ansible_host",
    "port": "ansible_port",
    "user": "ansible_user",
    "ssh_key": "ansible_ssh_private_key_file",
    "python": "ansible_python_interpreter",
}


def _table_path():
    real = os.path.join(HERE, "games.yml")
    example = os.path.join(HERE, "games.example.yml")
    return real if os.path.exists(real) else example


def _load_table():
    path = _table_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except OSError as exc:
        sys.stderr.write(f"Cannot read game table {path}: {exc}\n")
        return {}, {}
    games = data.get("games") or []
    connection = data.get("connection") or {}
    return games, connection


def _hostvars(game):
    hv = {}
    for field, var in FIELD_TO_VAR.items():
        if field in game and game[field] is not None:
            hv[var] = game[field]
    return hv


def _group_vars(connection):
    gv = {}
    for field, var in CONNECTION_TO_VAR.items():
        if field in connection and connection[field] is not None:
            gv[var] = connection[field]
    return gv


def build_inventory():
    games, connection = _load_table()
    hostvars = {}
    hosts = []
    for game in games:
        slug = game.get("slug")
        if not slug:
            continue
        hosts.append(slug)
        hostvars[slug] = _hostvars(game)
    return {
        "campaigns": {
            "hosts": hosts,
            "vars": _group_vars(connection),
        },
        "_meta": {"hostvars": hostvars},
    }


def main(argv):
    if "--host" in argv:
        idx = argv.index("--host")
        slug = argv[idx + 1] if idx + 1 < len(argv) else ""
        inv = build_inventory()
        print(json.dumps(inv["_meta"]["hostvars"].get(slug, {})))
        return 0
    # default: --list
    print(json.dumps(build_inventory()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
