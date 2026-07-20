"""Configuration for the llmroute gateway.

Defaults live here so the tool works out of the box. Users can override any
field with a JSON config file (``--config path.json`` or ``~/.llmroute.json``).
No third-party YAML/TOML dependency is required.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import List


@dataclass
class Config:
    # --- model tiers ---------------------------------------------------------
    # The small tier runs locally at zero marginal cost; the large tier is a
    # bigger (local or cloud) model used only when a request looks hard.
    small_model: str = "llama3.2:latest"
    large_model: str = "gpt-oss:120b-cloud"

    # Requests whose ``model`` field equals this trigger routing. Any other
    # model name is passed straight through to Ollama unchanged.
    trigger_model: str = "auto"

    # --- routing policy ------------------------------------------------------
    tau: float = 0.45              # complexity threshold: >= tau -> large tier
    reactive: bool = False         # enable heuristic verify-and-escalate
    min_answer_chars: int = 24     # used only if reactive is on

    # --- ollama connection ---------------------------------------------------
    ollama_url: str = "http://localhost:11434"
    temperature: float = 0.2
    request_timeout: int = 600

    # --- server --------------------------------------------------------------
    host: str = "127.0.0.1"
    port: int = 11435

    # --- observability -------------------------------------------------------
    log_decisions: bool = True     # print one line per routing decision
    decisions_log: str = ""        # JSONL path; "" -> ~/.llmroute/decisions.jsonl
    est_large_cost: float = 0.03   # illustrative $/request for the large tier
    cors: bool = True              # allow browser/webview clients to read stats

    # --- complexity heuristic keywords --------------------------------------
    hard_keywords: List[str] = field(default_factory=lambda: [
        "dynamic programming", "optimize", "efficient", "o(n", "concurren",
        "thread", "graph", "subsequence", "interval", "edit distance",
        "levenshtein", "longest", "architecture", "design", "scal", "refactor",
        "security", "race condition", "deadlock", "distributed", "algorithm",
    ])
    med_keywords: List[str] = field(default_factory=lambda: [
        "prime", "fibonacci", "parse", "valid", "stack", "queue", "sort",
        "search", "matrix", "balanced", "recursion", "regex", "test",
    ])

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    def decisions_path(self) -> str:
        """Resolve the JSONL decisions log path (creating the dir if needed)."""
        p = self.decisions_log or os.path.expanduser("~/.llmroute/decisions.jsonl")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p


def load_config(path: str | None = None) -> Config:
    """Load a Config, overlaying an optional JSON file on top of the defaults.

    Lookup order when ``path`` is None:
      1. $LLMROUTE_CONFIG
      2. ~/.llmroute.json
    Missing files are ignored (defaults are used).
    """
    cfg = Config()
    candidates = []
    if path:
        candidates.append(path)
    else:
        env = os.environ.get("LLMROUTE_CONFIG")
        if env:
            candidates.append(env)
        candidates.append(os.path.expanduser("~/.llmroute.json"))

    for p in candidates:
        if p and os.path.isfile(p):
            with open(p) as f:
                data = json.load(f)
            for k, v in data.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
            break

    # environment overrides for the most common knobs
    cfg.ollama_url = os.environ.get("OLLAMA_URL", cfg.ollama_url)
    return cfg
