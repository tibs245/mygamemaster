# 07 — Updating (credentials, config, modules) & Managing Instances

Three types of update, from lightest to heaviest. Each one **preserves game data and agent
memory** (the `data` and `home` volumes are never recreated or re-seeded).

| What to change | Playbook | Rebuilds image? | Effect |
|---|---|---|---|
| A **secret** (API key, Discord token) | `update-credentials.yml` | no | rewrites the `.env`, restarts |
| **Config** (model, persona/SOUL, Discord settings) | `update-config.yml` | no | re-renders `config.yaml` + `SOUL.md`, restarts |
| A **module** (skill, script) | `update-modules.yml` | **yes** | rebuild image + recreate container |

All playbooks accept `-e game=<slug>` (one instance) or no game flag (all games).

## Recommended path: `update.yml` (all-in-one, with safety net)

For a **safe single-command update**, use the orchestrator. It chains
`backup (safety net) → targeted update → smoke-test → status` with **one vault prompt**:

```bash
# Update modules (default) — backs up first, then rebuild + recreate
ansible-playbook ansible/playbooks/update.yml \
  -e game=mistfall -e confirm=yes --ask-vault-pass

# Lighter variants (no rebuild)
ansible-playbook ansible/playbooks/update.yml -e game=<slug> -e what=config
ansible-playbook ansible/playbooks/update.yml -e what=credentials --ask-vault-pass   # all games
```

`what` is `modules` (default), `config`, or `credentials`. **No** variant touches game data or
agent memory — only skills/hooks/scripts, `config.yaml`, and `SOUL.md` change.

### The two safeguards

- **Confirmation** (`-e confirm=yes`): required whenever the container is **recreated**
  (`what=modules`, or `redeploy.yml` / `update-modules.yml` run directly). Without it, the
  playbook stops before any change and prints a summary of what will be rebuilt and what is
  preserved. `config` and `credentials` (simple restart) do not require it.
- **Automatic backup**: a hybrid backup (data + memory, integrity-verified) is taken **before**
  any modification. If it fails, nothing is altered (`any_errors_fatal`). To skip it during fast
  dev iteration: `-e skip_backup=true`.

> `redeploy.yml` and `update-modules.yml` carry **the same safeguards** when run directly:
> confirmation + safety backup. `update.yml` remains the guided path (adds smoke-test + status).

## Updating credentials

Secrets live in the vault. Edit them, then replay only the `.env` write:

```bash
ansible-vault edit ansible/inventory/group_vars/all/vault.yml      # change the key/token
ansible-playbook ansible/playbooks/update-credentials.yml \
  -e game=mistfall --ask-vault-pass
```

To roll all instances over to a new shared OpenRouter key:

```bash
ansible-playbook ansible/playbooks/update-credentials.yml --ask-vault-pass
```

## Updating config

Edit the `games.yml` entry for the game (model, `soul_extra`, …) or a template
(`ansible/templates/config.yaml.j2`, `SOUL.md.j2`), then:

```bash
ansible-playbook ansible/playbooks/update-config.yml -e game=mistfall
```

`config.yaml` and `SOUL.md` are re-rendered; the instance restarts only if something changed
(idempotent).

## Updating modules

See also [`04-improve-the-modules.md`](04-improve-the-modules.md). Short form:

```bash
# Edit modules/… then:
ansible-playbook ansible/playbooks/update-modules.yml -e game=mistfall --ask-vault-pass
```

(`update-modules.yml` is an alias for `redeploy.yml`: image rebuild + container recreate. In
development mode, prefer `deploy -e dev_modules=true` + a plain `restart`.)

## Managing multiple instances

Each game is an **independent instance** (container + volumes + dedicated systemd unit). They can
be driven all at once or one by one.

### Check status

```bash
ansible-playbook ansible/playbooks/status.yml                       # all
ansible-playbook ansible/playbooks/status.yml -e game=mistfall
```

Shows per instance: systemd service state (`active`/`inactive`), container state, volumes.

### Control (start / stop / restart)

```bash
ansible-playbook ansible/playbooks/control.yml -e action=restart                    # all
ansible-playbook ansible/playbooks/control.yml -e action=stop -e game=mistfall
```

### Direct systemd equivalents

```bash
systemctl --user start|stop|restart|status hermes-<slug>
podman ps --filter name=hermes-          # all MJ containers
```

## Recommended update sequence

`update.yml` **automates** this sequence (and is the recommended path):

1. `backup.yml` (safety net) →
2. targeted update (`update-credentials` / `update-config` / `update-modules`) →
3. `smoke-test.yml` →
4. `status.yml` to confirm the instance is `active`.

Run steps manually only in specific cases (e.g. to inspect results between steps). In normal
usage, prefer `update.yml` which applies the safety net automatically.
