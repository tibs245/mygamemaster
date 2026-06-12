# Security Policy

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

If you discover a security vulnerability in MyGameMaster, report it privately by emailing:

**security@your-domain.example**

Include in your report:
- A clear description of the vulnerability
- Steps to reproduce (proof-of-concept if available)
- The potential impact (what an attacker could achieve)
- Your name/handle if you wish to be credited

We will acknowledge receipt within **72 hours** and aim to provide a resolution timeline within
**7 days**. We will keep you informed as the fix progresses and credit you in the release notes
unless you prefer to remain anonymous.

---

## Scope

The following are in scope for security reports:

- **Runtime hooks** (`modules/gaming/mj-tonnerre/hooks/`) — injection, bypass, or privilege
  escalation via hook inputs
- **Ansible playbooks and templates** — misconfigurations that could expose secrets or allow
  unauthorized access to the deployment host
- **Container isolation** — ways for one campaign container to read or write another campaign's
  data or memory volumes
- **Vault handling** — anything that could cause secrets to be logged, exposed in error messages,
  or written to unencrypted files
- **Discord bot input handling** — command injection or unintended privilege escalation through
  player-controlled input

## Out of Scope

The following are **not** in scope:

- Vulnerabilities in upstream dependencies (Hermes framework, Podman, Ansible, OpenRouter) —
  report those to their respective maintainers
- Issues requiring physical access to the deployment host
- Social engineering or phishing attacks
- Denial-of-service via LLM API cost exhaustion (this is a configuration / billing concern,
  not a code vulnerability)
- Findings from automated scanners without a demonstrated impact

---

## Secrets Handling — Hard Rules

These rules apply to everyone working with this repository:

1. **Never commit `vault.yml` unencrypted.** The file `ansible/inventory/group_vars/all/vault.yml`
   must always be encrypted with `ansible-vault` before any `git add`. The example file
   (`vault.example.yml`) contains only placeholder values and is safe to commit.

2. **Never commit `.env` files or any file containing real API keys, Discord tokens, or
   passwords.** If you accidentally commit a secret, consider it compromised: rotate it
   immediately, then clean the git history.

3. **Do not log secrets.** Hook scripts and playbooks must not print API keys or tokens,
   even at DEBUG verbosity. Use masked variables in Ansible (`no_log: true`) where appropriate.

4. **One token per bot per game.** Each campaign uses a distinct Discord application and bot
   token. Never reuse a token across campaigns.

---

## Supported Versions

This project does not currently maintain separate long-term-support branches.
Security fixes are applied to the `main` branch and released as new commits.
We recommend always running the latest version.

---

## Disclosure Policy

We follow **coordinated disclosure**: we ask that you give us a reasonable period (typically
90 days) to develop and release a fix before publishing details of the vulnerability. We will
work with you to agree on a disclosure timeline that is fair to both parties and to users.
