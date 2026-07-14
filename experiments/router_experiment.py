#!/usr/bin/env python3
"""
Smart LLM Router -- local experiment harness (Ollama, stdlib only).

Implements the paper's classify -> route -> verify pipeline on real coding
tasks and compares four strategies:

    always_weak     -> always use the free/local model
    always_strong   -> always use the premium ("paid") model  [baseline]
    random          -> pick a tier at random
    router (ours)   -> predictive routing + reactive escalation on verify fail

Metrics reported (per strategy):
    pass@1          -> fraction of tasks whose generated code passes all tests
    paid_fraction   -> fraction of tasks that invoked the strong/paid tier
    cost_$          -> assigned dollar cost (weak tier = $0; strong tier priced)
    avg_latency_s   -> mean wall-clock generation time
    savings_vs_paid -> 1 - cost/always_strong_cost

USAGE
-----
    python3 router_experiment.py                       # defaults, all tasks
    python3 router_experiment.py --limit 4             # quick smoke test
    python3 router_experiment.py --weak llama3.2:latest \
                                 --strong qwen3-coder:480b-cloud
    python3 router_experiment.py --tau 0.35            # routing threshold

SECURITY NOTE
-------------
This harness EXECUTES model-generated Python code to grade it (standard for
code benchmarks like HumanEval/MBPP). Each candidate runs in an isolated
subprocess with a timeout, but it is still arbitrary code from a model. Run
only on a machine you are comfortable with, ideally inside a container/VM.
Do not point this at untrusted prompts.
"""

import argparse
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

from tasks import TASKS

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# --- assigned pricing (USD). Weak/local tier is free; strong tier is priced ---
# These are configurable assumptions used only to convert token usage into a
# comparable dollar figure. Adjust to match whatever "paid" model you emulate.
STRONG_PRICE_IN_PER_1M = 1.00     # $ per 1M input (prompt) tokens
STRONG_PRICE_OUT_PER_1M = 3.00    # $ per 1M output (generated) tokens


# ---------------------------------------------------------------- ollama client
def ollama_generate(model, prompt, temperature=0.2, timeout=600):
    """Call Ollama /api/generate. Returns (text, in_tokens, out_tokens, seconds)."""
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate", data=payload,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[:200]
        raise RuntimeError(f"HTTP {e.code} from Ollama for '{model}': {detail}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach Ollama at {OLLAMA_URL}: {e.reason}")
    if "error" in resp:
        raise RuntimeError(f"Ollama error for '{model}': {resp['error']}")
    dt = time.time() - t0
    return (resp.get("response", ""),
            resp.get("prompt_eval_count", 0),
            resp.get("eval_count", 0),
            dt)


def preflight(model):
    """Verify a model responds; return None on success or an error string."""
    try:
        ollama_generate(model, "print ok", timeout=120)
        return None
    except Exception as e:  # noqa: BLE001
        return str(e)


# ---------------------------------------------------------------- helpers
def extract_code(text):
    """Pull the first fenced code block; fall back to the whole response."""
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()


def run_tests(code, tests, timeout=10):
    """Execute candidate code + tests in an isolated subprocess. True == pass."""
    script = code + "\n\n" + tests + "\nprint('__ALL_TESTS_PASSED__')\n"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        out = subprocess.run(
            [sys.executable, "-I", path],
            capture_output=True, text=True, timeout=timeout,
        )
        return "__ALL_TESTS_PASSED__" in out.stdout
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def complexity_score(prompt):
    """Predictive difficulty in [0,1] from the prompt (heuristic classifier)."""
    d = prompt.lower()
    score = min(len(prompt) / 600.0, 0.4)
    hard_kw = ["dynamic programming", "optimize", "efficient", "o(n",
               "concurren", "thread", "graph", "subsequence", "interval",
               "edit distance", "segment", "levenshtein", "longest"]
    med_kw = ["algorithm", "prime", "fibonacci", "parse", "valid", "stack",
              "queue", "sort", "search", "two", "matrix", "balanced"]
    score += 0.35 * sum(k in d for k in hard_kw)
    score += 0.12 * sum(k in d for k in med_kw)
    return min(score, 1.0)


def code_prompt(task):
    return (
        f"Write a Python function `{task['entry']}` that solves the problem.\n"
        f"Return ONLY the function definition inside a ```python code block.\n\n"
        f"Problem: {task['prompt']}"
    )


def price_strong(in_tok, out_tok):
    return (in_tok / 1e6) * STRONG_PRICE_IN_PER_1M + \
           (out_tok / 1e6) * STRONG_PRICE_OUT_PER_1M


# ---------------------------------------------------------------- experiment
def generate_and_grade(model, task):
    """Generate a solution with `model` and grade it. Returns a result dict."""
    text, itok, otok, dt = ollama_generate(model, code_prompt(task))
    code = extract_code(text)
    passed = run_tests(code, task["tests"])
    return dict(passed=passed, in_tok=itok, out_tok=otok, latency=dt, code=code)


def main():
    ap = argparse.ArgumentParser(description="Smart LLM Router experiment")
    ap.add_argument("--weak", default="llama3.2:latest",
                    help="free/local model (Ollama tag)")
    ap.add_argument("--strong", default="qwen3-coder:480b-cloud",
                    help="premium/'paid' model (Ollama tag)")
    ap.add_argument("--tau", type=float, default=0.35,
                    help="routing threshold for predictive escalation")
    ap.add_argument("--limit", type=int, default=0,
                    help="run only the first N tasks (0 = all)")
    ap.add_argument("--difficulty", default="",
                    help="filter tasks by difficulty: easy|medium|hard")
    ap.add_argument("--seed", type=int, default=0, help="random-baseline seed")
    ap.add_argument("--out", default="results.json", help="results output file")
    args = ap.parse_args()

    tasks = TASKS
    if args.difficulty:
        tasks = [t for t in tasks if t["difficulty"] == args.difficulty]
    if args.limit:
        tasks = tasks[:args.limit]
    rng = random.Random(args.seed)

    print(f"Weak (free) tier : {args.weak}")
    print(f"Strong (paid)tier: {args.strong}")
    print(f"Routing threshold: tau={args.tau}")
    print(f"Tasks            : {len(tasks)}")
    print(f"Strong pricing   : ${STRONG_PRICE_IN_PER_1M}/1M in, "
          f"${STRONG_PRICE_OUT_PER_1M}/1M out\n")

    # preflight: fail early with clear guidance
    for label, model in [("weak", args.weak), ("strong", args.strong)]:
        err = preflight(model)
        if err:
            print(f"[!] The {label} model '{model}' is not usable:\n    {err}\n")
            if "Unauthorized" in err or "cloud" in model:
                print("    This looks like an Ollama *cloud* model. Either:\n"
                      "      1) run `ollama signin` to authenticate, or\n"
                      "      2) use a local model instead, e.g.\n"
                      "         --strong qwen3:latest   (or mistral:latest)")
            else:
                print("    Make sure the model is pulled: `ollama pull " + model + "`")
            sys.exit(1)

    print(f"{'task':<16}{'diff':<8}{'x(q)':<7}{'weak':<7}{'strong':<8}"
          f"{'route':<8}{'paid?':<7}")
    print("-" * 67)

    records = []
    for t in tasks:
        # Generate once per tier and reuse across all strategies (saves calls).
        w = generate_and_grade(args.weak, t)
        s = generate_and_grade(args.strong, t)
        x = complexity_score(t["prompt"])

        # Router: predictive tier, then reactive escalation if weak fails verify.
        predicted_strong = x >= args.tau
        if predicted_strong:
            r_tier, r_pass = "strong", s["passed"]
            r_cost = price_strong(s["in_tok"], s["out_tok"])
            r_lat = s["latency"]
            r_paid = True
        else:
            if w["passed"]:                       # verified OK -> stay free
                r_tier, r_pass, r_cost = "weak", True, 0.0
                r_lat, r_paid = w["latency"], False
            else:                                 # escalate on verify fail
                r_tier, r_pass = "strong(esc)", s["passed"]
                r_cost = price_strong(s["in_tok"], s["out_tok"])
                r_lat = w["latency"] + s["latency"]
                r_paid = True

        rand_strong = rng.random() < 0.5

        records.append(dict(
            id=t["id"], difficulty=t["difficulty"], x=x,
            weak=w, strong=s,
            router=dict(tier=r_tier, passed=r_pass, cost=r_cost,
                        latency=r_lat, paid=r_paid),
            random_strong=rand_strong,
        ))
        print(f"{t['id']:<16}{t['difficulty']:<8}{x:<7.2f}"
              f"{('PASS' if w['passed'] else 'fail'):<7}"
              f"{('PASS' if s['passed'] else 'fail'):<8}"
              f"{r_tier:<8}{('yes' if r_paid else 'no'):<7}")

    # ---------------- aggregate ----------------
    n = len(records)

    def agg(strategy):
        pw = po = cost = lat = paid = 0
        for r in records:
            if strategy == "always_weak":
                passed, c, l, is_paid = r["weak"]["passed"], 0.0, r["weak"]["latency"], False
            elif strategy == "always_strong":
                passed = r["strong"]["passed"]
                c = price_strong(r["strong"]["in_tok"], r["strong"]["out_tok"])
                l, is_paid = r["strong"]["latency"], True
            elif strategy == "random":
                if r["random_strong"]:
                    passed = r["strong"]["passed"]
                    c = price_strong(r["strong"]["in_tok"], r["strong"]["out_tok"])
                    l, is_paid = r["strong"]["latency"], True
                else:
                    passed, c, l, is_paid = r["weak"]["passed"], 0.0, r["weak"]["latency"], False
            else:  # router
                passed = r["router"]["passed"]; c = r["router"]["cost"]
                l = r["router"]["latency"]; is_paid = r["router"]["paid"]
            po += 1 if passed else 0
            cost += c; lat += l; paid += 1 if is_paid else 0
        return dict(passk=po / n, paid_frac=paid / n, cost=cost, avg_lat=lat / n)

    strategies = ["always_weak", "always_strong", "random", "router"]
    results = {st: agg(st) for st in strategies}
    base = results["always_strong"]["cost"] or 1e-9

    print("\n" + "=" * 67)
    print(f"{'strategy':<16}{'pass@1':<9}{'paid_frac':<11}{'cost_$':<10}"
          f"{'avg_lat_s':<11}{'save_vs_paid':<12}")
    print("-" * 67)
    for st in strategies:
        r = results[st]
        save = 1 - r["cost"] / base
        print(f"{st:<16}{r['passk']*100:>5.0f}%   {r['paid_frac']*100:>7.0f}%   "
              f"{r['cost']:>7.4f}   {r['avg_lat']:>8.2f}   {save*100:>8.0f}%")
    print("=" * 67)
    print("Interpretation: the router aims for pass@1 close to always_strong")
    print("while spending far less (lower cost / paid_fraction).")

    with open(args.out, "w") as f:
        cfg = vars(args).copy()
        cfg["out"] = os.path.basename(cfg["out"])  # avoid leaking local paths
        json.dump({"config": cfg, "results": results,
                   "records": [{k: v for k, v in r.items()
                                if k not in ("weak", "strong")} for r in records]},
                  f, indent=2)
    print(f"\nSaved detailed results to {args.out}")


if __name__ == "__main__":
    main()
