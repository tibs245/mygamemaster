# Spec — Secrets & ansible-vault

## Principle

**No secrets in plain text in the repository.** Secrets live only in
`ansible/inventory/group_vars/all/vault.yml`, **encrypted with `ansible-vault`**. At deployment,
they are rendered into a file `~/.config/hermes-mj/<slug>.env` (mode `0600`, outside the repository) and
injected into the container via `EnvironmentFile` (Quadlet) or `--env-file`.

## Inventory of secrets (mapped from the old `.env`)

| Environment variable (container) | Role | Sensitivity | Scope |
|---|---|---|---|
| `OPENROUTER_API_KEY` | model access (openrouter provider) | 🔴 secret | shared or per campaign |
| `DISCORD_BOT_TOKEN` | Discord bot token | 🔴 secret | **per campaign** (or shared bot) |
| `DISCORD_ALLOWED_USERS` | authorized IDs (access control) | 🟠 sensitive | per campaign |
| `DISCORD_HOME_CHANNEL` | main channel | 🟢 non-secret | per campaign |

The other keys from the old `.env` (`*_TOOLS_DEBUG`, `BROWSER_*`, `TERMINAL_*`) are
**configuration**, not secrets → they go in `config.yaml` / `group_vars`, not in the vault.

## Vault structure (`vault.yml`, decrypted)

```yaml
# Model key (often shared across campaigns)
openrouter_api_key: "sk-or-v1-…"

# One Discord token per campaign — key name referenced by host_vars.discord_secret_key
discord_token_naissance: "MTA…"
discord_token_jusquau_bout: "MTB…"
```

`host_vars/<campaign>.yml` contains **only the name** of the key to resolve:
```yaml
discord_secret_key: discord_token_naissance
```
The `hermes_deploy` role does: `discord_bot_token: "{{ vault[discord_secret_key] }}"`.

## Lifecycle

```bash
# Create / edit the vault
ansible-vault create  ansible/inventory/group_vars/all/vault.yml
ansible-vault edit    ansible/inventory/group_vars/all/vault.yml
ansible-vault view    ansible/inventory/group_vars/all/vault.yml

# Run a playbook that needs secrets
ansible-playbook playbooks/deploy.yml -e campagne=naissance-dun-roi --ask-vault-pass
# or: --vault-password-file ~/.config/hermes-mj/.vault_pass   (mode 0600, outside repo)
```

An example file **unencrypted** `vault.example.yml` documents the expected keys and is
committed; the real `vault.yml` (encrypted) can be committed (encryption protects it), but the
**vault password** is never committed (`.vault_pass` is git-ignored).

## Rotation

1. `ansible-vault edit vault.yml` → replace the key/token.
2. `ansible-playbook playbooks/redeploy.yml -e campagne=<slug>` (or `deploy.yml`) → regenerates
   the `.env` and recreates the container. No game data touched.

## Safeguards

- `.gitignore` blocks `.env`, `secrets.yml`, `.vault_pass`, `*.key`.
- The `smoke-test` / final verification scans the repository (excluding `archive_hermes/` and `vault.yml`)
  to ensure no `sk-…` / token has leaked.
- `security.redact_secrets: true` remains active in `config.yaml` (redaction on the Hermes side).
