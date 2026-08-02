# 04 — Improving Modules

Modules (`modules/gaming/mygamemaster*`) are the GM's intelligence. Here is how to evolve them
**without losing any game data**.

## Standard loop (production)

1. **Edit** a skill, e.g. `modules/gaming/mygamemaster-outils/SKILL.md` or a script such as
   `modules/gaming/mygamemaster/scripts/clock.py`.
2. **Back up** as a precaution (recommended before any redeploy):
   ```bash
   ansible-playbook ansible/playbooks/backup.yml -e game=mistfall
   ```
3. **Redeploy** (rebuild image + recreate container, volumes preserved):
   ```bash
   ansible-playbook ansible/playbooks/redeploy.yml -e game=mistfall --ask-vault-pass
   ```
4. **Verify**:
   ```bash
   ansible-playbook ansible/playbooks/smoke-test.yml -e game=mistfall
   podman logs --tail 50 hermes-mistfall
   ```

`redeploy` rebuilds the image (modules baked in) then recreates containers on the new image.
The `data` and `home` volumes are **never touched**.

## Fast loop (development)

To iterate without a full rebuild on every change, **bind-mount** `modules/` into the container:

```bash
ansible-playbook ansible/playbooks/deploy.yml \
  -e game=mistfall -e dev_modules=true --ask-vault-pass
```

The Quadlet unit then mounts `modules/` read-only onto `/opt/modules`. A plain
`systemctl --user restart hermes-mistfall` reloads the modified code — no rebuild needed.

> To go back to production: redeploy **without** `-e dev_modules=true`, then run `redeploy` to
> bake the modules into the image.

## Testing a skill script in isolation

Skill scripts run inside the image environment:

```bash
podman run --rm mygamemaster:latest \
  python /opt/modules/gaming/mygamemaster/scripts/clock.py --help
```

To validate a campaign's data integrity (schemas):

```bash
podman run --rm -v hermes-mistfall-data:/d:ro,Z mygamemaster:latest \
  python /opt/modules/gaming/mygamemaster/scripts/validate_schema.py /d/example-mistfall
```

## Best practices

- One improvement = one commit in this repository (modules are version-controlled).
- Always `backup` before a `redeploy` that touches persistence or schemas.
- Keep the previous image tag (`mygamemaster:<date>`) so you can roll back if a regression appears:
  `podman tag mygamemaster:<date-ok> mygamemaster:latest` then redeploy.
