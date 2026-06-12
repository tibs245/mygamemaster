# 02 — Deploying a Game

## 1. Build the image (once)

The image bundles Hermes + all modules and is shared by every game instance.

```bash
cd ansible
ansible-playbook playbooks/build-image.yml
podman images | grep hermes-mj          # sanity check
```

Only rebuild when you **modify a module** (see [`04`](04-ameliorer-les-modules.md)).

## 2. Declare the game in `games.yml`

Open `ansible/inventory/games.yml` (copy from `games.example.yml` if you haven't yet) and add
one entry under `games:`:

```yaml
games:
  - slug: mistfall                # short id — names the container, volumes, systemd unit
    data_dir: example-mistfall    # folder under data/mj-tonnerre/campagnes/
    title: "Mistfall"             # human-readable name
    model: minimax/minimax-m3     # LLM the GM runs on (OpenRouter model id)
    provider: openrouter
    language: en                  # language the GM speaks to players
    discord_secret_key: discord_token_mistfall   # key to look up in vault.yml
    soul_extra: |
      ## Persona of this instance

      You are **MJ Tonnerre the Veiled**: patient, wry, sparing with words. Your menace never
      shouts — it seeps through sensory detail: what the character hears in the fog, the smell of
      wet stone, a rope that hums a little wrong. You speak in perceptions, never declarations.

      **Inspirations**: gothic mystery, slow-burn dread, fae bargains.
      **System**: generic d20 — Crunch 3/5.
      **Tone**: eerie, atmospheric, mysterious.
```

Add the matching Discord token to the vault:

```bash
ansible-vault edit ansible/inventory/group_vars/all/vault.yml
# add:  discord_token_mistfall: "Bot-token-from-Discord-Developer-Portal"
```

That is everything to declare. The dynamic inventory (`hermes_inventory.py`) reads `games.yml`
and exposes each entry as an Ansible host of the `campagnes` group.

## 3. Deploy

```bash
# Deploy one game:
ansible-playbook playbooks/deploy.yml -e game=mistfall --ask-vault-pass

# Deploy all games at once (omit -e game):
ansible-playbook playbooks/deploy.yml --ask-vault-pass

# Legacy alias (still works):
ansible-playbook playbooks/deploy.yml -e campagne=mistfall --ask-vault-pass
```

What `deploy` does:
1. Verifies the image exists.
2. Renders `config.yaml` + `SOUL.md` (the campaign persona).
3. Creates volumes `hermes-<slug>-data` and `hermes-<slug>-home`.
4. **Seed**: on the very first deploy, copies `data/mj-tonnerre/campagnes/<data_dir>/` into the
   data volume.
5. Writes the environment file (secrets, mode `0600`).
6. Installs the **Quadlet** unit and starts the container.

## 4. Verify

```bash
ansible-playbook playbooks/smoke-test.yml -e game=mistfall
systemctl --user status hermes-mistfall
podman logs -f hermes-mistfall
```

The smoke-test checks: `hermes --version`, presence of all 15 skills, readability of `monde.json`.

## Stop / restart / start

```bash
systemctl --user stop    hermes-<slug>
systemctl --user start   hermes-<slug>
systemctl --user restart hermes-<slug>
```

## Adding a new game (summary)

1. Create the game data folder:
   ```bash
   cp -r data/mj-tonnerre/campagnes/_template data/mj-tonnerre/campagnes/<your-data-dir>
   ```
   Then fill in `monde.json` (the `mj-tonnerre-initiation` skill drives a questionnaire that helps
   build it, or run `!init` in Discord).
2. Add **one entry** to `ansible/inventory/games.yml` (see format above).
3. Add `discord_token_<slug>` to the vault.
4. `ansible-playbook playbooks/deploy.yml -e game=<slug> --ask-vault-pass`

For a guided walkthrough from scratch (Discord bot creation included), see
[`CREATE-A-GAME.md`](CREATE-A-GAME.md).
