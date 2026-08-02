# 08 — Multiple Instances & Test Instances

## Two axes of multiplicity

1. **Multiple games on the same host** — already native: each game (`mistfall`, `emberfall`, …)
   has its own container, volumes, and systemd unit. Nothing special to do.
2. **One game deployed N times** — the **instance** dimension. Useful for testing an evolution on
   an **isolated copy** without touching the live session.

## The concept: `instance` and `deploy_id`

| Variable | Role |
|---|---|
| `game` (or `campagne`) | which game (source data) — e.g. `mistfall` |
| `instance` | which copy of that game — default `main` (= production) |
| `deploy_id` | computed identifier that names **everything**: `<slug>` if `main`, otherwise `<slug>-<instance>` |

`deploy_id` names the container, volumes (`data` / `home`), systemd unit, `.env` file, and
rendered configs. Two instances therefore share **nothing**.

```
instance=main   → hermes-mistfall               (production)
instance=test1  → hermes-mistfall-test1         (isolated test copy)
instance=test2  → hermes-mistfall-test2         (another test copy)
```

> Backward-compatible: without `-e instance`, `instance=main` is assumed → names are exactly
> what they were before.

## Deploy a test instance

```bash
ansible-playbook ansible/playbooks/deploy.yml \
  -e game=mistfall -e instance=test1 \
  -e discord_secret_key=discord_token_test \
  --ask-vault-pass
```

What happens:
- new volumes `hermes-mistfall-test1-{data,home}`;
- **seeded** from the same campaign data (`data/.../example-mistfall/`) → isolated copy;
- fresh memory, independent from production.

### Discord tokens and live instances

Two gateways **cannot share the same token** at the same time. To run a test instance
**connected to Discord**, give it its **own bot**:

1. Add a key to the vault, e.g. `discord_token_test: "…"`.
2. Point the instance at it with `-e discord_secret_key=discord_token_test`.

You can also override other parameters for the test, e.g. the model:
`-e model=deepseek/deepseek-v4-pro`.

> For **offline tests** (validating a skill script, a data schema) without Discord, an instance
> can run without a dedicated bot — the gateway will fail to connect, but volumes and scripts
> remain usable (`podman exec`, validation, etc.).

## Managing test instances

All commands accept `-e instance=`:

```bash
# status (global view = ALL instances, including dynamic test ones)
ansible-playbook ansible/playbooks/status.yml

# control a test instance
ansible-playbook ansible/playbooks/control.yml -e action=restart \
  -e game=mistfall -e instance=test1

# back up / update a test instance (same playbooks)
ansible-playbook ansible/playbooks/backup.yml        -e game=mistfall -e instance=test1
ansible-playbook ansible/playbooks/update-config.yml -e game=mistfall -e instance=test1
```

## Destroy a test instance

```bash
# Stop + remove container / unit / env / configs (VOLUMES are kept):
ansible-playbook ansible/playbooks/teardown.yml \
  -e game=mistfall -e instance=test1

# Remove everything including data+home volumes (IRREVERSIBLE):
ansible-playbook ansible/playbooks/teardown.yml \
  -e game=mistfall -e instance=test1 \
  -e remove_volumes=yes -e confirm=yes
```

`teardown` refuses to delete volumes without `-e confirm=yes`, and **warns** if you target
`instance=main` (production).

## Recommended test workflow

1. **Clone**: `deploy -e game=… -e instance=testN -e discord_secret_key=discord_token_test`.
2. **Experiment**: edit `modules/`, `update-modules -e instance=testN`, observe.
3. **Compare** safely — `instance=main` (production) is untouched.
4. **Clean up**: `teardown -e instance=testN -e remove_volumes=yes -e confirm=yes`.
