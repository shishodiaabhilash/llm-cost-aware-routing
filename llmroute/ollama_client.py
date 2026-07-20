"""Minimal Ollama HTTP client (standard library only)."""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ChatResult:
    text: str
    in_tokens: int
    out_tokens: int
    latency: float
    model: str


class OllamaError(RuntimeError):
    pass


def _post(url: str, payload: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[:200]
        raise OllamaError(f"HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise OllamaError(f"cannot reach Ollama at {url}: {e.reason}")


def chat(base_url: str, model: str, messages: List[Dict],
         temperature: float = 0.2, timeout: int = 600) -> ChatResult:
    """Call Ollama /api/chat (non-streaming) and normalise the result."""
    t0 = time.time()
    resp = _post(
        f"{base_url}/api/chat",
        {"model": model, "messages": messages, "stream": False,
         "options": {"temperature": temperature}},
        timeout,
    )
    if "error" in resp:
        raise OllamaError(f"{model}: {resp['error']}")
    text = (resp.get("message") or {}).get("content", "")
    return ChatResult(
        text=text,
        in_tokens=resp.get("prompt_eval_count", 0),
        out_tokens=resp.get("eval_count", 0),
        latency=time.time() - t0,
        model=model,
    )


def list_models(base_url: str, timeout: int = 30) -> List[str]:
    """Return locally available model tags via /api/tags."""
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=timeout) as r:
            data = json.load(r)
        return [m["name"] for m in data.get("models", [])]
    except Exception:  # noqa: BLE001
        return []
