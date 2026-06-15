#!/usr/bin/env bash
# Harness E2E — plays ONE one-shot CLI turn against a mock LLM, inside the hermes image,
# and checks whether the runtime hooks are INVOKED (collecte.csv / .banquier / commit).
# Hermetic: no real keys, no Discord. Goal: reveal/validate R1.
#
# Network: mock + hermes are TWO containers on the same podman network (both
# inside the podman-machine VM) → the macOS↔VM network layer is bypassed. The gateway
# reaches the mock by its DNS name "harness-mock".
set -euo pipefail

HARNESS="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HARNESS/.." && pwd)"
IMAGE="${IMAGE:-localhost/mygamemaster:latest}"
NET="harness-net"

WORK="$(mktemp -d)"
CAMP="$WORK/campagne"
HHOME="$WORK/hhome"
mkdir -p "$CAMP/sessions" "$CAMP/characters" "$HHOME"

cat > "$CAMP/world.json" <<'JSON'
{ "meta": { "nom": "Harness", "temps": { "regime": "Narratif" }, "verbosite": "DEBUG",
    "diagnostic": { "actif": true, "fichier": "collecte.csv", "regles": { "echantillon_frequence": 1 } } },
  "modules": {}, "global_state": {}, "universe": { "regions": [] } }
JSON
echo '[]' > "$CAMP/npcs.json"
cp "$HARNESS/config.local.yaml" "$HHOME/config.yaml"
cp "$REPO/ansible/templates/SOUL.md.j2" "$HHOME/SOUL.md"

cleanup() {
  podman rm -f harness-mock >/dev/null 2>&1 || true
  podman network rm "$NET" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

podman network create "$NET" >/dev/null 2>&1 || true

# Mock LLM in a container (python from the hermes image), on the shared network.
podman run -d --rm --name harness-mock --network "$NET" \
  -v "$HARNESS/mock_llm.py":/mock.py:ro,Z \
  --entrypoint /opt/hermes/venv/bin/python3 \
  "$IMAGE" /mock.py 8080 >/dev/null
sleep 1

echo "▶ One one-shot CLI turn (hooks accepted)…"
set +e
podman run --rm --network "$NET" \
  --entrypoint /opt/hermes/venv/bin/hermes \
  -e HOME=/hhome -e HERMES_HOME=/hhome \
  -e OPENROUTER_API_KEY=dummy -e PYTHONUNBUFFERED=1 \
  -e HERMES_ALLOW_ROOT_GATEWAY=1 \
  -e MGM_JUDGE_MOCK='{"ok":true,"violations":[]}' \
  -e MGM_FEATURE_TTS=0 \
  -v "$HHOME":/hhome:Z \
  -v "$CAMP":/data/campagne:Z \
  -v "$REPO/modules":/opt/modules:ro,Z \
  "$IMAGE" \
  -z "Rubis pousse la porte de la cabane de Berthe." --accept-hooks
RC=$?
echo "  (hermes exit: $RC)"
set -e

echo
if [ "$RC" -ne 0 ]; then
  echo "⚠️  The turn did NOT complete (exit $RC) → R1 verdict UNDETERMINED."
  echo "    An incomplete turn says nothing about hook invocation. First verify"
  echo "    that the gateway can reach the mock (logs: podman logs harness-mock)."
  echo "    See harness/README.md § Known blocker (provider auth offline)."
fi
echo "════════ R1 — were the hooks INVOKED? (valid only if exit=0) ════════"
if [ -f "$CAMP/collecte.csv" ]; then
  echo "  ✅ collecte.csv present — $(($(wc -l < "$CAMP/collecte.csv") - 1)) line(s) (transform_llm_output ran)"
else
  echo "  ❌ collecte.csv ABSENT — transform_llm_output NOT invoked"
fi
if [ -d "$CAMP/.banquier" ] && [ -n "$(ls -A "$CAMP/.banquier" 2>/dev/null)" ]; then
  echo "  ✅ .banquier/: $(ls "$CAMP/.banquier")"
else
  echo "  ❌ .banquier/ empty/absent"
fi
if [ -d "$CAMP/.git" ] && git -C "$CAMP" log --oneline 2>/dev/null | grep -q .; then
  echo "  ✅ auto-commit: $(git -C "$CAMP" log --oneline | head -1)"
else
  echo "  ❌ no auto-commit"
fi
