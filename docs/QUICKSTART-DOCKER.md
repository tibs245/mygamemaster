# Docker quickstart — build, test, and (optionally) run a live game

## Context: two distinct images

| Image | Purpose | Built by |
|---|---|---|
| **`mygamemaster-dev`** | local dev, CI, smoke-testing — no live game | `docker build` (this guide) |
| **`mygamemaster:latest`** | production — live Discord game | `ansible-playbook playbooks/build-image.yml` |

The dev image is intentionally minimal: it runs the three engine test suites so you can
validate the codebase without any credentials. Running an actual live game always requires a
Discord token and the Ansible/Podman deploy (or the manual `podman run` shown at the end of
this guide).

---

## 1. Build the dev image

From the repository root:

```bash
docker build -t mygamemaster-dev .
```

The build:
1. Uses `python:3.11-slim` as base.
2. Installs PyYAML.
3. Copies the repository (secrets and `.git` are excluded via `.dockerignore`).

Expected output ends with:

```
Successfully built <sha>
Successfully tagged mygamemaster-dev:latest
```

---

## 2. Run the test suites

```bash
docker run --rm mygamemaster-dev
```

This runs all three suites in sequence:

```
=== Suite 1 — engine scripts ===
Ran NNN tests in 0.2s
OK (skipped=N)

=== Suite 2 — runtime hooks ===
RESULT : NN/NN tests OK

=== Suite 3 — TTS pipeline ===
RESULT: NN/NN tests OK

All suites passed.
```

> **Note:** ~330 tests total across all three suites; exact counts may vary as suites grow.

Skipped tests are expected — they require real campaign data that is not committed to the
repository. The command exits 0 on success, non-zero if any suite fails.

---

## 3. Relation to the real Ansible/Podman deploy

The dev image does **not** include:

- The Hermes gateway binary (installed at build time by `playbooks/build-image.yml`).
- A rendered `config.yaml` (Ansible fills this from templates + vault).
- A Discord token or any API key.
- An `entrypoint.sh` that starts the gateway on container start.

To run a live game you need the full Ansible flow:

```bash
cd ansible
ansible-playbook playbooks/build-image.yml   # builds mygamemaster:latest with all of the above
ansible-playbook playbooks/deploy.yml -e game=<slug>
```

See [docs/01-prerequisites-and-installation.md](01-prerequisites-and-installation.md) and
[docs/02-deploy-a-campaign.md](02-deploy-a-campaign.md) for the complete walkthrough.
Or follow [docs/CREATE-A-GAME.md](CREATE-A-GAME.md) for a guided, AI-assisted setup.

---

## 4. Manual `podman run` for a live game (advanced)

If you have already built `mygamemaster:latest` with Ansible and want to start a game instance
manually (bypassing Quadlet/systemd), here is an example:

```bash
podman run -d \
  --name hermes-mistfall \
  --env DISCORD_TOKEN="<your-discord-bot-token>" \
  --env OPENROUTER_API_KEY="<your-openrouter-key>" \
  --env MINIMAX_API_KEY="<your-minimax-key-or-empty>" \
  --env HERMES_SLUG="mistfall" \
  -v hermes-mistfall-home:/opt/hermes-home:Z \
  -v hermes-mistfall-data:/opt/hermes-data:Z \
  localhost/mygamemaster:latest
```

> **Security tip:** avoid passing secrets as inline `--env` flags (they appear in `ps` output
> and shell history). Prefer `--env-file mistfall.env` with a file that is `chmod 600` and
> listed in `.gitignore`. Example:
>
> ```bash
> podman run -d --name hermes-mistfall \
>   --env-file mistfall.env \
>   -v hermes-mistfall-home:/opt/hermes-home:Z \
>   -v hermes-mistfall-data:/opt/hermes-data:Z \
>   localhost/mygamemaster:latest
> ```

> This is shown for reference. In practice Ansible manages volume creation, `config.yaml`
> rendering, and the Quadlet unit — doing it manually is error-prone. Use the playbooks.

---

## 5. Pre-built image from GHCR

A pre-built dev image is published to the GitHub Container Registry on every push to `main`
and on every version tag:

```bash
docker pull ghcr.io/tibs245/mygamemaster:latest
docker run --rm ghcr.io/tibs245/mygamemaster:latest
```

The image is built by the workflow at `.github/workflows/docker-publish.yml` using the
built-in `GITHUB_TOKEN` — no extra secrets required.

---

## 6. Publishing to Docker Hub instead (optional)

The workflow publishes to GHCR by default. To **also** publish to Docker Hub, add two repo
secrets in your GitHub repository settings:

| Secret name | Value |
|---|---|
| `DOCKERHUB_USERNAME` | your Docker Hub username |
| `DOCKERHUB_TOKEN` | a Docker Hub access token (read/write) |

Then add the following snippet to `.github/workflows/docker-publish.yml`, inside the same job,
after the GHCR login step:

```yaml
      - name: Log in to Docker Hub
        if: ${{ secrets.DOCKERHUB_USERNAME != '' }}
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}

      - name: Build and push to Docker Hub
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ secrets.DOCKERHUB_USERNAME }}/mygamemaster:latest
```

For local testing see [QUICKSTART-LOCAL.md](QUICKSTART-LOCAL.md).
