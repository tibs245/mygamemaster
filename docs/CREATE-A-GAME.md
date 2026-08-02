# Create a New Game — Step-by-Step

This guide walks you through setting up a brand-new MJ Tonnerre game from scratch. Replace
`<slug>` with your chosen short identifier (lowercase, hyphens only — e.g. `mistfall`), and
`<title>` with the human-readable name (e.g. "Mistfall").

For AI-assisted onboarding (the assistant asks you questions and generates the right commands),
see [`AI-ONBOARDING-PROMPT.md`](AI-ONBOARDING-PROMPT.md).

---

## Step 1 — Create a Discord application and bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and click
   **New Application**. Give it any name (typically your game title).

2. In the left sidebar, click **Bot**, then click **Reset Token** and copy the token that
   appears. Store it safely — you will need it in Step 3.

3. On the same Bot page, scroll down to **Privileged Gateway Intents** and enable:
   - **Message Content Intent** (required — the GM reads message text)
   - **Server Members Intent** (recommended — used for player look-ups)

4. Generate an invite URL: go to **OAuth2 → URL Generator**, tick the `bot` scope, then tick the
   minimum permissions:
   - Read Messages / View Channels
   - Send Messages
   - Read Message History
   - Add Reactions (optional, used for dice)

   Copy the generated URL, open it in a browser, and invite the bot to your server.

---

## Step 2 — Get API keys

**OpenRouter** (required — provides the LLM):

1. Create an account at <https://openrouter.ai>.
2. Go to **Keys** and create a new key.
3. Copy the key (starts with `sk-or-v1-…`).

**MiniMax** (optional — enables voice/TTS narration):

1. Create an account at <https://www.minimax.io>.
2. Go to **API Keys** and generate one.
3. Copy the key. If absent, the voice axis is silently disabled — nothing breaks.

---

## Step 3 — Add the Discord token to the Ansible vault

If you do not have a `vault.yml` yet, create it from the example:

```bash
cd ansible/inventory/group_vars/all
cp vault.example.yml vault.yml
ansible-vault encrypt vault.yml
```

Open the vault and add the token for your game:

```bash
ansible-vault edit ansible/inventory/group_vars/all/vault.yml
```

Add (or verify) these lines:

```yaml
openrouter_api_key: "sk-or-v1-YOUR_KEY"
# minimax_api_key: "YOUR_MINIMAX_KEY"    # optional

discord_token_<slug>: "Bot-TOKEN-FROM-DISCORD-DEVELOPER-PORTAL"
```

The key name `discord_token_<slug>` must match the `discord_secret_key` field you will write in
`games.yml` in the next step.

---

## Step 4 — Add one entry to `games.yml`

Open (or create from the example) `ansible/inventory/games.yml`:

```bash
cd ansible/inventory
# first time only:
cp games.example.yml games.yml
```

Fill in the `connection:` block at the top (your server's SSH details), then append your game
under `games:`:

```yaml
connection:
  host: your-server.example.com   # IP or hostname of the deployment host
  port: 22
  user: youruser
  ssh_key: ~/.ssh/id_ed25519
  python: /usr/bin/python3

games:
  - slug: <slug>                              # e.g. mistfall
    data_dir: <slug>                          # folder under data/mygamemaster/campaigns/
    title: "<title>"                          # e.g. "Mistfall"
    model: minimax/minimax-m3                 # LLM model id on OpenRouter
    provider: openrouter
    language: en                              # language the GM speaks (en, fr, …)
    discord_secret_key: discord_token_<slug>  # must match the vault key
    soul_extra: |
      ## Persona of this instance

      You are **MJ Tonnerre — <title>**: <describe the GM's voice, tone, style>.

      **Inspirations**: <list 2-3 inspirations>.
      **System**: <RPG system and crunch level>.
      **Tone**: <adjectives>.
```

That is the **only** file you need to edit to declare the game. The dynamic inventory reads it
automatically.

---

## Step 5 — Build the world

Choose one of two paths:

### Option A: edit `world.json` manually

Copy the template folder:

```bash
cp -r data/mygamemaster/campaigns/_template \
      data/mygamemaster/campaigns/<slug>
```

Open `data/mygamemaster/campaigns/<slug>/world.json` and fill in:
- `meta`: title, language, hooks toggles, verbosity
- `monde`: geography, time, lore
- `lieux`: starting locations
- `pnj`: key NPCs
- `factions`: factions and their goals

### Option B: run the in-game onboarding questionnaire

Deploy the bot first (Step 6), then type `!init` in your Discord game channel. The
`mygamemaster-initiation` skill walks you through every question and writes `world.json`
interactively.

For AI help building the world content, paste the prompt from
[`AI-ONBOARDING-PROMPT.md`](AI-ONBOARDING-PROMPT.md) into Claude or ChatGPT.

### Both paths: capture the player profile

Copy the template into the campaign folder and fill it from the first session:

```bash
cp modules/gaming/mygamemaster/references/player-profile-template.md \
   data/mygamemaster/campaigns/<slug>/player-profile.md
```

It records the player's control signals, agency contract, pacing dials, standing policies and
feedback protocol — the things a table otherwise rediscovers by trial and error, one rejected
session at a time. Option B asks for them directly (Block 6 of the questionnaire) and writes the
file for you. Each line is dated, sourced to a session, and marked `locked` / `observed` /
`hypothesis`; entries are superseded, never deleted. Update it at every close.

**Taste here, doctrine there.** What is specific to *this* player goes in the campaign's own
`<slug>/player-profile.md`. The GM conduct rules that apply to every table live in
[`modules/gaming/mygamemaster/references/locked-lessons.md`](../modules/gaming/mygamemaster/references/locked-lessons.md)
— 61 rules with stable IDs, loaded by the GM skill at every session. Do not copy rules between the
two files.

---

## Step 6 — Deploy

Build the shared image (once, or after any module change):

```bash
cd ansible
ansible-playbook playbooks/build-image.yml
```

Deploy your game:

```bash
ansible-playbook playbooks/deploy.yml -e game=<slug> --ask-vault-pass
```

This creates volumes, seeds the data, writes secrets, installs the Quadlet unit, and starts the
container.

---

## Step 7 — Verify with the smoke-test

```bash
ansible-playbook playbooks/smoke-test.yml -e game=<slug>
systemctl --user status hermes-<slug>
podman logs -f hermes-<slug>
```

The smoke-test checks: `hermes --version`, all 15 skills present, `world.json` readable. If
everything is green, your bot is live in Discord.

---

## What's next?

- Daily operations and command cheatsheet → [`05-lifecycle.md`](05-lifecycle.md)
- Backups and rollbacks → [`03-backup-and-restore.md`](03-backup-and-restore.md)
- Improving the GM's skills → [`04-improve-the-modules.md`](04-improve-the-modules.md)
- Runtime hooks (LLM judge, verbosity) → [`09-runtime-hooks.md`](09-runtime-hooks.md)
- Test instances (try changes without risking the live game) → [`08-test-instances.md`](08-test-instances.md)
