# Spec — Hermes OCI Image + modules

## Objective

A reproducible image containing **Hermes installed** and **our baked modules**, ready to launch the
Discord gateway of a campaign. Built once, shared by all campaign containers.

## Base

- Base: `docker.io/nikolaik/python-nodejs:python3.11-nodejs20` — this is the image that the original
  Hermes config already designates (`terminal.docker_image`), so the environment expected by the
  skills (Python 3.11 + Node 20). Guarantees that `clock.py`, `validate_schema.py`, etc. run.
- Lightweight alternative possible (`debian:stable-slim` + python/node) — not chosen by default to
  remain aligned with the original environment.

## Steps (Containerfile.j2)

```dockerfile
FROM {{ hermes_base_image }}

# 1. Base tools + skill script dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates git jq tini && \
    rm -rf /var/lib/apt/lists/*

# 2. Hermes installation (official method)
#    install.sh places the binary under /opt/hermes/.venv/bin/hermes
ENV HERMES_INSTALL_DIR=/opt/hermes
RUN curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
ENV PATH="/opt/hermes/.venv/bin:${PATH}"

# 3. Our modules (baked for reproducibility)
COPY modules/ /opt/modules/

# 4. Python dependencies of skill scripts (if requirements present)
RUN if [ -f /opt/modules/gaming/mygamemaster/scripts/requirements.txt ]; then \
      /opt/hermes/.venv/bin/pip install -r /opt/modules/gaming/mygamemaster/scripts/requirements.txt ; \
    fi

# 5. Hermes HOME + entrypoint
ENV HOME=/opt/hermes-home
RUN mkdir -p /opt/hermes-home /opt/data
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
```

> **Confirm on first build**: the exact name of the install variable and the final location of the
> binary (`/opt/hermes/.venv/bin/hermes`, confirmed by `archive_hermes/home/bin/hermes`). If
> `install.sh` imposes a per-user layout, adjust `HERMES_INSTALL_DIR`/`PATH` accordingly.

## entrypoint.sh (entrypoint.sh.j2)

Responsibilities:
1. Verify that `config.yaml` and `SOUL.md` are present in `$HOME` (mounted/provided).
2. Export secrets from the environment (injected via `--env-file` / systemd).
3. Launch the Hermes **Discord gateway** (command to finalize per doc — placeholder
   documented in the template).

```bash
#!/usr/bin/env bash
set -euo pipefail
export HOME=/opt/hermes-home

[[ -f "$HOME/config.yaml" ]] || { echo "config.yaml missing"; exit 1; }

# Non-interactive auth if necessary (key/token via env), then gateway startup.
# ⚠️ Command to validate on first real run (see architecture.md §5):
exec hermes gateway start --platform discord
```

## Modules: baked + dev bind-mount

- **Production**: modules baked into the image (`COPY modules/`). Redeploy = rebuild + recreate.
- **Development** (`-e dev_modules=true`): bind-mount `../modules` to `/opt/modules` in
  `podman run`, to iterate on a skill without rebuild. Documented in `docs/04-ameliorer-les-modules.md`.

## Tag & versioning

- Default tag: `mygamemaster:latest` + `mygamemaster:{{ image_version }}` (date or git short SHA
  passed as variable). Allows reverting to a previous image if a redeploy regresses.
