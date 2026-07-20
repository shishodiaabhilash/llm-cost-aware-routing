// Webview UI for LLM Router Assistant.
const vscode = acquireVsCodeApi();
const $ = (id) => document.getElementById(id);
const messages = $("messages");

function escapeHtml(s) {
  return (s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// very small markdown-ish renderer: fenced code blocks + inline code
function render(text) {
  const parts = String(text).split(/```/);
  let html = "";
  for (let i = 0; i < parts.length; i++) {
    if (i % 2 === 1) {
      const body = parts[i].replace(/^[a-zA-Z0-9]+\n/, "");
      html += `<pre><code>${escapeHtml(body)}</code></pre>`;
    } else {
      html += escapeHtml(parts[i])
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\n/g, "<br>");
    }
  }
  return html;
}

function bubble(cls) {
  const el = document.createElement("div");
  el.className = "msg " + cls;
  messages.appendChild(el);
  messages.scrollTop = messages.scrollHeight;
  return el;
}

let statusEl = null;

window.addEventListener("message", (e) => {
  const m = e.data;
  if (m.type === "user-echo") {
    const b = bubble("user");
    b.innerHTML = `<div class="who">You</div>${render(m.text)}`;
  } else if (m.type === "status") {
    if (m.text) {
      if (!statusEl) statusEl = bubble("status");
      statusEl.textContent = m.text;
    } else if (statusEl) {
      statusEl.remove();
      statusEl = null;
    }
  } else if (m.type === "tool") {
    const b = bubble("tool");
    b.innerHTML = `<div class="who">🔧 ${escapeHtml(m.tool)} <span class="tier">${escapeHtml(
      m.tier || ""
    )}</span></div><code>${escapeHtml(m.detail || "")}</code>`;
  } else if (m.type === "tool-result") {
    const b = bubble("tool-result");
    b.innerHTML = `<div class="who">↳ result</div><pre>${escapeHtml(
      (m.result || "").slice(0, 1200)
    )}</pre>`;
  } else if (m.type === "assistant") {
    if (statusEl) {
      statusEl.remove();
      statusEl = null;
    }
    const b = bubble("assistant");
    const badge = m.model
      ? `<span class="badge tier-${(m.tier || "").replace(
          /[^a-z]/gi,
          ""
        )}">${escapeHtml(m.tier || "")} · ${escapeHtml(m.model || "")}</span>`
      : "";
    b.innerHTML = `<div class="who">Assistant ${badge}</div>${render(m.text)}`;
  } else if (m.type === "error") {
    if (statusEl) {
      statusEl.remove();
      statusEl = null;
    }
    const b = bubble("error");
    b.innerHTML = `<div class="who">⚠ Error</div>${escapeHtml(m.text)}`;
  } else if (m.type === "clear") {
    messages.innerHTML = "";
    statusEl = null;
  } else if (m.type === "stats") {
    const s = m.stats;
    $("stats").textContent = `${s.pct_local}% local · $${(
      s.est_saved || 0
    ).toFixed(2)} saved · ${s.total} reqs`;
  }
});

function send() {
  const input = $("input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  vscode.postMessage({ type: "send", text });
}

$("send").addEventListener("click", send);
$("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});
