# Spec — Ansible Suite

## Conventions

- **Required collection**: `containers.podman` (`ansible-galaxy collection install containers.podman`).
- **Connection**: SSH to the deployment host. Connection parameters (host, port, user, SSH key,
  Python interpreter) are declared **once** in the `connection:` block of
  `ansible/inventory/games.yml` and exposed automatically by the dynamic inventory.
- **Pivot variable**: `campagne_slug` (game slug), derived from the `slug` field in `games.yml`.
  Use `-e game=<slug>` on the command line to target a single game; `-e campagne=<slug>` is a
  legacy alias that still works.
- **Instance dimension**: `instance` (default `main`) allows deploying the **same campaign
  multiple times** (e.g. for testing). The computed identifier
  `deploy_id = <slug>` (when `instance=main`) or `<slug>-<instance>` names the container,
  volumes, systemd unit, `.env` file, and rendered configs — so two instances share nothing.
  Defined in `group_vars/all/main.yml`. Backwards-compatible (`instance=main` → names
  unchanged). The seed always comes from `campagne_data_dir` → each instance has its own
  isolated data copy and its own memory.
- **Idempotence**: all roles are idempotent (declarative volume/container creation).

## Inventory & variables

```
inventory/
├── games.example.yml             # committed example — copy to games.yml to get started
├── games.yml                     # YOUR real table (git-ignored) — one row per game
├── hermes_inventory.py           # dynamic inventory: reads games.yml → campaigns group
├── group_vars/all/
│   ├── main.yml                  # global defaults (image, paths, default model, feature flags)
│   └── vault.yml                 # SECRETS encrypted with ansible-vault
└── host_vars/                    # LEGACY — no longer used; superseded by games.yml
```

### How the inventory works

`ansible.cfg` sets `inventory = inventory/hermes_inventory.py`. The script reads
`games.yml` (falling back to `games.example.yml` if it does not exist yet) and exposes every
entry under `games:` as an Ansible host in the `campaigns` group. The shared `connection:` block
is mapped to Ansible connection variables for the whole group.

**To add a campaign: append ONE entry to `games.yml` and add its Discord token to the vault.
Nothing else.**

### `games.yml` — structure

```yaml
# Connection to the host that runs the containers (shared by all games)
connection:
  host: your-server.example.com   # IP or hostname of the deployment host
  port: 22
  user: youruser
  ssh_key: ~/.ssh/id_ed25519
  python: /usr/bin/python3

games:
  - slug: mistfall                # short id → container / volumes / unit / env file
    data_dir: example-mistfall    # folder under data/mj-tonnerre/campaigns/
    title: "Mistfall"
    model: minimax/minimax-m3     # LLM model id (OpenRouter format)
    provider: openrouter
    language: en                  # language the GM uses with players
    discord_secret_key: discord_token_mistfall   # key looked up in vault.yml
    soul_extra: |
      ## Persona of this instance
      ...
```

### Field → role variable mapping

`hermes_inventory.py` translates each table field to the variable name consumed by the role and
templates:

| `games.yml` field    | Role variable           |
|----------------------|-------------------------|
| `slug`               | `campagne_slug`         |
| `data_dir`           | `campagne_data_dir`     |
| `title`              | `campagne_titre`        |
| `model`              | `model`                 |
| `provider`           | `provider`              |
| `language`           | `default_language`      |
| `discord_secret_key` | `discord_secret_key`    |
| `soul_extra`         | `soul_extra`            |

The role variable names (`campagne_slug`, `campagne_titre`, etc.) are **unchanged** from the
previous system.

### `group_vars/all/main.yml` (excerpt)

```yaml
hermes_image_name: hermes-mj
hermes_image_tag: latest
hermes_base_image: docker.io/nikolaik/python-nodejs:python3.11-nodejs20
container_data_root: /opt/data/mj-tonnerre/campaigns   # inside the container
container_home: /opt/hermes-home                        # inside the container
repo_root: "{{ playbook_dir | dirname | dirname }}"    # mono-repo root
backups_dir: "{{ repo_root }}/backups"
default_model: minimax/minimax-m3
default_provider: openrouter
default_language: fr
instance: main
deploy_id: "{{ campagne_slug if (instance | string) in ['main', ''] else (campagne_slug ~ '-' ~ instance) }}"
```

Secrets are **never** in `games.yml` or `main.yml`: `discord_secret_key` is only the *name* of
the variable to resolve from `vault.yml`.

## Roles

| Role | Input | Effect |
|---|---|---|
| `hermes_image` | base image, modules | renders `Containerfile`, runs `podman build`, tags the image |
| `hermes_deploy` | campaign variables | renders `config.yaml`+`SOUL.md`, creates data/home volumes, (re)creates the container + Quadlet unit, starts it |
| `hermes_backup` | campaign slug | `tar` of data+home volumes → `backups/<slug>/<timestamp>.tar.gz` |
| `hermes_restore` | campaign slug, `snapshot` | restores a tar into the volumes (with confirmation) |

### `hermes_deploy` — targeted-update split

`tasks/main.yml` imports two reusable sub-files (via `include_role` + `tasks_from`), allowing a
single aspect to be updated without replaying everything:

| `tasks_from` | Contents | Playbook that uses it alone |
|---|---|---|
| `config` | renders `config.yaml` + `SOUL.md`, notifies `restart_campagne` | `update-config.yml` |
| `credentials` | resolves the token (vault) → writes the `.env` at `0600`, notifies `restart_campagne` | `update-credentials.yml` |
| `main` (full) | assert + image check + `config` + volumes/seed + `credentials` + Quadlet + start | `deploy.yml` |

### `hermes_deploy` — sequence

1. Verify that the image exists (explicit failure if missing → run `build-image.yml` first).
2. Render `config.yaml` and `SOUL.md` into `~/.config/hermes-mj/rendered/<deploy_id>/` on the
   deployment host.
3. Create (if absent) the volumes `hermes-<deploy_id>-data` and `hermes-<deploy_id>-home`.
4. **Initial data seed**: if the data volume is empty, copy
   `data/mj-tonnerre/campaigns/<campagne_data_dir>/` into it (first deployment only).
5. Generate the Quadlet unit
   `~/.config/containers/systemd/hermes-<deploy_id>.container`.
6. `systemctl --user daemon-reload` + `systemctl --user start hermes-<deploy_id>` (handler).

### Quadlet (`hermes-campagne.container.j2`) — key sections

```ini
[Unit]
Description=Hermes MJ Tonnerre — {{ campagne_titre }}
After=network-online.target

[Container]
Image={{ hermes_image_name }}:{{ hermes_image_tag }}
ContainerName=hermes-{{ deploy_id }}
Environment=HOME={{ container_home }}
Environment=HERMES_HOME={{ container_home }}
EnvironmentFile={{ host_env_dir }}/{{ deploy_id }}.env
Volume=hermes-{{ deploy_id }}-data:{{ container_data_root }}:z
Volume=hermes-{{ deploy_id }}-home:{{ container_home }}:z
Volume={{ rendered_dir }}/config.yaml:/opt/hermes-cfg-src/config.yaml:ro,Z
Volume={{ rendered_dir }}/SOUL.md:{{ container_home }}/SOUL.md:ro,Z

[Service]
Restart=always
TimeoutStartSec=120

[Install]
WantedBy=default.target
```

Notable design decisions:
- The full `HERMES_HOME` volume (`hermes-<deploy_id>-home`) is mounted rather than just the
  `memory/` sub-directory, so that all agent state (state.db, memories/, sessions/,
  kanban.db, gateway_state.json) is persistent across container recreations.
- `config.yaml` is bind-mounted read-only as a *source* at `/opt/hermes-cfg-src/config.yaml`
  and copied into `HERMES_HOME` by the container entrypoint on every start. This avoids
  an `EBUSY` atomic-rename failure that would prevent Hermes from saving the hook approval
  allowlist.
- `:z` (shared SELinux label) is used on named volumes to avoid MCS category conflicts on
  container recreate.

The per-campaign `.env` file (secrets resolved from the vault) is written at `0600` to
`~/.config/hermes-mj/<deploy_id>.env` on the deployment host and is **never** committed.

## Playbooks

| Playbook | Role(s) | Usage |
|---|---|---|
| `build-image.yml` | `hermes_image` | `ansible-playbook playbooks/build-image.yml` |
| `deploy.yml` | `hermes_deploy` | `… deploy.yml` (all) or `… deploy.yml -e game=mistfall` (one) |
| `backup.yml` | `hermes_backup` | `… backup.yml` or `… backup.yml -e game=mistfall` |
| `restore.yml` | `hermes_restore` | `… restore.yml -e game=mistfall -e snapshot=<file>` |
| `redeploy.yml` | `hermes_image` + `hermes_deploy` | rebuild then redeploy (volumes preserved) |
| `smoke-test.yml` | ad hoc | start, verify `hermes --version`, skills listed, `world.json` readable |
| `update-config.yml` | `hermes_deploy` (`tasks_from: config`) | re-render config+SOUL, restart — no rebuild |
| `update-credentials.yml` | `hermes_deploy` (`tasks_from: credentials`) | rewrite the `.env` from vault, restart |
| `update-modules.yml` | `import_playbook: redeploy.yml` | rebuild image + recreate (explicit alias) |
| `update.yml` | `hermes_deploy` | safe rolling update (pull image, redeploy, verify) |
| `status.yml` | ad hoc (read-only) | global `podman` overview + per-campaign/instance detail |
| `control.yml` | ad hoc | `-e action=start\|stop\|restart` on one instance or all |
| `teardown.yml` | ad hoc | destroy an instance (container/unit/env); volumes via `-e remove_volumes=yes -e confirm=yes` |

All playbooks accept `-e game=<slug>` (one campaign) or no `-e game` (all declared campaigns).
The legacy `-e campagne=<slug>` still works as an alias. This is the multi-instance management
mechanism: N campaigns = N inventory hosts = N isolated containers/volumes/systemd units.

## Static checks

```bash
ansible-lint ansible/
ansible-playbook --syntax-check ansible/playbooks/*.yml
ansible-playbook playbooks/deploy.yml -e game=mistfall --check
ansible-vault view inventory/group_vars/all/vault.yml   # secrets readable with the vault password
```
