"""OpenAI-compatible HTTP gateway (standard library ``http.server``).

Endpoints:
    GET  /health                     -> {"status": "ok"}
    GET  /v1/models                  -> OpenAI-style model list
    POST /v1/chat/completions        -> routes to an Ollama model and returns an
                                        OpenAI-style completion (stream or not)
    GET  /stats                      -> aggregate routing stats (for dashboards)
    GET  /decisions?n=50             -> recent routing decisions

The ``api_key`` sent by clients is ignored (there is no OpenAI account
involved -- "OpenAI-compatible" refers only to the request/response format).
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import Config
from .engine import Router
from . import ollama_client as oc


# ------------------------------------------------------------------ stats state
_LOCK = threading.Lock()
_RECENT = deque(maxlen=300)
_STATS = {
    "total": 0, "small": 0, "large": 0, "escalated": 0, "fallback": 0,
    "errors": 0, "in_tokens": 0, "out_tokens": 0,
    "est_saved": 0.0, "est_spent": 0.0, "started": time.time(),
}


def _record(cfg: Config, result):
    is_large = result.tier == "large"
    entry = {
        "ts": time.time(),
        "complexity": round(result.complexity, 3),
        "tier": result.tier,
        "model": result.model,
        "escalated": result.escalated,
        "in_tokens": result.in_tokens,
        "out_tokens": result.out_tokens,
        "latency": round(result.latency, 2),
    }
    with _LOCK:
        _STATS["total"] += 1
        _STATS["in_tokens"] += result.in_tokens
        _STATS["out_tokens"] += result.out_tokens
        if is_large:
            _STATS["large"] += 1
            _STATS["est_spent"] += cfg.est_large_cost
        else:
            _STATS["small"] += 1
            _STATS["est_saved"] += cfg.est_large_cost  # avoided the large tier
        if result.escalated:
            _STATS["escalated"] += 1
        if "fallback" in result.tier:
            _STATS["fallback"] += 1
        _RECENT.appendleft(entry)
    try:
        with open(cfg.decisions_path(), "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _snapshot():
    with _LOCK:
        s = dict(_STATS)
        recent = list(_RECENT)
    total = s["total"] or 1
    s["pct_local"] = round(100.0 * s["small"] / total, 1)
    s["uptime_s"] = round(time.time() - s["started"], 1)
    return s, recent


def _chunk_text(text: str, size: int = 24):
    for i in range(0, len(text), size):
        yield text[i:i + size]


class Handler(BaseHTTPRequestHandler):
    router: Router = None          # injected in serve()
    config: Config = None

    def log_message(self, fmt, *args):
        return

    # ----------------------------------------------------------------- helpers
    def _cors(self):
        if self.config.cors:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _json(self, code: int, obj: dict, extra_headers: dict = None):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw or b"{}")

    # ------------------------------------------------------------------ OPTIONS
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    # --------------------------------------------------------------------- GET
    def do_GET(self):
        path = self.path.split("?", 1)[0].rstrip("/")
        if path == "/health":
            return self._json(200, {"status": "ok", "service": "llmroute"})
        if path == "/stats":
            s, _ = _snapshot()
            s["small_model"] = self.config.small_model
            s["large_model"] = self.config.large_model
            s["tau"] = self.config.tau
            s["reactive"] = self.config.reactive
            return self._json(200, s)
        if path == "/decisions":
            n = 50
            if "?" in self.path:
                from urllib.parse import parse_qs, urlparse
                q = parse_qs(urlparse(self.path).query)
                n = int(q.get("n", [50])[0])
            _, recent = _snapshot()
            return self._json(200, {"decisions": recent[:n]})
        if path == "/v1/models":
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
                result = self.router.passthrough(model_field, messages,
                                                 temperature)
        except oc.OllamaError as e:
            with _LOCK:
                _STATS["errors"] += 1
            return self._json(502, {"error": {
                "message": str(e), "type": "ollama_error"}})
        except Exception as e:  # noqa: BLE001
            with _LOCK:
                _STATS["errors"] += 1
            return self._json(500, {"error": {"message": str(e)}})

        _record(self.config, result)
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
        self._cors()
        for k, v in route_headers.items():
            self.send_header(k, v)
        self.end_headers()

        def send(delta: dict, finish=None):
            obj = {
                "id": cid, "object": "chat.completion.chunk",
                "created": created, "model": result.model,
                "choices": [{"index": 0, "delta": delta,
                             "finish_reason": finish}],
                "x_llmroute": {"tier": result.tier,
                               "escalated": result.escalated},
            }
            self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
            self.wfile.flush()

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
    print(f"stats: http://{config.host}:{config.port}/stats   "
          f"log: {config.decisions_path()}", flush=True)
    print("Point any OpenAI-compatible client's base URL here. "
          "api_key is ignored.", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down.", flush=True)
        httpd.shutdown()
