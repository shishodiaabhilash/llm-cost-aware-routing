// LLM Router Assistant -- an agentic AI coding assistant for VS Code, powered by
// your local llmroute gateway. Pure JavaScript (no build step required).
//
// Features: agentic chat (tools), inline autocomplete (ghost text), and editor
// commands (Explain / Fix / Document / Tests).

const vscode = require("vscode");
const http = require("http");
const https = require("https");
const cp = require("child_process");
const path = require("path");

let SMALL_MODEL = null; // learned from the gateway's /stats
let LARGE_MODEL = null;

// ------------------------------------------------------------------ helpers
function cfg() {
  return vscode.workspace.getConfiguration("llmrouter");
}
function workspaceRoot() {
  const f = vscode.workspace.workspaceFolders;
  return f && f.length ? f[0].uri.fsPath : process.cwd();
}

// The agent loop needs a capable model, so default to the large tier.
function agentModel() {
  const m = cfg().get("agentModel", "");
  if (m === "auto") return "auto";
  if (m) return m;
  return LARGE_MODEL || "auto";
}
// Autocomplete needs low latency, so default to the small/local tier.
function completionModel() {
  const m = cfg().get("completionModel", "");
  if (m) return m;
  return SMALL_MODEL || "auto";
}

function safeResolve(rel) {
  const root = workspaceRoot();
  let r = String(rel || ".").trim();
  r = r.replace(/^([A-Za-z]:)?[\\/]+/, "");
  const abs = path.resolve(root, r);
  if (abs !== root && !abs.startsWith(root + path.sep)) {
    throw new Error("path escapes the workspace: " + rel);
  }
  return abs;
}

async function listWorkspaceTop() {
  try {
    const items = await vscode.workspace.fs.readDirectory(
      vscode.Uri.file(workspaceRoot())
    );
    return items
      .filter(([n]) => n !== ".git")
      .slice(0, 100)
      .map(([n, t]) => (t === vscode.FileType.Directory ? n + "/" : n))
      .join("\n");
  } catch (_) {
    return "(unavailable)";
  }
}

function gatewayChat(messages, model) {
  return new Promise((resolve, reject) => {
    const base = cfg().get("gatewayUrl", "http://localhost:11435");
    const url = new URL(base + "/v1/chat/completions");
    const payload = JSON.stringify({
      model: model || cfg().get("model", "auto"),
      messages,
      stream: false,
      temperature: 0.2,
    });
    const lib = url.protocol === "https:" ? https : http;
    const req = lib.request(
      url,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(payload),
          Authorization: "Bearer unused",
        },
        timeout: 600000,
      },
      (res) => {
        let body = "";
        res.on("data", (c) => (body += c));
        res.on("end", () => {
          try {
            const j = JSON.parse(body);
            if (j.error) return reject(new Error(j.error.message || body));
            const content = j.choices?.[0]?.message?.content ?? "";
            const meta = j.x_llmroute || {};
            resolve({ content, model: j.model, tier: meta.tier || "?" });
          } catch (e) {
            reject(new Error("bad gateway response: " + body.slice(0, 200)));
          }
        });
      }
    );
    req.on("error", (e) =>
      reject(new Error("cannot reach gateway at " + base + ": " + e.message))
    );
    req.on("timeout", () => req.destroy(new Error("gateway timeout")));
    req.write(payload);
    req.end();
  });
}

// ------------------------------------------------------------------ tools
function parseTool(text) {
  const t = String(text).replace(/```(?:json)?/gi, "");
  const matches = t.match(/\{[\s\S]*?\}/g);
  if (!matches) return null;
  for (const m of matches) {
    if (!/"tool"/.test(m)) continue;
    try {
      const obj = JSON.parse(m);
      if (obj && typeof obj.tool === "string") return obj;
    } catch (_) {}
  }
  return null;
}

async function runTool(action) {
  try {
    switch (action.tool) {
      case "read_file": {
        const abs = safeResolve(action.path);
        const buf = await vscode.workspace.fs.readFile(vscode.Uri.file(abs));
        let txt = Buffer.from(buf).toString("utf8");
        if (txt.length > 60000) txt = txt.slice(0, 60000) + "\n...[truncated]";
        return txt;
      }
      case "list_dir": {
        const abs = safeResolve(action.path || ".");
        const items = await vscode.workspace.fs.readDirectory(
          vscode.Uri.file(abs)
        );
        return (
          items
            .map(([n, t]) => (t === vscode.FileType.Directory ? n + "/" : n))
            .join("\n") || "(empty)"
        );
      }
      case "edit_file": {
        const abs = safeResolve(action.path);
        const ok = await vscode.window.showWarningMessage(
          `Assistant wants to write ${action.path}`,
          { modal: true },
          "Apply",
          "Reject"
        );
        if (ok !== "Apply") return "USER REJECTED the edit.";
        const enc = Buffer.from(action.content ?? "", "utf8");
        await vscode.workspace.fs.writeFile(vscode.Uri.file(abs), enc);
        const doc = await vscode.workspace.openTextDocument(
          vscode.Uri.file(abs)
        );
        vscode.window.showTextDocument(doc, { preview: false });
        return `Wrote ${action.path} (${enc.length} bytes).`;
      }
      case "run_command": {
        const ok = await vscode.window.showWarningMessage(
          `Assistant wants to run:\n\n${action.command}`,
          { modal: true },
          "Run",
          "Reject"
        );
        if (ok !== "Run") return "USER REJECTED the command.";
        return await new Promise((resolve) => {
          cp.exec(
            action.command,
            { cwd: workspaceRoot(), timeout: 60000, maxBuffer: 1024 * 1024 },
            (err, stdout, stderr) => {
              const out = (stdout || "") + (stderr || "");
              resolve(
                (err ? `[exit ${err.code}]\n` : "") +
                  (out.slice(0, 8000) || "(no output)")
              );
            }
          );
        });
      }
      default:
        return "Unknown tool: " + action.tool;
    }
  } catch (e) {
    const msg = String(e.message || e);
    if (/escapes the workspace|ENOENT|not found|EISDIR|no such/i.test(msg)) {
      const top = await listWorkspaceTop();
      return (
        `ERROR: ${msg}. Use a path RELATIVE to the workspace root ` +
        `(e.g. "experiments/tasks.py"). Top-level entries:\n${top}`
      );
    }
    return "TOOL ERROR: " + msg;
  }
}

// ------------------------------------------------------------------ prompt
async function buildSystemPrompt() {
  const top = await listWorkspaceTop();
  const ed = vscode.window.activeTextEditor;
  let ctx = `Top-level entries in the workspace (relative to the root):\n${top}`;
  if (ed) {
    const rel = path.relative(workspaceRoot(), ed.document.uri.fsPath);
    ctx += `\n\nActive file (relative path): ${rel} (${ed.document.languageId})`;
    const sel = ed.document.getText(ed.selection);
    if (sel && sel.trim())
      ctx += `\nSelected text:\n\`\`\`\n${sel.slice(0, 4000)}\n\`\`\``;
  }
  return [
    "You are LLM Router Assistant, an agentic AI coding assistant embedded in",
    "VS Code. You help read, write, and run code in the user's workspace.",
    "",
    "TOOLS: to use a tool, reply with EXACTLY ONE JSON object and NOTHING else",
    "(no prose, no markdown fences). Available tools:",
    '  {"tool":"read_file","path":"relative/path"}',
    '  {"tool":"list_dir","path":"relative/path"}',
    '  {"tool":"edit_file","path":"relative/path","content":"FULL NEW FILE CONTENT"}',
    '  {"tool":"run_command","command":"shell command"}',
    "",
    "RULES:",
    "- Paths MUST be RELATIVE to the workspace root. NEVER use absolute paths",
    "  and NEVER invent paths like /workspace/root. Only use paths that exist",
    "  (see the listing below) or that you discover via list_dir.",
    "- Use list_dir to explore before reading/editing if unsure.",
    "- One tool per step. After each tool you receive its result, then continue.",
    "- When finished, reply with a normal natural-language answer (no JSON).",
    "",
    "CONTEXT:",
    ctx,
  ].join("\n");
}

// ------------------------------------------------------------------ agent loop
async function runAgent(userText, history, view) {
  const sys = await buildSystemPrompt();
  const messages = [
    { role: "system", content: sys },
    ...history,
    { role: "user", content: userText },
  ];
  const maxSteps = cfg().get("maxSteps", 6);
  const model = agentModel();

  for (let step = 0; step < maxSteps; step++) {
    view.post({ type: "status", text: "thinking…" });
    let res;
    try {
      res = await gatewayChat(messages, model);
    } catch (e) {
      view.post({ type: "error", text: String(e.message || e) });
      return history;
    }

    const action = parseTool(res.content);
    if (!action) {
      if (/"tool"\s*:/.test(res.content) && step < maxSteps - 1) {
        view.post({
          type: "tool",
          tool: "(malformed tool call)",
          detail: "asking the model to retry",
          model: res.model,
          tier: res.tier,
        });
        messages.push({ role: "assistant", content: res.content });
        messages.push({
          role: "user",
          content:
            "That was not valid. Reply with EXACTLY one JSON object and " +
            'nothing else, e.g. {"tool":"list_dir","path":"."}. ' +
            "Use RELATIVE paths only.",
        });
        continue;
      }
      view.post({
        type: "assistant",
        text: res.content,
        model: res.model,
        tier: res.tier,
      });
      history.push({ role: "user", content: userText });
      history.push({ role: "assistant", content: res.content });
      return history;
    }

    view.post({
      type: "tool",
      tool: action.tool,
      detail: action.path || action.command || "",
      model: res.model,
      tier: res.tier,
    });

    let result;
    try {
      result = await runTool(action);
    } catch (e) {
      result = "TOOL ERROR: " + (e.message || e);
    }
    view.post({ type: "tool-result", tool: action.tool, result });

    messages.push({ role: "assistant", content: res.content });
    messages.push({
      role: "user",
      content: `TOOL RESULT (${action.tool}):\n${result}`,
    });
  }

  view.post({
    type: "assistant",
    text: "(stopped: reached the maximum number of tool steps)",
    model: "-",
    tier: "-",
  });
  return history;
}

// ------------------------------------------------------------------ webview
class ChatViewProvider {
  constructor(context) {
    this.context = context;
    this.history = [];
    this.view = null;
  }
  post(msg) {
    if (this.view) this.view.webview.postMessage(msg);
  }
  async sendUserMessage(text) {
    await vscode.commands.executeCommand("llmrouter.chat.focus");
    for (let i = 0; i < 20 && !this.view; i++)
      await new Promise((r) => setTimeout(r, 100));
    this.post({ type: "user-echo", text });
    this.history = await runAgent(text, this.history, this);
    this.post({ type: "status", text: "" });
  }
  resolveWebviewView(webviewView) {
    this.view = webviewView;
    const w = webviewView.webview;
    w.options = {
      enableScripts: true,
      localResourceRoots: [
        vscode.Uri.joinPath(this.context.extensionUri, "media"),
      ],
    };
    w.html = this.html(w);
    w.onDidReceiveMessage(async (m) => {
      if (m.type === "send") {
        this.post({ type: "user-echo", text: m.text });
        this.history = await runAgent(m.text, this.history, this);
        this.post({ type: "status", text: "" });
      } else if (m.type === "new") {
        this.history = [];
        this.post({ type: "clear" });
      }
    });
  }
  html(webview) {
    const nonce = String(Math.random()).slice(2);
    const mediaUri = (f) =>
      webview.asWebviewUri(
        vscode.Uri.joinPath(this.context.extensionUri, "media", f)
      );
    const gw = cfg().get("gatewayUrl", "http://localhost:11435");
    const csp = [
      "default-src 'none'",
      `style-src ${webview.cspSource} 'unsafe-inline'`,
      `script-src 'nonce-${nonce}'`,
      `connect-src ${gw} http://localhost:11435 http://127.0.0.1:11435`,
    ].join("; ");
    return `<!DOCTYPE html><html><head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<link rel="stylesheet" href="${mediaUri("main.css")}">
</head><body>
<div id="header"><span id="brand">LLM Router</span><span id="stats"></span></div>
<div id="messages"></div>
<div id="composer">
  <textarea id="input" rows="2" placeholder="Ask about your code, request an edit, or a command…"></textarea>
  <button id="send">Send</button>
</div>
<script nonce="${nonce}">window.GATEWAY = ${JSON.stringify(gw)};</script>
<script nonce="${nonce}" src="${mediaUri("main.js")}"></script>
</body></html>`;
  }
}

// ------------------------------------------------------------------ inline completion
function trimCompletion(text) {
  let t = String(text).replace(/```[a-zA-Z]*\n?/g, "").replace(/```/g, "");
  t = t.replace(/^[\r\n]+/, "");
  const lines = t.split("\n").slice(0, 12);
  return lines.join("\n").replace(/\s+$/, "");
}

function makeInlineProvider() {
  return {
    async provideInlineCompletionItems(document, position, ctxObj, token) {
      if (!cfg().get("enableCompletions", true)) return;
      await new Promise((r) => setTimeout(r, 250)); // debounce
      if (token.isCancellationRequested) return;

      const prefix = document
        .getText(new vscode.Range(new vscode.Position(0, 0), position))
        .slice(-1500);
      const endPos = document.lineAt(document.lineCount - 1).range.end;
      const suffix = document
        .getText(new vscode.Range(position, endPos))
        .slice(0, 400);
      if (!prefix.trim()) return;

      const messages = [
        {
          role: "system",
          content:
            "You are a code completion engine. Output ONLY the code that should " +
            "be inserted at the cursor to continue the program. No explanations, " +
            "no markdown fences, no repetition of existing code.",
        },
        {
          role: "user",
          content:
            `Language: ${document.languageId}\n<BEFORE_CURSOR>\n${prefix}\n` +
            (suffix ? `<AFTER_CURSOR>\n${suffix}\n` : "") +
            `Provide only the insertion at the cursor.`,
        },
      ];
      let res;
      try {
        res = await gatewayChat(messages, completionModel());
      } catch (_) {
        return;
      }
      if (token.isCancellationRequested) return;
      const text = trimCompletion(res.content);
      if (!text) return;
      return [
        new vscode.InlineCompletionItem(
          text,
          new vscode.Range(position, position)
        ),
      ];
    },
  };
}

// ------------------------------------------------------------------ editor commands
function selectionOrFile() {
  const ed = vscode.window.activeTextEditor;
  if (!ed) return null;
  const sel = ed.document.getText(ed.selection);
  const text = sel && sel.trim() ? sel : ed.document.getText();
  const rel = path.relative(workspaceRoot(), ed.document.uri.fsPath);
  return { text, lang: ed.document.languageId, rel };
}

function editorCommand(kind, provider) {
  return async () => {
    const s = selectionOrFile();
    if (!s) {
      vscode.window.showInformationMessage("Open a file first.");
      return;
    }
    const fence = "```" + s.lang + "\n" + s.text + "\n```";
    const prompts = {
      explain: `Explain what this code does (from ${s.rel}):\n\n${fence}`,
      fix: `Find and fix bugs in this code (from ${s.rel}). Explain the fix and show the corrected code:\n\n${fence}`,
      doc: `Add clear docstrings/comments to this code (from ${s.rel}) and return the documented version:\n\n${fence}`,
      tests: `Write thorough unit tests for this code (from ${s.rel}):\n\n${fence}`,
    };
    await provider.sendUserMessage(prompts[kind] || prompts.explain);
  };
}

// ------------------------------------------------------------------ activate
function pollStats(provider, status) {
  const base = cfg().get("gatewayUrl", "http://localhost:11435");
  http
    .get(base + "/stats", (res) => {
      let b = "";
      res.on("data", (c) => (b += c));
      res.on("end", () => {
        try {
          const s = JSON.parse(b);
          SMALL_MODEL = s.small_model || SMALL_MODEL;
          LARGE_MODEL = s.large_model || LARGE_MODEL;
          status.text = `$(compass) ${s.pct_local}% local · $${(
            s.est_saved || 0
          ).toFixed(2)} saved`;
          provider.post({ type: "stats", stats: s });
        } catch (_) {}
      });
    })
    .on("error", () => {
      status.text = "$(compass) Router (offline)";
    });
}

function activate(context) {
  const provider = new ChatViewProvider(context);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("llmrouter.chat", provider, {
      webviewOptions: { retainContextWhenHidden: true },
    })
  );

  // inline (ghost-text) completions
  context.subscriptions.push(
    vscode.languages.registerInlineCompletionItemProvider(
      { pattern: "**" },
      makeInlineProvider()
    )
  );

  const status = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Right,
    100
  );
  status.command = "llmrouter.focusChat";
  status.text = "$(compass) Router";
  status.tooltip = "LLM Router Assistant";
  status.show();
  context.subscriptions.push(status);

  pollStats(provider, status);
  const poll = setInterval(() => pollStats(provider, status), 4000);
  context.subscriptions.push({ dispose: () => clearInterval(poll) });

  context.subscriptions.push(
    vscode.commands.registerCommand("llmrouter.focusChat", () =>
      vscode.commands.executeCommand("llmrouter.chat.focus")
    ),
    vscode.commands.registerCommand("llmrouter.newChat", () => {
      provider.history = [];
      provider.post({ type: "clear" });
    }),
    vscode.commands.registerCommand("llmrouter.showStats", () => {
      const base = cfg().get("gatewayUrl", "http://localhost:11435");
      vscode.env.openExternal(vscode.Uri.parse(base + "/stats"));
    }),
    vscode.commands.registerCommand("llmrouter.explain", editorCommand("explain", provider)),
    vscode.commands.registerCommand("llmrouter.fix", editorCommand("fix", provider)),
    vscode.commands.registerCommand("llmrouter.doc", editorCommand("doc", provider)),
    vscode.commands.registerCommand("llmrouter.tests", editorCommand("tests", provider)),
    vscode.commands.registerCommand("llmrouter.toggleCompletions", async () => {
      const cur = cfg().get("enableCompletions", true);
      await cfg().update("enableCompletions", !cur, true);
      vscode.window.showInformationMessage(
        "LLM Router inline completions " + (!cur ? "enabled" : "disabled")
      );
    })
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
