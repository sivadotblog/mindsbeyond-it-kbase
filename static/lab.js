/* Mindsbeyond KB Lab: vanilla JS, no build step. Talks to /api/v2. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const DEFAULT_METHODS = ["fulltext", "vector_ann", "vector_enn", "hybrid_rrf", "hybrid_score"];

const state = { health: null, caps: null, methods: [], selected: new Set(DEFAULT_METHODS), run: null, lastCompare: null, lastOrder: [] };

async function api(path, opts = {}) {
  const init = { headers: { "Content-Type": "application/json" }, ...opts };
  if (init.body && typeof init.body !== "string") init.body = JSON.stringify(init.body);
  const resp = await fetch(`/api/v2${path}`, init);
  let data = null;
  try { data = await resp.json(); } catch (_) { /* empty body */ }
  if (!resp.ok) throw new Error((data && data.error) || `Request failed with HTTP ${resp.status}`);
  return data;
}

function user() {
  return ($("#user").value || "").trim() || "siva";
}

function busy(button, on) {
  if (!button) return;
  button.disabled = on;
  if (on) { button.dataset.label = button.textContent; button.textContent = "Working…"; }
  else if (button.dataset.label) button.textContent = button.dataset.label;
}

function showError(target, err) {
  target.innerHTML = `<p class="err">${esc(err.message || err)}</p>`;
}

function pipelineHtml(pipeline, color) {
  // Highlight stage names so the shape of the pipeline reads at a glance.
  const json = esc(JSON.stringify(pipeline, null, 2));
  const styled = json.replace(/&quot;(\$[a-zA-Z]+)&quot;:/g, (_, s) => `<span class="stage">"${s}"</span>:`);
  return `<pre class="json" style="--c:${color || "var(--signal)"}">${styled}</pre>`;
}

function methodColor(name) { return `var(--m-${name}, var(--ink-2))`; }

/* ---------------------------------------------------------------- tabs ---- */
function selectTab(id) {
  $$("nav.tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.id === `t-${id}`)));
  $$("section.tab").forEach((s) => { s.hidden = s.id !== `tab-${id}`; });
  if (id === "memory") listMemory();
  if (id === "sop") listRuns();
  try { history.replaceState(null, "", `#${id}`); } catch (_) { /* ignore */ }
}

/* -------------------------------------------------------------- status ---- */
function renderStatus() {
  const h = state.health, c = state.caps;
  if (!h) return;
  const parts = [];
  parts.push(h.mode === "offline"
    ? `<span class="offline">Mode <b>offline</b> (no cluster; results are approximations)</span>`
    : `<span>Mode <b>Atlas</b></span>`);
  if (c && c.server_version) parts.push(`<span>MongoDB <b>${esc(c.server_version)}</b></span>`);
  parts.push(`<span>LLM <b>${esc(h.llm.enabled ? `${h.llm.provider} ${h.llm.model}` : "off (rules)")}</b></span>`);
  parts.push(`<span>Memory <b>${esc(h.default_memory_backend)}</b></span>`);
  parts.push(`<span>Index model <b>${esc(h.index.index_model)}</b></span>`);
  $("#status").innerHTML = parts.join("");
}

/* -------------------------------------------------------------- search ---- */
function renderChips() {
  const avail = (state.caps && state.caps.methods) || {};
  $("#method-chips").innerHTML = state.methods.map((m) => {
    const on = state.selected.has(m.name);
    const a = avail[m.name];
    const note = a && !a.available ? ` <small>(${esc(a.reason)})</small>` : "";
    return `<label class="chip" style="--c:${methodColor(m.name)}" data-on="${on}" title="${esc(m.summary)}">
      <input type="checkbox" value="${esc(m.name)}" ${on ? "checked" : ""}> ${esc(m.label)}${note}</label>`;
  }).join("");
  $$("#method-chips input").forEach((box) => box.addEventListener("change", () => {
    if (box.checked) state.selected.add(box.value); else state.selected.delete(box.value);
    box.closest(".chip").dataset.on = String(box.checked);
  }));
}

function searchBody() {
  const num = (id) => { const v = $(id).value; return v === "" ? null : Number(v); };
  return {
    query: $("#q").value,
    limit: num("#o-limit") || 8,
    num_candidates: num("#o-cands"),
    query_model: $("#o-model").value,
    rerank: $("#o-rerank").checked,
    rerank_model: $("#o-rmodel").value,
    fuzzy: $("#o-fuzzy").checked,
    filters: { category: $("#o-cat").value || null, domain: $("#o-dom").value || null },
    weights: { vector: num("#o-wv") ?? 1, text: num("#o-wt") ?? 1 },
    normalization: $("#o-norm").value,
  };
}

async function compare(ev) {
  ev && ev.preventDefault();
  const out = $("#search-out");
  const methods = state.methods.map((m) => m.name).filter((n) => state.selected.has(n));
  if (!methods.length) { out.innerHTML = `<p class="err">Pick at least one method.</p>`; return; }
  const body = { ...searchBody(), methods };
  if (methods.includes("vector_filtered") && !body.filters.category && !body.filters.domain) {
    out.innerHTML = `<p class="err">Vector with pre filter needs a category or domain filter. Set one under Options.</p>`;
    return;
  }
  const btn = $("#compare-btn");
  busy(btn, true);
  try {
    const data = await api("/search/compare", { method: "POST", body });
    state.lastCompare = data;
    state.lastOrder = methods;
    renderCompare(data, methods);
  } catch (err) { showError(out, err); }
  finally { busy(btn, false); }
}

function renderCompare(data, order) {
  const out = $("#search-out");
  const cols = order.map((name) => data.results[name]).filter(Boolean);
  const limit = Math.max(1, ...cols.map((c) => c.results.length));
  out.innerHTML = `
    <div class="river" id="river">
      <h2>Rank river <span>each line is one article; a flat line means the methods agree on its rank</span></h2>
      <div id="river-svg"></div>
    </div>
    <div class="columns" id="columns">${cols.map(columnHtml).join("")}</div>
    ${agreementHtml(data)}`;
  drawRiver(cols, limit);
  wireHover();
}

function columnHtml(col) {
  const color = methodColor(col.method);
  const meta = `${col.ms} ms${col.reranked ? ", reranked" : ""}${col.offline ? ", offline" : ""}`;
  let body;
  if (col.status !== "ok") {
    const label = col.status === "unsupported" ? "Not available on this cluster" : "Failed";
    body = `<div class="why ${esc(col.status)}"><b>${label}.</b> ${esc(col.reason)}</div>`;
  } else if (!col.results.length) {
    body = `<div class="why">No results.</div>`;
  } else {
    const top = Math.max(...col.results.map((r) => r.score)) || 1;
    body = `<ol>${col.results.map((r) => {
      const pct = Math.max(2, Math.round((r.score / top) * 100));
      let delta = "";
      if (col.reranked && r.rank_change != null) {
        delta = r.rank_change > 0 ? `<span class="delta up" title="moved up from rank ${r.pre_rerank_rank}">▲${r.rank_change}</span>`
          : r.rank_change < 0 ? `<span class="delta down" title="moved down from rank ${r.pre_rerank_rank}">▼${-r.rank_change}</span>`
          : `<span class="delta">=</span>`;
      }
      return `<li data-doc="${esc(r.doc_id)}">
        <span class="r">${r.rank}</span>
        <span><span class="t">${esc(r.title)}</span><br><span class="id">${esc(r.doc_id)}, ${esc(r.domain)}</span></span>
        <span class="s">${r.score.toFixed(4)}<br>${delta}</span>
        <span class="bar"><i style="width:${pct}%"></i></span></li>`;
    }).join("")}</ol>`;
  }
  const warns = (col.warnings || []).map((w) => `<div>${esc(w)}</div>`).join("");
  return `<article class="col" style="--c:${color}">
    <header><h3>${esc(col.label)}</h3><div class="meta">${esc(meta)}</div></header>
    ${body}
    ${warns ? `<div class="warns">${warns}</div>` : ""}
    <details class="pipe"><summary>Pipeline (${(col.pipeline || []).length} stages)</summary>${pipelineHtml(col.pipeline, color)}</details>
  </article>`;
}

function drawRiver(cols, limit) {
  const host = $("#river-svg");
  const colW = 250 + 12; // matches the column min width plus gap
  const width = Math.max(host.clientWidth || 0, cols.length * colW);
  const step = width / cols.length;
  const rowH = 22, top = 14, height = top * 2 + (limit - 1) * rowH;
  const docs = new Map();
  cols.forEach((col, i) => {
    if (col.status !== "ok") return;
    col.results.forEach((r) => {
      if (!docs.has(r.doc_id)) docs.set(r.doc_id, []);
      docs.get(r.doc_id).push({ i, rank: r.rank, method: col.method });
    });
  });
  const x = (i) => step * i + step / 2;
  const y = (rank) => top + (rank - 1) * rowH;
  let svg = `<svg width="${width}" height="${height}" role="img" aria-label="Rank of each article per method">`;
  for (let rank = 1; rank <= limit; rank++) svg += `<text class="rank" x="4" y="${y(rank) + 4}">${rank}</text>`;
  cols.forEach((col, i) => {
    if (col.status !== "ok") svg += `<line x1="${x(i)}" x2="${x(i)}" y1="${top}" y2="${height - top}" stroke="var(--rule)" stroke-dasharray="4 4"/>`;
  });
  for (const [doc, pts] of docs) {
    let path = "";
    pts.forEach((p, k) => {
      const prev = pts[k - 1];
      path += (prev && prev.i === p.i - 1 ? " L" : " M") + `${x(p.i)},${y(p.rank)}`;
    });
    svg += `<g class="doc" data-doc="${esc(doc)}"><title>${esc(doc)}</title><path class="line" d="${path}"/>`;
    pts.forEach((p) => { svg += `<circle class="dot" cx="${x(p.i)}" cy="${y(p.rank)}" r="6" fill="${methodColor(p.method)}"/>`; });
    svg += `</g>`;
  }
  host.innerHTML = svg + `</svg>`;
}

function wireHover() {
  const setHot = (doc) => {
    $$("#river g.doc").forEach((g) => {
      g.classList.toggle("hot", doc != null && g.dataset.doc === doc);
      g.classList.toggle("dim", doc != null && g.dataset.doc !== doc);
    });
    $$("#columns li[data-doc]").forEach((li) => li.classList.toggle("hot", doc != null && li.dataset.doc === doc));
  };
  $$("#columns li[data-doc], #river g.doc").forEach((el) => {
    el.addEventListener("mouseenter", () => setHot(el.dataset.doc));
    el.addEventListener("mouseleave", () => setHot(null));
  });
}

function agreementHtml(data) {
  const ag = data.agreement || {};
  const label = (n) => (state.methods.find((m) => m.name === n) || { label: n }).label;
  const pairs = (ag.pairs || []).map((p) => `<tr><td>${esc(label(p.a))}</td><td>${esc(label(p.b))}</td>
    <td class="num">${p.jaccard.toFixed(2)}</td><td class="num">${p.common.length}</td></tr>`).join("");
  const cons = (ag.consensus || []).map((c) => `<tr><td>${esc(c.doc_id)}</td><td>${esc(c.title)}</td>
    <td class="num">${c.methods.length}</td><td class="num">${c.avg_rank}</td></tr>`).join("");
  const recall = ag.ann_recall != null
    ? `<p>ANN recall against exact search: <b>${Math.round(ag.ann_recall * 100)}%</b> of the ENN results also came back from ANN.</p>` : "";
  return `<div class="agreement">
    <div><h3>How much the methods overlap</h3>${recall}
      ${pairs ? `<table><thead><tr><th>Method</th><th>Method</th><th>Jaccard</th><th>Shared</th></tr></thead><tbody>${pairs}</tbody></table>` : `<p class="hint">Run two or more methods to compare them.</p>`}</div>
    <div><h3>Articles most methods agree on</h3>
      ${cons ? `<table><thead><tr><th>Article</th><th>Title</th><th>Methods</th><th>Avg rank</th></tr></thead><tbody>${cons}</tbody></table>` : `<p class="hint">No article came back from more than one method.</p>`}</div>
  </div>`;
}

/* ----------------------------------------------------------------- SOP ---- */
async function startRun(ev) {
  ev && ev.preventDefault();
  const task = $("#task").value.trim();
  if (task.length < 3) { $("#run-out").innerHTML = `<p class="err">Describe the task in a few words.</p>`; return; }
  const btn = $("#start-btn");
  busy(btn, true);
  try {
    state.run = await api("/agent/runs", { method: "POST", body: { task, user_id: user(), memory_backend: $("#m-backend").value || null } });
    renderRun();
    listRuns();
  } catch (err) { showError($("#run-out"), err); }
  finally { busy(btn, false); }
}

async function runAction(path, body, btn) {
  busy(btn, true);
  try {
    state.run = await api(`/agent/runs/${state.run.id}${path}`, { method: "POST", body: body || {} });
    renderRun();
    if (path === "/finish") listRuns();
  } catch (err) { alertInline(err); }
  finally { busy(btn, false); }
}

function alertInline(err) {
  const box = $("#run-error");
  if (box) box.innerHTML = `<p class="err">${esc(err.message || err)}</p>`;
}

function renderRun() {
  const run = state.run;
  const out = $("#run-out");
  if (!run) { out.innerHTML = ""; return; }
  const finished = run.status === "completed" || run.status === "abandoned";
  const s = run.search || {};
  const cands = (s.candidates || []).map((c) => `<tr><td>${esc(c.doc_id)}</td><td>${esc(c.title)}</td>
    <td class="num">${Math.round(c.confidence * 100)}%</td>
    <td>${!finished && (!run.procedure || run.procedure.doc_id !== c.doc_id)
      ? `<button class="plain small" data-choose="${esc(c.doc_id)}">Use this</button>` : run.procedure && run.procedure.doc_id === c.doc_id ? "chosen" : ""}</td></tr>`).join("");

  const recalled = (run.recalled || []).map((h) => `<li><span class="mtype" style="--c:var(--t-${esc(h.record.type)})">${esc(h.record.type)}</span>
    ${esc(h.record.content)} <span class="hint">(${h.score.toFixed(2)}, ${esc(h.why)})</span></li>`).join("");

  const proc = run.procedure;
  const header = run.status === "no_match"
    ? `<div class="panel procedure"><h2>No procedure fits this task well enough</h2>
        <p class="reason">The best match was below the confidence threshold, so no checklist was started.
        Pick one of the candidates if it is right, or rephrase the task.</p></div>`
    : `<div class="panel procedure"><h2>Procedure <small>chosen by ${esc(proc.chosen_by === "user" ? "you" : "the agent")}</small></h2>
        <p class="title">${esc(proc.doc_id)} ${esc(proc.title)}</p>
        <p class="reason">${esc(proc.reason)}</p></div>`;

  const steps = (run.checklist || []).map((st) => stepHtml(st, finished)).join("");
  const writes = (run.memory_writes || []).map((w) => `<li><span class="op ${esc(w.op)}">${esc(w.op)}</span>
    ${esc(w.type)}: ${esc(w.label || "")} <span class="hint">${esc(w.reason)}</span></li>`).join("");

  out.innerHTML = `
    <div id="run-error"></div>
    ${header}
    <div class="panel recall"><h2>Recalled from memory <small>${esc(run.memory_backend || "memory off")}${run.recall_strategy ? `, ${esc(run.recall_strategy)}` : ""}</small></h2>
      ${recalled ? `<ul>${recalled}</ul>` : `<p class="hint">Nothing relevant yet. Finish a run and the agent will remember it.</p>`}
      ${run.recall_pipeline ? `<details class="pipe"><summary>Recall pipeline</summary>${pipelineHtml(run.recall_pipeline)}</details>` : ""}</div>
    <div class="panel cands"><h2>Candidates <small>${esc(s.method || "search")}${s.reranked ? " + rerank" : ""}</small></h2>
      <table><thead><tr><th>Article</th><th>Title</th><th>Match</th><th></th></tr></thead><tbody>${cands || `<tr><td colspan="4">No candidates.</td></tr>`}</tbody></table>
      ${s.pipeline && s.pipeline.length ? `<details class="pipe"><summary>Search pipeline</summary>${pipelineHtml(s.pipeline)}</details>` : ""}</div>
    ${steps ? `<div class="panel"><h2>Checklist <small>${esc(run.status.replace("_", " "))}</small></h2><ol class="checklist">${steps}</ol>
      ${finished ? "" : `<p><button class="primary" id="finish-btn">Finish run and save to memory</button></p>`}</div>` : ""}
    ${!steps && !finished ? `<div class="panel"><button class="plain" id="finish-btn">Close this run</button></div>` : ""}
    ${finished ? `<div class="panel"><h2>Summary <small>${esc(run.status)}</small></h2><p class="summary">${esc(run.summary)}</p>
      <h2>Saved to memory</h2>${writes ? `<ul class="writes">${writes}</ul>` : `<p class="hint">Nothing was saved.</p>`}</div>` : ""}`;

  $$("[data-choose]", out).forEach((b) => b.addEventListener("click", () => runAction("/choose", { doc_id: b.dataset.choose }, b)));
  $$("[data-confirm]", out).forEach((b) => b.addEventListener("click", () => {
    const li = b.closest("li");
    const note = $("input.note-in", li)?.value || null;
    runAction(`/steps/${encodeURIComponent(li.dataset.step)}`, { status: b.dataset.confirm, note }, b);
  }));
  const fin = $("#finish-btn");
  if (fin) fin.addEventListener("click", () => runAction("/finish", {}, fin));

  renderChat();
  renderTrace();
}

function stepHtml(st, finished) {
  const doer = st.actor === "agent" ? "Agent step, read only" : "Your step";
  const hints = st.hints && st.hints.length ? `<ul class="hints">${st.hints.map((h) => `<li>${esc(h)}</li>`).join("")}</ul>` : "";
  const guidance = st.guidance && st.guidance.length ? `<ul class="guidance">${st.guidance.map((g) => `<li>${esc(g)}</li>`).join("")}</ul>` : "";
  const actions = st.actor === "human" && st.status === "pending" && !finished
    ? `<div class="actions"><input type="text" class="note-in" placeholder="Note (optional): what happened?" aria-label="Note for ${esc(st.title)}" maxlength="2000">
        <button class="plain small" data-confirm="done">Done</button>
        <button class="plain small" data-confirm="failed">Failed</button>
        <button class="plain small" data-confirm="skipped">Skip</button></div>` : "";
  return `<li class="step" data-step="${esc(st.id)}" data-status="${esc(st.status)}" data-actor="${esc(st.actor)}">
    <div><div class="step-title">${esc(st.title)}</div><div class="who-does">${doer}${st.status !== "pending" ? `, ${esc(st.status)}` : ""}</div>
      ${st.command ? `<pre>${esc(st.command)}</pre>` : ""}
      ${st.explain ? `<p class="explain">${esc(st.explain)}</p>` : ""}
      ${st.output ? `<p class="output">${esc(st.output)}</p>` : ""}
      ${hints}${st.note ? `<p class="note">Your note: ${esc(st.note)}</p>` : ""}${guidance}${actions}</div></li>`;
}

function renderChat() {
  const run = state.run;
  $("#chat").hidden = !run;
  if (!run) return;
  const log = $("#chat-log");
  log.innerHTML = (run.messages || []).map((m) => `<p class="msg"><b>${m.role === "user" ? "You" : "Agent"}</b>${esc(m.content)}</p>`).join("")
    || `<p class="hint">Tell the agent anything it should know, like your cluster name. Questions ending in ? search the knowledge base.</p>`;
  log.scrollTop = log.scrollHeight;
  $("#chat-form input").disabled = run.status === "completed" || run.status === "abandoned";
}

function renderTrace() {
  const run = state.run;
  $("#trace-panel").hidden = !run;
  if (!run) return;
  const list = $("#trace");
  list.innerHTML = (run.trace || []).map((e) => {
    const detail = e.detail && Object.keys(e.detail).length
      ? `<details><summary>Details</summary>${pipelineHtml(e.detail)}</details>` : "";
    return `<li data-kind="${esc(e.kind)}"><span class="seq">${e.seq}</span>
      <div><div class="what">${esc(e.title)}</div><div class="kind">${esc(e.kind.replace("_", " "))}${e.ms != null ? `, ${e.ms} ms` : ""}</div>${detail}</div></li>`;
  }).join("");
  list.scrollTop = list.scrollHeight;
}

async function sendMessage(ev) {
  ev.preventDefault();
  const input = $("#chat-in");
  const content = input.value.trim();
  if (!content || !state.run) return;
  input.value = "";
  await runAction("/messages", { content }, $("#chat-form button"));
}

async function listRuns() {
  try {
    const data = await api(`/agent/runs?user_id=${encodeURIComponent(user())}`);
    const box = $("#runs-list");
    if (!data.runs.length) { box.textContent = "No runs yet."; return; }
    box.innerHTML = `<table><tbody>${data.runs.map((r) => `<tr><td><a href="#sop" data-run="${esc(r.id)}">${esc(r.task)}</a></td>
      <td>${esc(r.status.replace("_", " "))}</td></tr>`).join("")}</tbody></table>`;
    $$("[data-run]", box).forEach((a) => a.addEventListener("click", async (e) => {
      e.preventDefault();
      try { state.run = await api(`/agent/runs/${a.dataset.run}`); renderRun(); } catch (err) { showError($("#run-out"), err); }
    }));
  } catch (_) { /* the list is a convenience */ }
}

/* -------------------------------------------------------------- memory ---- */
function memoryItemHtml(rec, hit) {
  const parts = hit && hit.score_parts;
  let bar = "";
  if (parts) {
    // Each segment is the weighted contribution of one part, so the bar length is the score.
    const [a, b, c] = (state.health && state.health.memory_weights) || [0.6, 0.2, 0.2];
    const total = a + b + c || 1;
    const w = { rel: a / total, rec: b / total, imp: c / total };
    const seg = (v, k) => `<i class="${k}" style="width:${(v * w[k] * 100).toFixed(1)}%" title="${k} ${v.toFixed(2)}"></i>`;
    bar = `<div class="scorebar" aria-label="score ${hit.score}">${seg(parts.relevance, "rel")}${seg(parts.recency, "rec")}${seg(parts.importance, "imp")}</div>
      <div class="meta">Score ${hit.score.toFixed(3)}: relevance ${parts.relevance.toFixed(2)}, recency ${parts.recency.toFixed(2)},
        importance ${parts.importance.toFixed(2)}. ${esc(hit.why)}</div>`;
  }
  const when = new Date(rec.updated_at).toLocaleString();
  const versions = rec.history && rec.history.length ? `, ${rec.history.length + 1} versions` : "";
  const expires = rec.expires_at ? `, expires ${new Date(rec.expires_at).toLocaleString()}` : "";
  return `<li>
    <div><span class="mtype" style="--c:var(--t-${esc(rec.type)})">${esc(rec.type)}</span> <span class="label">${esc(rec.label || "")}</span></div>
    <div><button class="plain small" data-del="${esc(rec.id)}">Delete</button></div>
    <div class="content">${esc(rec.content)}</div>
    ${bar}
    <div class="meta">${esc(rec.visibility === "org" ? "Shared with the project" : "Private")}, updated ${esc(when)}${versions}${expires}</div>
  </li>`;
}

function memParams() {
  return { backend: $("#m-backend").value || "", type: $("#m-type").value || "" };
}

async function listMemory() {
  const out = $("#mem-out");
  const { backend, type } = memParams();
  try {
    const qs = new URLSearchParams({ user_id: user(), ...(backend && { backend }), ...(type && { type }) });
    const data = await api(`/memory?${qs}`);
    out.innerHTML = data.items.length
      ? `<ul class="memlist">${data.items.map((r) => memoryItemHtml(r)).join("")}</ul>`
      : `<p class="empty">No memories for ${esc(user())} yet. Finish an SOP run, or add one by hand below.</p>`;
    wireDeletes();
  } catch (err) { showError(out, err); }
}

async function recallMemory(ev) {
  ev && ev.preventDefault();
  const out = $("#mem-out");
  const query = $("#m-q").value.trim();
  if (!query) return listMemory();
  const { backend, type } = memParams();
  try {
    const data = await api("/memory/search", { method: "POST", body: { query, user_id: user(), backend: backend || null, types: type ? [type] : null } });
    const [wa, wb, wc] = (state.health && state.health.memory_weights) || [0.6, 0.2, 0.2];
    out.innerHTML = `<div class="legend"><span><i style="background:var(--signal)"></i>relevance × ${wa}</span>
        <span><i style="background:var(--m-hybrid_rrf)"></i>recency × ${wb}</span><span><i style="background:var(--m-fulltext)"></i>importance × ${wc}</span>
        <span>${esc(data.backend)}: ${esc(data.strategy)}, ${data.ms} ms</span></div>
      ${(data.warnings || []).map((w) => `<p class="hint">${esc(w)}</p>`).join("")}
      ${data.hits.length ? `<ul class="memlist">${data.hits.map((h) => memoryItemHtml(h.record, h)).join("")}</ul>` : `<p class="empty">Nothing recalled for that.</p>`}
      ${data.pipeline ? `<details class="panel pipe"><summary>Recall pipeline</summary>${pipelineHtml(data.pipeline)}</details>` : ""}`;
    wireDeletes();
  } catch (err) { showError(out, err); }
}

function wireDeletes() {
  $$("[data-del]").forEach((b) => b.addEventListener("click", async () => {
    const { backend } = memParams();
    try {
      await api(`/memory/${encodeURIComponent(b.dataset.del)}?${new URLSearchParams({ user_id: user(), ...(backend && { backend }) })}`, { method: "DELETE" });
      b.closest("li").remove();
    } catch (err) { b.replaceWith(Object.assign(document.createElement("span"), { className: "err", textContent: err.message })); }
  }));
}

async function setupMemory() {
  const btn = $("#m-setup");
  busy(btn, true);
  try {
    const data = await api(`/memory/setup?${new URLSearchParams({ backend: $("#m-backend").value })}`, { method: "POST" });
    $("#m-backend-info").innerHTML = `<ul>${data.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>`;
  } catch (err) { showError($("#m-backend-info"), err); }
  finally { busy(btn, false); }
}

async function addMemory(ev) {
  ev.preventDefault();
  try {
    const out = await api("/memory", { method: "POST", body: {
      type: $("#a-type").value, label: $("#a-label").value || null, content: $("#a-content").value,
      importance: Number($("#a-imp").value), visibility: $("#a-vis").value, user_id: user(),
      backend: $("#m-backend").value || null,
    } });
    $("#m-backend-info").innerHTML = `<p><span class="op ${esc(out.op)}">${esc(out.op)}</span> ${esc(out.reason)}</p>`;
    $("#a-content").value = "";
    listMemory();
  } catch (err) { showError($("#m-backend-info"), err); }
}

async function loadBackends() {
  try {
    const data = await api("/memory/backends");
    const sel = $("#m-backend");
    sel.innerHTML = data.backends.map((b) => `<option value="${esc(b.name)}" ${b.default ? "selected" : ""}>${esc(b.name)}${b.default ? " (default)" : ""}</option>`).join("");
    const describe = () => {
      const b = data.backends.find((x) => x.name === sel.value) || {};
      const notes = [];
      if (b.error) notes.push(`Unavailable: ${b.error}`);
      if (b.persistent === false) notes.push("Kept in the app process; cleared on restart.");
      if (b.indexes) notes.push("Indexes: " + (b.indexes.length ? b.indexes.map((i) => `${i.name} ${i.status}`).join(", ") : "none yet, press Set up memory indexes"));
      if (b.note) notes.push(b.note);
      if (b.capabilities && !b.capabilities.delete) notes.push("This backend does not support delete.");
      $("#m-backend-info").textContent = notes.join(" ");
    };
    sel.addEventListener("change", () => { describe(); listMemory(); });
    describe();
  } catch (_) { /* shown on first memory call */ }
}

/* ---------------------------------------------------------------- init ---- */
async function init() {
  try { const saved = localStorage.getItem("kblab.user"); if (saved) $("#user").value = saved; } catch (_) { /* storage off */ }
  $("#user").addEventListener("change", () => {
    try { localStorage.setItem("kblab.user", user()); } catch (_) { /* storage off */ }
    listRuns();
    if (!$("#tab-memory").hidden) listMemory();
  });
  $$("nav.tabs button").forEach((b) => b.addEventListener("click", () => selectTab(b.id.slice(2))));
  $("#search-form").addEventListener("submit", compare);
  $("#task-form").addEventListener("submit", startRun);
  $("#chat-form").addEventListener("submit", sendMessage);
  $$(".examples [data-task]").forEach((b) => b.addEventListener("click", () => { $("#task").value = b.dataset.task; startRun(); }));
  $("#m-search-form").addEventListener("submit", recallMemory);
  $("#m-list").addEventListener("click", () => { $("#m-q").value = ""; listMemory(); });
  $("#m-type").addEventListener("change", () => ($("#m-q").value ? recallMemory() : listMemory()));
  $("#m-setup").addEventListener("click", setupMemory);
  $("#m-add-form").addEventListener("submit", addMemory);
  window.addEventListener("resize", () => { if (state.lastCompare && $("#river-svg")) renderCompare(state.lastCompare, state.lastOrder); });

  try {
    const [health, methods, facets] = await Promise.all([api("/health"), api("/search/methods"), api("/facets")]);
    state.health = health;
    state.methods = methods.methods;
    for (const [id, values] of [["#o-cat", facets.category], ["#o-dom", facets.domain]]) {
      $(id).insertAdjacentHTML("beforeend", values.map((v) => `<option>${esc(v)}</option>`).join(""));
    }
    $("#o-model").value = health.index.query_model;
    $("#o-rmodel").value = health.index.rerank_model;
    renderStatus();
    renderChips();
    api("/capabilities").then((caps) => { state.caps = caps; renderStatus(); renderChips(); }).catch(() => {});
  } catch (err) {
    $("#status").innerHTML = `<span class="err">Cannot reach the API: ${esc(err.message)}</span>`;
  }
  loadBackends();
  const tab = (location.hash || "").slice(1);
  if (["search", "sop", "memory"].includes(tab)) selectTab(tab);
}

init();
