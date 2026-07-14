# Smart LLM Router — Cost-Aware Routing Between Small Local and Large Cloud Models

A free-first, cost-aware gateway concept for AI coding assistance: classify each
request, serve it with a **small, locally-running (free) model** by default, and
**escalate to a large cloud-based model** only when the task is predicted to be
hard or when a lightweight verifier judges the local answer inadequate.

This repository contains:

- **`paper/`** — an arXiv-style paper (LaTeX source + compiled PDF) formalizing
  the routing problem, the *classify → route → verify* architecture, and a cost
  model, plus an evaluation protocol.
- **`experiments/`** — a small, dependency-free experiment harness that runs the
  idea for real against local and cloud models via [Ollama](https://ollama.com),
  and a coding benchmark used to measure model capability.

> **Author:** Abhilash Shishodia

---

## Key idea

Most everyday coding requests are easy and do not need a frontier model. A router
that keeps easy work on a free local model and escalates only the hard cases can
retain quality while cutting cost. Escalation is driven by:

1. a **predictive** complexity signal (a classifier applied before generation), and
2. a **reactive** verifier (run the local answer's tests / checks; escalate on failure).

---

## Terminology (important, kept honest)

- **Small local free model** — runs locally via Ollama at zero marginal cost and
  is always available offline (e.g. `llama3.2`, `gemma3`, `phi4-mini`, `mistral`).
- **Large cloud-based model** — a large model served from Ollama's cloud,
  comparable in capability to paid-tier hosted models. In this study we evaluate
  only cloud models we can access for free (e.g. `gpt-oss:120b-cloud`,
  `qwen3-coder:480b-cloud`).
- **Paid models are not evaluated here.** Extending the study to metered paid APIs
  (e.g. commercial frontier models) is explicitly left as **future work**.

Any dollar figures in the harness are **configurable, illustrative assumptions**
used only to convert token usage into a comparable cost; they are not vendor prices.

---

## Repository layout

```
paper/
  smart_llm_router.tex     # LaTeX source (self-contained; TikZ diagram, no images)
  smart_llm_router.pdf     # compiled paper
experiments/
  tasks.py                 # coding-task suite with executable unit tests
  router_experiment.py     # classify -> route -> verify harness (4 strategies)
  benchmark.py             # per-model capability benchmark
  results_*.json           # saved router-experiment results
  benchmark_*.json         # saved benchmark results
```

---

## Requirements

- Python 3.9+ (standard library only — no pip installs)
- [Ollama](https://ollama.com) running locally (`ollama serve`)
- One or more local models pulled, e.g.:
  ```sh
  ollama pull llama3.2
  ollama pull gemma3
  ```
- (Optional) an Ollama account signed in (`ollama signin`) to use cloud models.

For the LaTeX paper, any TeX distribution works;
[Tectonic](https://tectonic-typesetting.github.io) compiles it with a single command:
```sh
cd paper && tectonic smart_llm_router.tex
```

---

## Running the experiments

Routing experiment (compares always-free, always-cloud, random, and the router):

```sh
cd experiments
# mixed workload, local weak vs cloud strong tier
python3 router_experiment.py --weak llama3.2:latest --strong qwen3-coder:480b-cloud
# only the hardest tasks
python3 router_experiment.py --difficulty brutal --strong qwen3-coder:480b-cloud
# tune routing aggressiveness (lower tau = more requests kept free)
python3 router_experiment.py --tau 0.35
```

Model capability benchmark (evaluates each model individually):

```sh
cd experiments
python3 benchmark.py
python3 benchmark.py --difficulty brutal
python3 benchmark.py --models "llama3.2:latest,gpt-oss:120b-cloud"
```

Both scripts print a summary table and save a JSON results file.

---

## Example measured results

Measured on the included 44-problem suite (Python, execution-based pass@1). Your
numbers will vary by hardware, models, and task mix.

**Model capability — pass@1 by difficulty tier**

| Model | Class | Overall | Easy | Hard | Brutal |
|-------|-------|:---:|:---:|:---:|:---:|
| llama3.2 (3B) | small local free | 73% | 100% | 100% | 42% |
| gemma3 | small local free | 93% | 100% | 88% | 83% |
| phi4-mini | small local free | 52% | 100% | 75% | 17% |
| gpt-oss:120b | large cloud | 100% | 100% | 100% | 100% |
| qwen3-coder:480b | large cloud | 98% | 100% | 100% | 92% |

Small local models are competitive on easy work but lag on the hardest tier
(avg ~47% vs ~96% for large cloud models) — the headroom a router exploits.

**Router vs baselines** (small local `llama3.2` + large cloud `gpt-oss:120b`, τ=0.45)

| Strategy | pass@1 | cloud fraction | cost | savings |
|----------|:---:|:---:|:---:|:---:|
| always free (local) | 80% | 0% | $0.0000 | — |
| always cloud (baseline) | 100% | 100% | $0.0491 | 0% |
| random | 84% | 41% | $0.0194 | 61% |
| **router (ours)** | **100%** | **52%** | **$0.0287** | **41%** |

The router **matched the large cloud model's 100% pass@1** while sending only
**52%** of requests to the large tier — the reactive verifier caught 6 cases the
small model silently failed and escalated exactly those. (Dollar figures use
configurable, illustrative pricing, not vendor prices.)

> **Scope & honesty:** we evaluate *small local free* models and *large
> cloud-based* models (comparable to paid-tier models). We do **not** test metered
> paid APIs here; that is future work. The experimental verifier executes each
> task's unit tests (an *oracle*), so escalation results are an upper bound for
> the reactive mechanism.

---

## Security note

The harness **executes model-generated Python code** to grade it (standard for code
benchmarks such as HumanEval / MBPP). Each candidate runs in an isolated subprocess
with a timeout, but it is still arbitrary generated code. Run only on a machine you
are comfortable with, ideally in a container or VM, and never point it at untrusted
prompts.

---

## Status

This is a concept/position paper with a working prototype and preliminary empirical
results on a local + free-cloud model setup. Contributions and independent
replication are welcome.

## License

MIT — see [LICENSE](LICENSE).
