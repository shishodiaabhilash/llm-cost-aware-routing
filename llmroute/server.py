"""OpenAI-compatible HTTP gateway (standard library ``http.server``).

Endpoints:
    GET  /health                     -> {"status": "ok"}
    GET  /v1/models                  -> OpenAI-style model list
    POST /v1/chat/completions        -> routes to an Ollama model and returns an
                                        OpenAI-style completion (stream or not)

The ``api_key`` sent by clients is ignored (there is no OpenAI account
involved -- "OpenAI-compatible" refers only to the request/response format).
"""

from __future__ import annotations

import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import Config
from .engine import Router
from . import ollama_client as oc


def _chunk_text(text: str, size: int = 24):
    for i in range(0, len(text), size):
        yield text[i:i + size]


class Handler(BaseHTTPRequestHandler):
    router: Router = None          # injected in serve()
    config: Config = None

    # silence default noisy logging; we do our own
    def log_message(self, fmt, *args):
        return

    # ----------------------------------------------------------------- helpers
    def _json(self, code: int, obj: dict, extra_headers: dict = None):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw or b"{}")

    # --------------------------------------------------------------------- GET
    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            return self._json(200, {"status": "ok", "service": "llmroute"})
        if self.path.startswith("/v1/models"):
            models = ["auto", self.config.small_model, self.config.large_model]
            data = [{"id": m, "object": "model", "owned_by": "llmroute"}
                    for m in dict.fromkeys(models)]
            return self._json(200, {"object": "list", "data": data})
        return self._json(404, {"error": {"message": "not found"}})

    # -------------------------------------------------------------------- POST
    def do_POST(self):
        if not self.path.startswith("/v1/chat/completions"):
            return self._json(404, {"error": {"message": "not found"}})
        try:
            req = self._read_body()
        except Exception as e:  # noqa: BLE001
            return self._json(400, {"error": {"message": f"bad JSON: {e}"}})

        messages = req.get("messages", [])
        model_field = req.get("model", self.config.trigger_model)
        temperature = req.get("temperature")
        stream = bool(req.get("stream", False))

        try:
            if model_field == self.config.trigger_model:
                result = self.router.route(messages, temperature)
            else:
                # explicit model -> pass straight through to Ollama
                result = self.router.passthrough(model_field, messages,
                                                 temperature)
        except oc.OllamaError as e:
            return self._json(502, {"error": {
                "message": str(e), "type": "ollama_error"}})
        except Exception as e:  # noqa: BLE001
            return self._json(500, {"error": {"message": str(e)}})

        if self.config.log_decisions:
            print(f"[llmroute] x={result.complexity:.2f} tier={result.tier} "
                  f"model={result.model} escalated={result.escalated} "
                  f"out_tok={result.out_tokens} {result.latency:.1f}s",
                  flush=True)

        route_headers = {
            "X-LLMRoute-Model": result.model,
            "X-LLMRoute-Tier": result.tier,
            "X-LLMRoute-Escalated": str(result.escalated).lower(),
        }
        cid = "chatcmpl-" + uuid.uuid4().hex[:24]
        created = int(time.time())

        if stream:
            return self._stream(cid, created, result, route_headers)

        return self._json(200, {
            "id": cid, "object": "chat.completion", "created": created,
            "model": result.model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": result.text},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": result.in_tokens,
                "completion_tokens": result.out_tokens,
                "total_tokens": result.in_tokens + result.out_tokens,
            },
            "x_llmroute": {
                "tier": result.tier, "escalated": result.escalated,
                "complexity": round(result.complexity, 3),
            },
        }, route_headers)

    # ------------------------------------------------------------------ stream
    def _stream(self, cid, created, result, route_headers):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        for k, v in route_headers.items():
            self.send_header(k, v)
        self.end_headers()

        def send(delta: dict, finish=None):
            obj = {
                "id": cid, "object": "chat.completion.chunk",
                "created": created, "model": result.model,
                "choices": [{"index": 0, "delta": delta,
                             "finish_reason": finish}],
            }
            self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
            self.wfile.flush()

        # role first, then the (already-decided) final answer in pieces
        send({"role": "assistant"})
        for piece in _chunk_text(result.text):
            send({"content": piece})
        send({}, finish="stop")
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def serve(config: Config):
    Handler.config = config
    Handler.router = Router(config)
    httpd = ThreadingHTTPServer((config.host, config.port), Handler)
    print(f"llmroute gateway on http://{config.host}:{config.port}/v1  "
          f"(small={config.small_model}, large={config.large_model}, "
          f"tau={config.tau}, reactive={config.reactive})", flush=True)
    print("Point any OpenAI-compatible client's base URL here. "
          "api_key is ignored.", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down.", flush=True)
        httpd.shutdown()
