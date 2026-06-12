# 05 — Lifecycle

The complete daily loop: **back up → deploy → test → improve → redeploy**.

```
        ┌──────────────┐
        │  build-image │  (once, then on every module change)
        └──────┬───────┘
               ▼
   ┌───────────────────────┐      ┌──────────────┐
   │       deploy          │─────▶│  smoke-test  │
   │ (renders config+SOUL, │      │  (verifies)  │
   │  volumes, Quadlet)    │      └──────┬───────┘
   └───────────────────────┘             │ ok
               ▲                          ▼
               │                  ┌──────────────┐
               │                  │  in service  │  systemctl --user
               │                  │ (Discord     │  podman logs
               │                  │  gateway)    │
               │                  └──────┬───────┘
               │                          │ needs to evolve
        ┌──────┴───────┐                  ▼
        │   redeploy   │◀────────┌──────────────┐
        │ (rebuild +   │         │   improve    │  edit modules/
        │  recreate)   │         │   modules    │  (see doc 04)
        └──────────────┘         └──────────────┘
               ▲
               │  always before a risky change
        ┌──────┴───────┐
        │    backup    │  data + home → backups/<slug>/
        └──────────────┘   (restore if needed, see doc 03)
```

## Command cheatsheet

| Action | Command |
|---|---|
| Build the image | `ansible-playbook playbooks/build-image.yml` |
| Deploy one game | `ansible-playbook playbooks/deploy.yml -e game=<slug> --ask-vault-pass` |
| Deploy all games | `ansible-playbook playbooks/deploy.yml --ask-vault-pass` |
| Run smoke-test | `ansible-playbook playbooks/smoke-test.yml -e game=<slug>` |
| Back up | `ansible-playbook playbooks/backup.yml -e game=<slug>` |
| Rebuild + recreate | `ansible-playbook playbooks/redeploy.yml -e game=<slug> --ask-vault-pass` |
| Restore | `ansible-playbook playbooks/restore.yml -e game=<slug> -e set=<s> -e restore_what=all -e confirm=yes` |
| Update credentials only | `ansible-playbook playbooks/update-credentials.yml -e game=<slug> --ask-vault-pass` |
| Update config only | `ansible-playbook playbooks/update-config.yml -e game=<slug>` |
| Update modules only | `ansible-playbook playbooks/update-modules.yml -e game=<slug> --ask-vault-pass` |
| Show instance status | `ansible-playbook playbooks/status.yml [-e game=<slug>]` |
| Control instances | `ansible-playbook playbooks/control.yml -e action=start\|stop\|restart [-e game=<slug>]` |
| Deploy a test copy | `ansible-playbook playbooks/deploy.yml -e game=<slug> -e instance=test1 -e discord_secret_key=discord_token_test --ask-vault-pass` |
| Destroy an instance | `ansible-playbook playbooks/teardown.yml -e game=<slug> -e instance=test1 [-e remove_volumes=yes -e confirm=yes]` |
| Status / logs | `systemctl --user status hermes-<id>` · `podman logs -f hermes-<id>` |

> **Instances**: `-e instance=<name>` deploys an **isolated copy** of a game
> (`deploy_id = <slug>-<instance>`). All playbooks accept it — details in
> [`08-instances-de-test.md`](08-instances-de-test.md).

> **Targeted updates**: credentials / config / modules can be updated independently, without
> touching data or memory — details in [`07-mettre-a-jour.md`](07-mettre-a-jour.md).

## Common scenarios

**Initial launch**
`build-image` → (vault ready) → `deploy -e game=…` → `smoke-test` → watch `podman logs`.

**Evolving a rule or skill**
`backup` → edit `modules/` → `redeploy -e game=…` → `smoke-test`.

**Recovering from a bad operation**
`restore -e game=… -e set=… -e restore_what=all -e confirm=yes` → `smoke-test`.

**Testing an idea safely**
Deploy a throwaway instance (`-e instance=testN -e discord_secret_key=discord_token_test`),
experiment, then `teardown -e instance=testN -e remove_volumes=yes -e confirm=yes`.

## Persistence

Containers are **Quadlet** units (systemd user) with `Restart=always`. To have them come back
after a machine reboot with no open session:

```bash
loginctl enable-linger $USER
```
