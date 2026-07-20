"""The routing engine: classify -> route -> (optional) verify & escalate.

This is the deployable counterpart of the experimental harness. In deployment
we do not have ground-truth unit tests, so the router is primarily *predictive*
(a complexity score decides the tier). An optional, heuristic *reactive* check
can escalate obviously-weak answers; it is off by default to avoid needless
escalations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .config import Config
from . import ollama_client as oc


@dataclass
class RouteResult:
    model: str            # the model that produced the final answer
    tier: str             # "small" | "large"
    text: str
    complexity: float
    escalated: bool
    in_tokens: int
    out_tokens: int
    latency: float


class Router:
    def __init__(self, config: Optional[Config] = None):
        self.cfg = config or Config()

    # ------------------------------------------------------------------ score
    def complexity(self, messages: List[Dict]) -> float:
        """Predictive difficulty in [0, 1] from the latest user message."""
        text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                text = m.get("content", "") or ""
                break
        if not text:
            text = " ".join(m.get("content", "") for m in messages)
        d = text.lower()
        score = min(len(text) / 600.0, 0.4)
        score += 0.35 * sum(k in d for k in self.cfg.hard_keywords)
        score += 0.12 * sum(k in d for k in self.cfg.med_keywords)
        return min(score, 1.0)

    # ------------------------------------------------------------------ choose
    def choose_tier(self, complexity: float):
        if complexity >= self.cfg.tau:
            return "large", self.cfg.large_model
        return "small", self.cfg.small_model

    # -------------------------------------------------------------- reactive
    def should_escalate(self, answer: str, messages: List[Dict]) -> bool:
        """Very conservative heuristic used only when cfg.reactive is True."""
        a = (answer or "").strip()
        if len(a) < self.cfg.min_answer_chars:
            return True
        low = a.lower()
        refusals = ("i cannot", "i can't help", "i am unable", "as an ai")
        return any(r in low for r in refusals)

    # ------------------------------------------------------------------ route
    def _try_chat(self, model, messages, temp):
        try:
            return oc.chat(self.cfg.ollama_url, model, messages, temp,
                           self.cfg.request_timeout), None
        except oc.OllamaError as e:
            return None, str(e)

    def route(self, messages: List[Dict],
              temperature: Optional[float] = None) -> RouteResult:
        temp = self.cfg.temperature if temperature is None else temperature
        x = self.complexity(messages)
        tier, model = self.choose_tier(x)

        if tier == "large":
            res, err = self._try_chat(model, messages, temp)
            if res is None:
                # resilience: large tier unavailable -> fall back to small
                fb, fberr = self._try_chat(self.cfg.small_model, messages, temp)
                if fb is None:
                    raise oc.OllamaError(
                        f"both tiers failed (large: {err}; small: {fberr})")
                return RouteResult(
                    model=self.cfg.small_model, tier="small (fallback)",
                    text=fb.text, complexity=x, escalated=False,
                    in_tokens=fb.in_tokens, out_tokens=fb.out_tokens,
                    latency=fb.latency)
            return RouteResult(
                model=model, tier="large", text=res.text, complexity=x,
                escalated=False, in_tokens=res.in_tokens,
                out_tokens=res.out_tokens, latency=res.latency)

        # small tier
        res, err = self._try_chat(model, messages, temp)
        if res is None:
            raise oc.OllamaError(f"small tier failed: {err}")

        if self.cfg.reactive and self.should_escalate(res.text, messages):
            lg, lgerr = self._try_chat(self.cfg.large_model, messages, temp)
            if lg is not None:
                return RouteResult(
                    model=self.cfg.large_model, tier="large", text=lg.text,
                    complexity=x, escalated=True, in_tokens=lg.in_tokens,
                    out_tokens=lg.out_tokens, latency=lg.latency)
            # escalation target unavailable -> keep the small answer
            return RouteResult(
                model=model, tier="small (escalation unavailable)",
                text=res.text, complexity=x, escalated=False,
                in_tokens=res.in_tokens, out_tokens=res.out_tokens,
                latency=res.latency)

        return RouteResult(
            model=model, tier="small", text=res.text, complexity=x,
            escalated=False, in_tokens=res.in_tokens,
            out_tokens=res.out_tokens, latency=res.latency)

    # --------------------------------------------------------------- passthru
    def passthrough(self, model: str, messages: List[Dict],
                    temperature: Optional[float] = None) -> RouteResult:
        """Send directly to a named model (no routing)."""
        temp = self.cfg.temperature if temperature is None else temperature
        res = oc.chat(self.cfg.ollama_url, model, messages, temp,
                      self.cfg.request_timeout)
        return RouteResult(
            model=model, tier="explicit", text=res.text,
            complexity=self.complexity(messages), escalated=False,
            in_tokens=res.in_tokens, out_tokens=res.out_tokens,
            latency=res.latency,
        )

    def ask(self, prompt: str) -> str:
        """Convenience: route a single user prompt and return the answer text."""
        return self.route([{"role": "user", "content": prompt}]).text
