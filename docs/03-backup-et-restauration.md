# 03 — Backup, Restore & Reset

## Data model: what is persisted, and where

Each campaign has **two** persistent stores (Podman volumes, isolated per `deploy_id`):

| Volume | Mounted at | Contents | Backed up by |
|---|---|---|---|
| `hermes-<id>-data` | `/opt/data/mj-tonnerre/campagnes` | **Game data**: `monde.json`, `pnj.json`, `personnages/`, `sessions/`, `evenements.json`, `geo.json`, `images/`, `collecte.csv`, **`.banquier/`** (ledger + snapshots) | volume export → `tar.gz` |
| `hermes-<id>-home` | `/opt/hermes-home` (all of `HERMES_HOME`) | **Agent state / memory**: `state.db`, `memories/`, Hermes `sessions/`, `kanban.db`, gateway state | `hermes backup` → `zip` (hot, consistent) |

> **Note**: the full `HERMES_HOME` is mounted (not just the `memory/` subdirectory). The old
> single-directory mount left all agent state in the ephemeral container layer and was erased on
> every `recreate`. `config.yaml` and `SOUL.md` remain read-only bind-mounts regenerated from
> Ansible templates, so they are **not** backed up (they are reproducible).

### Migration (one-time, for older deployments)

Old deployments used the misnamed `hermes-<id>-memory` volume. A simple redeploy switches to
the correct `hermes-<id>-home` volume:

```bash
ansible-playbook playbooks/deploy.yml -e game=<slug> --ask-vault-pass
```

The container is recreated on the `-home` volume. The old empty `-memory` volume becomes an
orphan and is cleaned up by `teardown.yml`. After this switch, **agent memory persists** across
redeploys, reboots, and `update-modules`.

---

## Back up

A **hybrid engine** is used: `hermes backup` (consistent SQLite zip **without stopping the bot**)
for `HERMES_HOME`, plus a volume export for game data. Every backup produces a **set**
(`<timestamp>-<label>`) with **verified integrity** (sha256 + archive test) and a **manifest**.

```bash
cd ansible
ansible-playbook playbooks/backup.yml -e game=mistfall
ansible-playbook playbooks/backup.yml                          # all games
ansible-playbook playbooks/backup.yml -e game=<slug> -e backup_label=before-refactor
```

Output, under `backups/<id>/` (on the **controller**, git-ignored):

```
<stamp>-<label>-data.tar.gz      # game data
<stamp>-<label>-home.zip         # agent state/memory (hermes backup)
<stamp>-<label>-manifest.json    # links both + sizes + sha256 + image tag
```

- **Integrity**: each archive is tested (gzip/zip) on the remote host, then sha256 is
  **re-verified after transfer** to the controller. A mismatch **aborts** with a clear error.
- **Rotation**: only the last `backup_keep` sets (default **14**) are kept per game.
- **Optional freeze**: `-e backup_freeze=true` stops the container during the export (100%
  consistent snapshot, ~10 s offline). Normally unnecessary (`hermes backup` is hot-consistent).
- `backups/` can grow large — archive it elsewhere (NAS, S3) according to your policy.

> Tip: schedule a daily backup via cron or a systemd timer running `backup.yml`.

---

## Restore

Warning: restore **overwrites** the targeted volume(s). Safeguards: `-e confirm=yes`, **plus** an
automatic **safety backup** of the current state taken **before** overwriting (disable with
`-e restore_safety_backup=false`). After restore, a health check verifies the container restarts.

```bash
# Full rollback (game + agent) from a backup set (recommended):
ansible-playbook playbooks/restore.yml -e game=<slug> \
  -e set=<stamp>-<label> -e restore_what=all -e confirm=yes

# Restore ONLY game data (agent keeps running):
ansible-playbook playbooks/restore.yml -e game=<slug> \
  -e set=<stamp>-<label> -e restore_what=data -e confirm=yes

# Restore ONLY agent memory/state (game data unchanged):
ansible-playbook playbooks/restore.yml -e game=<slug> \
  -e set=<stamp>-<label> -e restore_what=home -e confirm=yes
```

- `set=` reads the **manifest** and **verifies sha256** before touching anything.
- `restore_what`: `data` | `home` | `all` (`memory` is an alias for `home`).
- Single-file mode (backward-compatible, no manifest): `-e snapshot=/abs/...-data.tar.gz`.
- `home` is restored via `hermes import` (zip) in a transient container; `data` via volume
  recreation + import.

---

## Reset

### Reset agent memory — **game data is preserved**

```bash
ansible-playbook playbooks/reset-memory.yml -e game=<slug> -e confirm=yes
```

Wipes the `HERMES_HOME` volume (memory / sessions / agent state) and restarts. **Game data**
(the `data` volume, including `.banquier/`) is **untouched**. An automatic `pre-reset-memory`
safety backup is taken first — reversible with
`restore.yml -e set=<…pre-reset-memory> -e restore_what=home`.

### Reset the Banker runtime (advanced)

```bash
ansible-playbook playbooks/reset-banquier.yml -e game=<slug> -e confirm=yes
# + purge timestamped snapshots: -e purge_snapshots=yes
```

Purges `ledger-*` / `pending-*` / `snap-*.json` from the Banker (if a turn got stuck), without
touching game content. `snapshots/` and `scoreboard.json` are kept by default.

---

## Operations matrix

| Need | Command |
|---|---|
| **Back up game + agent memory** | `backup.yml -e game=<slug>` |
| **Restore game + agent memory** | `restore.yml -e game=<slug> -e set=<set> -e restore_what=all -e confirm=yes` |
| **Restore game data only** | `… -e restore_what=data …` |
| **Reset agent memory (keep game)** | `reset-memory.yml -e game=<slug> -e confirm=yes` |

> **By default, everything is kept** (game + agent memory): agent memory persists on its volume,
> backups are integrity-verified, and every destructive operation takes an automatic safety net.
> Reset and teardown require explicit confirmation (plus `force_prod=yes` to destroy production
> volumes).

---

## Extracting game data for inspection

To inspect or edit files outside the container:

```bash
podman run --rm -v hermes-mistfall-data:/d:ro,Z \
  -v "$PWD/extract":/out:Z docker.io/library/alpine \
  sh -c "cp -a /d/. /out/"
```

> **Initial data** remains versioned in `data/mj-tonnerre/campagnes/<data_dir>/` (the seed).
> **Live data** (modified during play) is in the volume — **backups are the source of truth**.

## Recommended strategy

- Back up **before** every significant `redeploy` / `update-modules` (the automatic safety backup
  already covers restore / reset / teardown).
- Periodically test a restore on a **throwaway instance** (`-e instance=test1`).
- Archive `backups/` outside the deployment host (NAS, S3); local rotation keeps only
  `backup_keep` sets.
