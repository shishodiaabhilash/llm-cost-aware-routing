# LLM Router Assistant (VS Code extension)

An **agentic** AI coding assistant for VS Code — a Claude Code / Copilot-style
chat that reads your files, proposes edits, and runs commands, all powered by
your local **llmroute** gateway (so a small local model handles easy work and a
large model only the hard parts).

Written in plain JavaScript — **no build step**.

## Prerequisites
1. The `llmroute` gateway running (from the repo root):
   ```sh
   python3 -m llmroute.cli serve --small llama3.2:latest --large gemma3:latest
   ```
2. VS Code 1.85+.

## Run it (development)
1. Open **this `vscode-extension/` folder** in VS Code.
2. Press **F5** ("Run LLM Router Assistant"). A new *Extension Development Host*
   window opens with the extension loaded.
3. Click the **compass icon** in the activity bar → the **Assistant** panel.
4. Ask something. Try:
   - "What does the file `llmroute/engine.py` do?" (it will `read_file`)
   - "Add a docstring to the `route` method." (it proposes an `edit_file`, you approve)
   - "Run the tests" (it proposes a `run_command`, you approve)

The status bar shows live routing (`% local · $ saved`), and each answer shows a
badge of which **tier/model** produced it.

## Tools the agent can use
| Tool | Approval |
|------|----------|
| `read_file` | auto (read-only) |
| `list_dir` | auto (read-only) |
| `edit_file` | **asks** before writing |
| `run_command` | **asks** before running |

Edits and commands always require your explicit confirmation.

## Settings
- `llmrouter.gatewayUrl` (default `http://localhost:11435`)
- `llmrouter.model` (default `auto` — let the router decide)
- `llmrouter.maxSteps` (default `6`)
- `llmrouter.autoApproveReadTools` (default `true`)

## Packaging (later)
When your network allows npm, package a `.vsix` with:
```sh
npx @vscode/vsce package
```
then install it via *Extensions → … → Install from VSIX*.

## Notes
- This is an MVP foundation. Roadmap: streaming answers, inline (ghost-text)
  autocomplete, diff previews for edits, `@file`/`@selection` mentions, and a
  routing dashboard view.
- Tool-following quality depends on the model; hard/agentic prompts route to the
  large tier, which follows the JSON tool protocol more reliably.
