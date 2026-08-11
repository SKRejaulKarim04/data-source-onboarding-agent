
"use strict";

const $ = (id) => document.getElementById(id);
let state = null;

/* --- HTTP ---------------------------------------------------------------- */

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail || detail; } catch (e) { /* keep statusText */ }
    throw new Error(detail);
  }
  return response.json();
}

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/* --- Chat helpers -------------------------------------------------------- */

function addMsg(type, html, rawPrompt = null) {
  $("welcome")?.remove();
  const thread = $("chat-thread");
  const div = document.createElement("div");
  div.className = `msg ${type}`;
  
  if (type === "user") {
    let editHtml = "";
    if (rawPrompt) {
      editHtml = `
        <button class="edit-icon" title="Edit prompt" onclick="editPrompt(this)" style="display:none; background:transparent; border:none; cursor:pointer; margin-top:8px; color:rgba(255,255,255,0.7); font-size:12px; font-family:var(--font); text-decoration:underline;">
          Edit
        </button>`;
    }
    div.innerHTML = `
      <div class="msg-avatar">U</div>
      <div class="msg-body group">
        <div class="msg-content">${html}</div>
        ${editHtml}
      </div>`;
    
    if (rawPrompt) {
      // Show edit on hover
      div.addEventListener("mouseenter", () => div.querySelector(".edit-icon").style.display = "block");
      div.addEventListener("mouseleave", () => div.querySelector(".edit-icon").style.display = "none");
      div.dataset.raw = rawPrompt;
    }
  } else {
    div.innerHTML = `
      <div class="msg-avatar">⚡</div>
      <div class="msg-body">${html}</div>`;
  }
  
  thread.appendChild(div);
  thread.scrollTop = thread.scrollHeight;
  return div;
}

function editPrompt(btn) {
  const msg = btn.closest(".msg");
  const raw = msg.dataset.raw;
  
  // Remove all following messages
  while (msg.nextSibling) {
    msg.nextSibling.remove();
  }
  
  const body = msg.querySelector(".msg-body");
  body.innerHTML = `
    <textarea class="edit-textarea" style="width:100%; min-width:300px; background:rgba(0,0,0,0.3); border:1px solid var(--border); border-radius:8px; color:#fff; font-family:var(--font); padding:8px; font-size:13.5px; resize:vertical; min-height:60px;"></textarea>
    <div style="display:flex; gap:8px; margin-top:8px;">
      <button class="btn" onclick="savePrompt(this)">Save & Submit</button>
      <button class="btn ghost" onclick="cancelEdit(this)">Cancel</button>
    </div>
  `;
  const textarea = body.querySelector(".edit-textarea");
  textarea.value = raw;
  textarea.focus();
}

function cancelEdit(btn) {
  const msg = btn.closest(".msg");
  const raw = msg.dataset.raw;
  msg.querySelector(".msg-body").innerHTML = `
    <div class="msg-content">${escapeHtml(raw)}</div>
    <button class="edit-icon" title="Edit prompt" onclick="editPrompt(this)" style="display:none; background:transparent; border:none; cursor:pointer; margin-top:8px; color:rgba(255,255,255,0.7); font-size:12px; font-family:var(--font); text-decoration:underline;">
      Edit
    </button>
  `;
}

function savePrompt(btn) {
  const msg = btn.closest(".msg");
  const newPrompt = msg.querySelector(".edit-textarea").value.trim();
  if (!newPrompt) return;
  
  msg.dataset.raw = newPrompt;
  msg.querySelector(".msg-body").innerHTML = `
    <div class="msg-content">${escapeHtml(newPrompt)}</div>
    <button class="edit-icon" title="Edit prompt" onclick="editPrompt(this)" style="display:none; background:transparent; border:none; cursor:pointer; margin-top:8px; color:rgba(255,255,255,0.7); font-size:12px; font-family:var(--font); text-decoration:underline;">
      Edit
    </button>
  `;
  
  // Re-submit
  const typing = addTyping();
  $("send-btn").disabled = true;

  api("/api/requests", { method: "POST", body: JSON.stringify({ prompt: newPrompt }) })
    .then(s => {
      state = s;
      removeTyping();
      paintExtractionInChat();
      paintQuestionsInChat();
      paintRightPanel();
    })
    .catch(e => {
      removeTyping();
      addMsg("agent", `<div class="note-inline bad">Extraction failed: ${escapeHtml(e.message)}</div>`);
    })
    .finally(() => {
      $("send-btn").disabled = false;
    });
}

function addTyping() {
  const div = document.createElement("div");
  div.className = "msg agent";
  div.innerHTML = `<div class="msg-avatar">⚡</div><div class="msg-body"><div class="typing"><span></span><span></span><span></span></div></div>`;
  div.id = "typing-indicator";
  $("chat-thread").appendChild(div);
  $("chat-thread").scrollTop = $("chat-thread").scrollHeight;
  return div;
}

function removeTyping() {
  const el = $("typing-indicator");
  if (el) el.remove();
}

/* --- Paint functions (right panel) --------------------------------------- */

function paintChecks() {
  const c = state && state.connector;
  if (!c || !c.checks) { $("tab-checks").innerHTML = `<div class="empty-state"><div class="icon">📋</div>No connector generated yet.</div>`; return; }

  const grid = c.checks.map(k =>
    `<div class="check-item ${k.passed ? "ok" : "bad"}"><span class="mark">${k.passed ? "PASS" : "FAIL"}</span>${k.name}</div>`
  ).join("");

  const findings = (c.findings || []).length
    ? `<h3 style="font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--text-dim);margin:20px 0 8px">Findings</h3>` +
      c.findings.map(f => `<div class="note ${f.severity === "error" ? "bad" : "warn"}">
          <strong>${escapeHtml(f.check)}</strong>${f.line ? ` &middot; line ${f.line}` : ""} &mdash; ${escapeHtml(f.message)}
          ${f.remedy ? `<br><span style="color:var(--text-dim);font-size:12px">Fix: ${escapeHtml(f.remedy)}</span>` : ""}
        </div>`).join("")
    : "";

  const warnings = (c.warnings || []).map(w => `<div class="note warn">${escapeHtml(w)}</div>`).join("");

  $("tab-checks").innerHTML = `
    <div style="margin-bottom:14px">
      <span class="flag ${c.accepted ? "pass" : "fail"}">${c.accepted ? "accepted" : "rejected"}</span>
      <span style="font-family:var(--mono);font-size:12px;color:var(--text-dim);margin-left:10px">${escapeHtml(c.summary)}</span>
    </div>
    ${warnings}
    <div class="checks-grid">${grid}</div>
    ${findings}`;
}

function paintCode() {
  const c = state && state.connector;
  if (!c || !c.code) { $("tab-code").innerHTML = `<div class="empty-state"><div class="icon">💻</div>No connector generated yet.</div>`; return; }
  $("tab-code").innerHTML = `
    <dl class="kv" style="margin-bottom:12px">
      <dt>module</dt><dd>${escapeHtml(c.module_name)}</dd>
      <dt>template</dt><dd>${escapeHtml(c.template_key)} v${escapeHtml(c.template_version)}</dd>
      <dt>spec sha</dt><dd>${escapeHtml(c.spec_checksum)}</dd>
      <dt>code sha</dt><dd>${escapeHtml(c.code_checksum)}</dd>
      <dt>repairs</dt><dd>${c.repair_iterations}</dd>
    </dl>
    <pre class="code">${escapeHtml(c.code)}</pre>`;
}

function paintConnect() {
  const c = state && state.connector;
  if (!c || !c.code) { $("tab-connect").innerHTML = `<div class="empty-state"><div class="icon">🔗</div>Generate a connector first.</div>`; return; }

  const vars = ((state.artifact && state.artifact.manifest && state.artifact.manifest.required_env) || [])
    .filter(v => v.endsWith("USERNAME") || v.endsWith("PASSWORD"));

  const t = state.sandbox;
  const result = (t && t.summary)
    ? `<div class="note ${t.success ? "" : "bad"}" style="margin-top:14px">
         <span class="flag ${t.success ? "pass" : "fail"}">${t.success ? "connected" : "failed"}</span>
         <span style="font-family:var(--mono);font-size:12px;margin-left:8px">${escapeHtml(t.summary)}</span>
       </div>` + (t.tables && t.tables.length ? renderSchema(t.tables) : "")
    : "";

  $("tab-connect").innerHTML = `
    <p style="font-size:13px;color:var(--text-dim);margin-top:0">
      Credentials are sent once for this test. They are not stored, logged, or written to the artifact.
    </p>
    ${vars.map(v => `<label class="cred-label">
        <span>${escapeHtml(v)}</span>
        <input type="${v.endsWith("PASSWORD") ? "password" : "text"}" data-cred="${escapeHtml(v)}">
      </label>`).join("")}
    <div class="actions"><button class="btn" id="run-test">Run connection test</button></div>
    ${result}`;

  const button = $("run-test");
  if (button) button.addEventListener("click", runTest);
}

function renderSchema(tables) {
  return `<h3 style="font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--text-dim);margin:20px 0 8px">
      Schema &mdash; ${tables.length} tables</h3>
    <table class="schema"><thead><tr><th>table</th><th>columns</th><th>primary key</th></tr></thead><tbody>
    ${tables.map(t => `<tr>
      <td>${escapeHtml(t.schema)}.${escapeHtml(t.name)}</td>
      <td>${t.columns.length}</td>
      <td>${escapeHtml(t.columns.filter(c => c.primary_key).map(c => c.name).join(", ") || "—")}</td>
    </tr>`).join("")}</tbody></table>`;
}

function paintArtifact() {
  const a = state && state.artifact;
  if (!a || !a.name) { $("tab-artifact").innerHTML = `<div class="empty-state"><div class="icon">📦</div>No artifact yet.</div>`; return; }
  $("tab-artifact").innerHTML = `
    <dl class="kv" style="margin-bottom:14px">
      <dt>name</dt><dd>${escapeHtml(a.name)}</dd>
      <dt>version</dt><dd>${escapeHtml(a.version)}</dd>
      <dt>checksum</dt><dd>${escapeHtml(a.checksum)}</dd>
      <dt>files</dt><dd>${a.files.map(escapeHtml).join(", ")}</dd>
    </dl>
    <div class="actions">
      <a href="/api/requests/${state.id}/download" download><button class="btn">📥 Download bundle</button></a>
    </div>
    <h3 style="font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--text-dim);margin:20px 0 8px">Manifest</h3>
    <pre class="code">${escapeHtml(JSON.stringify(a.manifest, null, 2))}</pre>`;
}

function paintRightPanel() {
  paintChecks();
  paintCode();
  paintConnect();
  paintArtifact();
}

/* --- Chat: paint extraction into conversation ---------------------------- */

function paintExtractionInChat() {
  const ex = state.extraction;
  if (!ex) return;

  let html = `<div class="label">Extraction Result</div>`;

  // Security findings
  const notes = [];
  (ex.security_findings || []).forEach(f => {
    const cls = f.kind === "credential" ? "bad" : "warn";
    notes.push(`<div class="note-inline ${cls}"><strong>${escapeHtml(f.label)}</strong> — ${escapeHtml(f.detail)}</div>`);
  });
  (ex.notes || []).forEach(n => notes.push(`<div class="note-inline ok">${escapeHtml(n)}</div>`));
  html += notes.join("");

  // Spec summary
  const d = ex.draft || {};
  const rows = [
    ["confidence", `${(ex.confidence * 100).toFixed(0)}%`],
    ["source type", d.source_type || "—"],
    ["class", d.connector_name || "—"],
    ["host", d.host || d.base_url || "—"],
    ["port", d.port || "—"],
    ["database", d.database || "—"],
    ["auth", d.auth_method || "—"],
    ["access", d.read_only === false ? "read-write" : "read-only"],
  ];
  if ((ex.assumed || []).length) rows.push(["assumed", ex.assumed.join(", ")]);
  if ((ex.missing || []).length) rows.push(["missing", `<span class="flag fail">${ex.missing.join(", ")}</span>`]);

  html += `<dl class="spec-grid">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>`;

  // Generate button if ready
  let btnId = null;
  if (ex.ready) {
    btnId = 'gen-' + Math.random().toString(36).substr(2, 9);
    html += `<div class="actions"><button class="btn" id="${btnId}">⚡ Generate Connector</button></div>`;
  }

  addMsg("agent", html);

  // Wire up generate button
  if (btnId) {
    const genBtn = $(btnId);
    if (genBtn) genBtn.addEventListener("click", () => generate(btnId));
  }
}

function paintQuestionsInChat() {
  const qs = (state.extraction && state.extraction.questions) || [];
  if (!qs.length) return;

  const btnId = 'ans-' + Math.random().toString(36).substr(2, 9);
  let html = `<div class="label">I need a few more details</div><div class="q-block">`;
  qs.forEach(q => {
    const control = q.options && q.options.length
      ? `<select data-field="${q.field}"><option value="">— choose —</option>${
          q.options.map(o => `<option value="${escapeHtml(o)}">${escapeHtml(o)}</option>`).join("")}</select>`
      : `<input type="text" data-field="${q.field}" placeholder="${escapeHtml(q.example || "")}">`;
    html += `<div class="q-item">
      <div class="q-text">${escapeHtml(q.question)}</div>
      <div class="q-why">${escapeHtml(q.why)}</div>
      ${control}
    </div>`;
  });
  html += `</div><div class="q-actions"><button class="btn" id="${btnId}">Submit answers</button></div>`;

  const msgEl = addMsg("agent", html);

  $(btnId).addEventListener("click", () => applyAnswers(msgEl, btnId));
}

/* --- Actions ------------------------------------------------------------- */

async function submit() {
  const prompt = $("prompt").value.trim();
  if (!prompt) return;

  addMsg("user", escapeHtml(prompt), prompt);
  $("prompt").value = "";
  autoResize();

  const typing = addTyping();
  $("send-btn").disabled = true;

  try {
    state = await api("/api/requests", { method: "POST", body: JSON.stringify({ prompt }) });
    removeTyping();
    paintExtractionInChat();
    paintQuestionsInChat();
    paintRightPanel();
  } catch (e) {
    removeTyping();
    addMsg("agent", `<div class="note-inline bad">Extraction failed: ${escapeHtml(e.message)}</div>`);
  } finally {
    $("send-btn").disabled = false;
  }
}

async function applyAnswers(msgEl, btnId) {
  const answers = {};
  msgEl.querySelectorAll(".q-item [data-field]").forEach(el => {
    if (el.value.trim()) answers[el.dataset.field] = el.value.trim();
  });
  if (!Object.keys(answers).length) return;

  // Show user's answers as a message
  const answerText = Object.entries(answers).map(([k, v]) => `<strong>${escapeHtml(k)}</strong>: ${escapeHtml(v)}`).join("<br>");
  addMsg("user", answerText);

  const typing = addTyping();
  const btn = $(btnId);
  if (btn) btn.disabled = true;

  try {
    state = await api(`/api/requests/${state.id}/answers`, { method: "POST", body: JSON.stringify({ answers }) });
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Update answers";
    }
    removeTyping();
    paintExtractionInChat();
    paintQuestionsInChat();
    paintRightPanel();
  } catch (e) {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Submit answers";
    }
    removeTyping();
    addMsg("agent", `<div class="note-inline bad">Could not apply answers: ${escapeHtml(e.message)}</div>`);
  }
}

async function generate(btnId) {
  addMsg("user", "Generate the connector");
  const typing = addTyping();
  const btn = $(btnId);
  if (btn) btn.disabled = true;

  try {
    state = await api(`/api/requests/${state.id}/generate`, { method: "POST" });
    removeTyping();

    const c = state.connector;
    let html = `<div class="label">Connector Generated</div>`;
    html += `<div class="note-inline ${c.accepted ? "ok" : "bad"}">${c.accepted ? "✓ Accepted" : "✗ Rejected"} — ${escapeHtml(c.summary)}</div>`;
    html += `<p style="font-size:12px;color:var(--text-dim);margin-top:8px">Check the <strong>Standards</strong>, <strong>Code</strong>, and <strong>Artifact</strong> tabs on the right for full details.</p>`;
    addMsg("agent", html);

    paintRightPanel();
    showTab("checks");
  } catch (e) {
    if (btn) btn.disabled = false;
    removeTyping();
    addMsg("agent", `<div class="note-inline bad">Generation failed: ${escapeHtml(e.message)}</div>`);
  }
}

async function runTest() {
  const credentials = {};
  document.querySelectorAll("#tab-connect [data-cred]").forEach(el => {
    if (el.value) credentials[el.dataset.cred] = el.value;
  });
  const button = $("run-test");
  if (button) { button.disabled = true; button.textContent = "Testing…"; }

  try {
    state = await api(`/api/requests/${state.id}/test`, { method: "POST", body: JSON.stringify({ credentials }) });

    const t = state.sandbox;
    let html = `<div class="label">Connection Test</div>`;
    html += `<div class="note-inline ${t.success ? "ok" : "bad"}">${t.success ? "✓ Connected" : "✗ Failed"} — ${escapeHtml(t.summary)}</div>`;
    addMsg("agent", html);

    paintRightPanel();
    showTab("connect");
  } catch (e) {
    addMsg("agent", `<div class="note-inline bad">Connection test failed: ${escapeHtml(e.message)}</div>`);
  } finally {
    const b = $("run-test");
    if (b) { b.disabled = false; b.textContent = "Run connection test"; }
  }
}

function showTab(name) {
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === name));
  ["checks", "code", "connect", "artifact"].forEach(t => $("tab-" + t).classList.toggle("hidden", t !== name));
}

/* --- Auto-resize textarea ------------------------------------------------ */

function autoResize() {
  const el = $("prompt");
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 120) + "px";
}

/* --- Wiring -------------------------------------------------------------- */

$("send-btn").addEventListener("click", submit);
$("prompt").addEventListener("input", autoResize);
$("prompt").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
});

document.querySelectorAll("[data-fill]").forEach(b =>
  b.addEventListener("click", () => {
    $("prompt").value = b.dataset.fill;
    autoResize();
    $("prompt").focus();
  })
);

document.querySelectorAll("#tabs button").forEach(b =>
  b.addEventListener("click", () => showTab(b.dataset.tab))
);

api("/api/health").then(h => {
  $("health").textContent = h.live_model ? "live model" : "offline — scripted";
}).catch(() => { $("health").textContent = "api unreachable"; });

/* --- Resizer ------------------------------------------------------------- */
const resizer = $("resizer");
const leftPanel = $("chat-column");
let isDragging = false;

resizer.addEventListener("mousedown", (e) => {
  isDragging = true;
  resizer.classList.add("dragging");
  document.body.style.cursor = "col-resize";
  e.preventDefault();
});

document.addEventListener("mousemove", (e) => {
  if (!isDragging) return;
  leftPanel.style.width = e.clientX + "px";
});

document.addEventListener("mouseup", () => {
  if (isDragging) {
    isDragging = false;
    resizer.classList.remove("dragging");
    document.body.style.cursor = "default";
  }
});
