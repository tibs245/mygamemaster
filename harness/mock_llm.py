#!/usr/bin/env python3
"""OpenAI-compatible mock LLM for the E2E harness — deterministic canned response.

No real keys, no outbound network: the Hermes gateway points its
model.base_url here (chat_completions). Used to PROVE runtime hook
invocation without depending on a real LLM.

The returned narration intentionally contains a ```python``` block to verify
the player-channel scrub (R4b) end-to-end once the hooks are active.

Usage: python3 mock_llm.py [port]   (default 8080)
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

NARRATION = (
    "Berthe lève les yeux de ses nasses quand tu pousses la porte. "
    "« Te revoilà », dit-elle, en te tendant une anguille fumée.\n\n"
    "```python\nprint('trace interne MJ — ne doit jamais fuiter au joueur')\n```\n\n"
    "Le feu crépite doucement. Que fais-tu ?"
)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        # Hermes resolves/validates the model via the provider's /v1/models before the chat.
        sys.stderr.write("[mock] GET %s\n" % self.path)
        sys.stderr.flush()
        self._send({"object": "list", "data": [
            {"id": "mock", "object": "model", "owned_by": "harness"}]})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            raw = self.rfile.read(length)
        except Exception:
            raw = b""
        sys.stderr.write("[mock] POST %s len=%d stream=%s\n" % (
            self.path, length, b'"stream": true' in raw or b'"stream":true' in raw))
        sys.stderr.flush()
        body = {
            "id": "mock-cmpl-1",
            "object": "chat.completion",
            "model": "mock",
            "choices": [{
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": NARRATION},
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        data = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
