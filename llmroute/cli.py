"""Command-line interface for llmroute.

    llmroute serve                 # start the OpenAI-compatible gateway
    llmroute route "question"      # one-shot: route a prompt, print the answer
    llmroute models                # list locally available Ollama models
    llmroute config                # print the effective configuration
    llmroute version
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import load_config
from .engine import Router
from . import ollama_client as oc


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(prog="llmroute",
                                 description="Free-first cost-aware router for "
                                             "Ollama (OpenAI-compatible).")
    ap.add_argument("--config", help="path to a JSON config file")
    sub = ap.add_subparsers(dest="cmd")

    p_serve = sub.add_parser("serve", help="start the gateway")
    p_serve.add_argument("--host")
    p_serve.add_argument("--port", type=int)
    p_serve.add_argument("--small", help="small/local free model tag")
    p_serve.add_argument("--large", help="large model tag")
    p_serve.add_argument("--tau", type=float, help="routing threshold [0,1]")
    p_serve.add_argument("--reactive", action="store_true",
                         help="enable heuristic verify-and-escalate")

    p_route = sub.add_parser("route", help="route one prompt and print answer")
    p_route.add_argument("prompt")
    p_route.add_argument("--verbose", "-v", action="store_true")

    sub.add_parser("models", help="list local Ollama models")
    sub.add_parser("config", help="print effective configuration")
    sub.add_parser("version", help="print version")

    args = ap.parse_args(argv)
    cfg = load_config(args.config)

    if args.cmd == "serve":
        if args.host:  cfg.host = args.host
        if args.port:  cfg.port = args.port
        if args.small: cfg.small_model = args.small
        if args.large: cfg.large_model = args.large
        if args.tau is not None: cfg.tau = args.tau
        if args.reactive: cfg.reactive = True
        from .server import serve
        serve(cfg)
        return 0

    if args.cmd == "route":
        r = Router(cfg)
        res = r.route([{"role": "user", "content": args.prompt}])
        if args.verbose:
            print(f"[complexity={res.complexity:.2f} tier={res.tier} "
                  f"model={res.model} escalated={res.escalated}]\n",
                  file=sys.stderr)
        print(res.text)
        return 0

    if args.cmd == "models":
        for m in oc.list_models(cfg.ollama_url):
            print(m)
        return 0

    if args.cmd == "config":
        print(cfg.to_json())
        return 0

    if args.cmd == "version":
        print(f"llmroute {__version__}")
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
