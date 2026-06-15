# Dockerfile — MJ Tonnerre dev/test image
#
# PURPOSE: local development and CI validation only.
# Running a live game still requires a Discord token and the full Ansible/Podman
# deploy described in docs/02-deployer-une-campagne.md.
#
# Default CMD runs all three engine test suites so `docker run --rm mygamemaster-dev`
# serves as a smoke-test for the codebase without any external credentials.

FROM python:3.11-slim

LABEL org.opencontainers.image.title="mygamemaster-dev"
LABEL org.opencontainers.image.description="MJ Tonnerre engine — dev/test image"
LABEL org.opencontainers.image.source="https://github.com/tibs245/mygamemaster"

WORKDIR /app

# git is required by the hooks test suite (auto-commit tests).
# PyYAML is the only non-stdlib Python dep used by the skill scripts.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir PyYAML

# Copy the repo (most of the image weight is the modules)
COPY . .

# Default: run all three test suites.
# Each suite exits non-zero on failure, so `docker run` returns 1 if any suite fails.
CMD ["sh", "-c", "\
  echo '=== Suite 1 — engine scripts ===' && \
  cd /app/modules/gaming/mygamemaster/scripts && python3 -m unittest discover -s tests && \
  echo '=== Suite 2 — runtime hooks ===' && \
  cd /app/modules/gaming/mygamemaster/hooks && python3 test_hooks.py && \
  echo '=== Suite 3 — TTS pipeline ===' && \
  cd /app/modules/gaming/mygamemaster-tts/tests && python3 test_tts.py && \
  echo '' && echo 'All suites passed.' \
"]
