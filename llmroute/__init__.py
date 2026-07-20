"""
llmroute -- a free-first, cost-aware, OpenAI-compatible routing gateway for
Ollama models.

Public API:
    from llmroute import Router, Config
    r = Router()
    result = r.route([{"role": "user", "content": "explain this function"}])
    print(result.model, result.text)
"""

from .config import Config, load_config
from .engine import Router, RouteResult

__version__ = "0.1.0"
__all__ = ["Router", "RouteResult", "Config", "load_config", "__version__"]
