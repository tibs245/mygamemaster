# 01 — Prerequisites & Installation

## Host requirements (Linux)

| Tool | Purpose | Check |
|---|---|---|
| **Podman** ≥ 4 (rootless) | runs the containers | `podman --version` |
| **systemd user** + Quadlet | persistence (auto-restart) | `systemctl --user status` |
| **Ansible** ≥ 2.16 | orchestration | `ansible --version` |
| **ansible-vault** | encrypted secrets (bundled with Ansible) | `ansible-vault --version` |
| **rsync, gzip, tar** | seeding & backups | `which rsync gzip tar` |

> **Rootless Podman** is strongly recommended (containers run as your user). To have them restart
> at boot without an open session:
> `loginctl enable-linger $USER`

## Install Ansible collections (recommended)

```bash
ansible-galaxy collection install -r ansible/requirements.yml
```

The suite drives `podman` via plain `command:` calls and works without the collection; it adds
convenience and idempotency checks.

## Set up the vault (secrets)

Secrets are **never stored in plain text**. Start from the documented example:

```bash
cd ansible/inventory/group_vars/all
cp vault.example.yml vault.yml
ansible-vault encrypt vault.yml          # prompts for a password
ansible-vault edit vault.yml             # enter your real keys
```

Keys expected (see [`../specs/secrets-et-vault.md`](../specs/secrets-et-vault.md) and
`vault.example.yml` for the full format):

```yaml
openrouter_api_key: "sk-or-v1-…"         # model access (required)
minimax_api_key: "…"                      # voice/TTS — optional, fail-open if absent
discord_token_mistfall: "…"              # one Discord bot token per game (key name must match
                                          # the discord_secret_key field in games.yml)
```

To avoid retyping the vault password on every command:

```bash
mkdir -p ~/.config/mygamemaster
printf '%s' 'MY_VAULT_PASSWORD' > ~/.config/mygamemaster/.vault_pass
chmod 600 ~/.config/mygamemaster/.vault_pass
# then uncomment vault_password_file in ansible/ansible.cfg
```

## Declare your games (`games.yml`)

All games live in a **single declarative table**: `ansible/inventory/games.yml` (git-ignored).
Copy the committed example to get started:

```bash
cd ansible/inventory
cp games.example.yml games.yml
```

Edit `games.yml`: fill in the `connection:` block (SSH host, user, key) and add your game(s)
under the `games:` list. Each entry becomes an Ansible host automatically — no other file to
touch. See [`02-deployer-une-campagne.md`](02-deployer-une-campagne.md) for the entry format and
the full deployment procedure.

## Verify everything is ready

```bash
cd ansible
ansible-lint                                    # must pass
ansible-playbook --syntax-check playbooks/deploy.yml -e game=mistfall
ansible-vault view inventory/group_vars/all/vault.yml   # your secrets should print
```
