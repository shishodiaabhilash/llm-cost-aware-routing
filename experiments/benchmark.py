#!/usr/bin/env python3
"""
Model benchmark for the Smart LLM Router study.

Evaluates each model INDIVIDUALLY on the full coding-task suite and reports
pass@1 (fraction of tasks whose generated code passes all unit tests), broken
down by difficulty, plus mean generation latency and token usage.

Models are grouped into two honestly-labelled classes:
  * "small local free"  -> models running locally via Ollama at zero marginal
                           cost (always available offline).
  * "large cloud"       -> large models served from Ollama's cloud; these are
                           comparable in capability to paid-tier hosted models,
                           but here we test only cloud models we can access
                           for free. Testing true paid APIs is left as future
                           work (see the paper).

USAGE
-----
    python3 benchmark.py                          # default model set, all tasks
    python3 benchmark.py --limit 8                # quick smoke test
    python3 benchmark.py --models llama3.2:latest,gpt-oss:120b-cloud

Security note: like the router harness, this executes model-generated code in
an isolated subprocess with a timeout. Run only where you are comfortable.
"""

import argparse
import json
import time

from tasks import TASKS
from router_experiment import (ollama_generate, extract_code, run_tests,
                               code_prompt)

# Default evaluation set. Edit freely.
# (qwen3:latest is excluded by default: it is a slow reasoning model ~50s/task.)
DEFAULT_LOCAL = ["llama3.2:latest", "gemma3:latest", "phi4-mini:latest",
                 "mistral:latest"]
DEFAULT_CLOUD = ["gpt-oss:120b-cloud", "qwen3-coder:480b-cloud"]

DIFFS = ["easy", "medium", "hard", "expert", "brutal"]


def evaluate(model, tasks):
    rows = []
    for t in tasks:
        try:
            text, itok, otok, dt = ollama_generate(model, code_prompt(t))
            passed = run_tests(extract_code(text), t["tests"])
        except Exception:                       # noqa: BLE001 (model/network err)
            itok = otok = 0
            dt = 0.0
            passed = False
        rows.append(dict(id=t["id"], difficulty=t["difficulty"],
                         passed=passed, latency=dt,
                         in_tok=itok, out_tok=otok))
    return rows


def summarize(rows):
    n = len(rows)
    overall = sum(r["passed"] for r in rows) / n if n else 0.0
    by = {}
    for d in DIFFS:
        sub = [r for r in rows if r["difficulty"] == d]
        by[d] = (sum(r["passed"] for r in sub) / len(sub)) if sub else None
    lat = sum(r["latency"] for r in rows) / n if n else 0.0
    return overall, by, lat


def main():
    ap = argparse.ArgumentParser(description="LLM coding benchmark")
    ap.add_argument("--models", default="",
                    help="comma-separated model tags (overrides defaults)")
    ap.add_argument("--limit", type=int, default=0, help="first N tasks (0=all)")
    ap.add_argument("--difficulty", default="",
                    help="filter: easy|medium|hard|expert|brutal")
    ap.add_argument("--out", default="benchmark.json")
    args = ap.parse_args()

    tasks = TASKS
    if args.difficulty:
        tasks = [t for t in tasks if t["difficulty"] == args.difficulty]
    if args.limit:
        tasks = tasks[:args.limit]

    if args.models:
        models = [(m.strip(),
                   "large cloud" if "cloud" in m else "small local free")
                  for m in args.models.split(",") if m.strip()]
    else:
        models = ([(m, "small local free") for m in DEFAULT_LOCAL] +
                  [(m, "large cloud") for m in DEFAULT_CLOUD])

    print(f"Tasks: {len(tasks)}  (easy/medium/hard/expert)")
    print(f"Models: {len(models)}\n")
    header = (f"{'model':<26}{'class':<18}{'pass@1':<8}"
              f"{'easy':<6}{'med':<6}{'hard':<6}{'exp':<6}{'brut':<6}{'lat_s':<7}")
    print(header)
    print("-" * len(header))

    results = {}
    for model, cls in models:
        t0 = time.time()
        rows = evaluate(model, tasks)
        overall, by, lat = summarize(rows)
        results[model] = dict(cls=cls, overall=overall, by=by,
                              avg_latency=lat, rows=rows)

        def fmt(v):
            return f"{v*100:>3.0f}%" if v is not None else "  - "
        print(f"{model:<26}{cls:<18}{overall*100:>4.0f}%  "
              f"{fmt(by['easy']):<6}{fmt(by['medium']):<6}"
              f"{fmt(by['hard']):<6}{fmt(by['expert']):<6}"
              f"{fmt(by['brutal']):<6}{lat:>5.1f}")

    print("-" * len(header))
    # class averages
    for cls in ["small local free", "large cloud"]:
        vals = [r["overall"] for r in results.values() if r["cls"] == cls]
        if vals:
            print(f"avg {cls:<22}: pass@1 = {sum(vals)/len(vals)*100:.0f}%")

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved {args.out}")


if __name__ == "__main__":
    main()
