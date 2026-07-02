/* GLM 技术方案智能生成 POC —— 无框架前端 */
const $ = (sel) => document.querySelector(sel);
let taskId = null;
let outlineData = null;        // 当前任务大纲（面板2编辑的对象）
let chaptersLocal = {};        // no -> {title, content}
let currentSection = null;     // 面板3当前查看的节
let kbTimer = null;

/* ---------- 基础工具 ---------- */
async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = r.status;
    try { msg = (await r.json()).detail || msg; } catch (e) {}
    throw new Error(msg);
  }
  return r.json();
}

/* SSE 消费：POST 返回 text/event-stream，逐事件回调 */
async function sse(path, onEvent) {
  const resp = await fetch(path, { method: "POST" });
  if (!resp.ok) throw new Error("请求失败 " + resp.status);
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 2);
      if (line.startsWith("data:")) onEvent(JSON.parse(line.slice(5)));
    }
  }
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.style.display = "block";
  setTimeout(() => { t.style.display = "none"; }, 3200);
}

const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/* 迷你 Markdown 渲染（标题/列表/表格/加粗），不依赖外网 CDN */
function mdRender(md) {
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
  let html = "", inList = false, rows = [];
  const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };
  const flushTable = () => {
    if (!rows.length) return;
    html += "<table>" + rows.map((r, i) =>
      "<tr>" + r.map(c => i === 0 ? `<th>${inline(c)}</th>` : `<td>${inline(c)}</td>`).join("") + "</tr>"
    ).join("") + "</table>";
    rows = [];
  };
  for (const raw of String(md).split("\n")) {
    const s = raw.trim();
    if (s.startsWith("|")) {
      const cells = s.replace(/^\|/, "").replace(/\|$/, "").split("|").map(c => c.trim());
      if (!cells.every(c => /^[-: ]*$/.test(c))) rows.push(cells);
      continue;
    }
    flushTable();
    if (!s) { closeList(); continue; }
    if (/^#{1,6}\s*/.test(s)) { closeList(); html += `<h4>${inline(s.replace(/^#+\s*/, ""))}</h4>`; }
    else if (/^[-*]\s+/.test(s)) { if (!inList) { html += "<ul>"; inList = true; } html += `<li>${inline(s.replace(/^[-*]\s+/, ""))}</li>`; }
    else { closeList(); html += `<p>${inline(s)}</p>`; }
  }
  closeList(); flushTable();
  return html;
}

/* ---------- 视图切换 ---------- */
function showView(name) {
  $("#view-gen").style.display = name === "gen" ? "" : "none";
  $("#view-kb").style.display = name === "kb" ? "" : "none";
  $("#nav-gen").classList.toggle("active", name === "gen");
  $("#nav-kb").classList.toggle("active", name === "kb");
  if (name === "kb") refreshKb();
}

function gotoPanel(n) {
  for (let i = 1; i <= 4; i++) $(`#panel-${i}`).style.display = i === n ? "" : "none";
  document.querySelectorAll(".step").forEach(el => {
    const s = +el.dataset.step;
    el.classList.toggle("active", s === n);
    el.classList.toggle("done", s < n);
  });
}

/* ---------- 历史任务 ---------- */
const STAGE_NAMES = { created: "待解析", parsing: "解析中", parsed: "已解析", outlining: "规划中",
  outlined: "大纲待确认", outline_confirmed: "待生成", generating: "生成中", generated: "已生成",
  reviewing: "校验中", reviewed: "已校验", exported: "已导出" };

async function refreshHistory() {
  try {
    const list = await api("/api/tasks");
    $("#history-list").innerHTML = list.map(t =>
      `<div class="history-item" onclick="loadTask('${t.id}')">${esc(t.project_name || t.id)}<span class="st">${STAGE_NAMES[t.stage] || t.stage}</span></div>`
    ).join("");
  } catch (e) { /* 忽略 */ }
}

async function loadTask(id) {
  const t = await api("/api/tasks/" + id);
  taskId = t.id;
  outlineData = t.outline;
  chaptersLocal = {};
  Object.entries(t.chapters || {}).forEach(([no, c]) => { chaptersLocal[no] = c; });
  showView("gen");
  if (t.requirements) { renderRequirements(t.requirements); $("#p1-work").style.display = "flex"; $("#p1-result-card").style.display = ""; $("#p1-next").style.display = ""; $("#p1-live").style.display = "none"; }
  if (t.retrieved && t.retrieved.length) renderRefs("#p2-refs", t.retrieved);
  if (t.outline) { renderOutlineEditor(); $("#p2-confirm").style.display = ""; $("#p2-live").style.display = "none"; }
  const stage = t.stage;
  if (["created", "parsing"].includes(stage)) gotoPanel(1);
  else if (["parsed", "outlining", "outlined"].includes(stage)) gotoPanel(stage === "parsed" ? 2 : 2), t.outline || startOutlineIfNeeded(stage);
  else if (["outline_confirmed", "generating", "generated"].includes(stage)) {
    gotoPanel(3); buildGenNav(); renderTerms(t.terms || {}); updateProgress();
    if (stage === "generated") $("#p3-next").style.display = "";
    const first = Object.keys(chaptersLocal)[0];
    if (first) showSection(first);
    if (stage !== "generated") toast("该任务生成未完成，点击导航可查看已完成章节；可重新进入生成");
  } else if (["reviewing", "reviewed", "exported"].includes(stage)) {
    gotoPanel(4);
    if (t.review) renderReview(t.review);
    $("#p4-export").style.display = "";
  }
  refreshHistory();
}

function startOutlineIfNeeded(stage) { if (stage === "parsed") { /* 等用户点下一步 */ } }

/* ---------- 面板1：需求解析 ---------- */
async function startParse() {
  const f = $("#p1-file").files[0];
  if (!f) { toast("请先选择招标/需求文件"); return; }
  $("#p1-start").disabled = true;
  try {
    const fd = new FormData();
    fd.append("file", f);
    const t = await api("/api/tasks", { method: "POST", body: fd });
    taskId = t.id;
    $("#p1-work").style.display = "flex";
    $("#p1-live").style.display = "";
    const log = $("#p1-log");
    log.textContent = "";
    await sse(`/api/tasks/${taskId}/parse`, ev => {
      if (ev.type === "delta") { log.textContent += ev.text; log.scrollTop = log.scrollHeight; }
      else if (ev.type === "done") {
        $("#p1-live").style.display = "none";
        renderRequirements(ev.requirements);
        $("#p1-result-card").style.display = "";
        $("#p1-next").style.display = "";
        toast("需求解析完成");
        refreshHistory();
      } else if (ev.type === "error") { toast("解析失败：" + ev.message); }
    });
  } catch (e) { toast("出错：" + e.message); }
  $("#p1-start").disabled = false;
}

function renderRequirements(req) {
  const tbl = (rows, heads) =>
    `<table class="table"><tr>${heads.map(h => `<th>${h}</th>`).join("")}</tr>` +
    rows.map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join("")}</tr>`).join("") + "</table>";
  let html = "";
  html += `<div class="block"><h4>项目名称</h4><p style="font-size:14px">${esc(req.project_name)}</p></div>`;
  if ((req.tech_params || []).length)
    html += `<div class="block"><h4>技术参数要求（${req.tech_params.length}）</h4>` +
      tbl(req.tech_params.map(p => [p.item, p.requirement]), ["参数项", "要求"]) + "</div>";
  if ((req.milestones || []).length)
    html += `<div class="block"><h4>工期里程碑</h4>` +
      tbl(req.milestones.map(m => [m.name, m.deadline]), ["节点", "时间要求"]) + "</div>";
  if ((req.qualifications || []).length)
    html += `<div class="block"><h4>资质要求</h4><ul class="plain">` +
      req.qualifications.map(q => `<li>${esc(q)}</li>`).join("") + "</ul></div>";
  if ((req.scoring || []).length)
    html += `<div class="block"><h4>评分标准</h4>` +
      tbl(req.scoring.map(s => [s.item, s.weight, s.note]), ["评分项", "分值", "响应要点"]) + "</div>";
  if ((req.risks || []).length)
    html += `<div class="block"><h4>⚠ 隐含要求与风险预警（${req.risks.length}）</h4>` +
      req.risks.map(r => `<div class="risk-card"><b>${esc(r.text)}</b><div class="why">${esc(r.why)}</div></div>`).join("") + "</div>";
  $("#p1-result").innerHTML = html;
}

/* ---------- 面板2：大纲规划 ---------- */
async function startOutline() {
  gotoPanel(2);
  $("#p2-live").style.display = "";
  const log = $("#p2-log");
  log.textContent = "";
  try {
    await sse(`/api/tasks/${taskId}/outline`, ev => {
      if (ev.type === "refs") {
        renderRefs("#p2-refs", ev.refs);
        if (ev.warning) toast(ev.warning);
      } else if (ev.type === "delta") { log.textContent += ev.text; log.scrollTop = log.scrollHeight; }
      else if (ev.type === "done") {
        $("#p2-live").style.display = "none";
        outlineData = ev.outline;
        renderOutlineEditor();
        $("#p2-confirm").style.display = "";
        toast("大纲已生成，可编辑后确认");
        refreshHistory();
      } else if (ev.type === "error") { toast("大纲生成失败：" + ev.message); }
    });
  } catch (e) { toast("出错：" + e.message); }
}

function renderRefs(sel, refs) {
  $(sel).innerHTML = (refs || []).length ? refs.map(r =>
    `<div class="ref-card"><div class="src"><span>📄 ${esc(r.doc_name || "知识库")}</span><span>相似度 ${(r.score ?? 0).toFixed ? (r.score).toFixed(2) : r.score}</span></div><div class="txt">${esc(r.text)}</div></div>`
  ).join("") : `<p class="hint">未检索到参考（知识库为空或不可用），将直接基于需求生成</p>`;
}

function renderOutlineEditor() {
  const box = $("#p2-outline");
  box.innerHTML = "";
  (outlineData.chapters || []).forEach((ch, ci) => {
    const chDiv = document.createElement("div");
    chDiv.className = "ol-chapter";
    chDiv.innerHTML = `<div class="ol-chapter-head"><span class="no">${esc(ch.no)}</span>
      <input value="${esc(ch.title)}" onchange="outlineData.chapters[${ci}].title=this.value">
      <button class="btn sm danger" onclick="delChapter(${ci})">删章</button></div>`;
    (ch.sections || []).forEach((sec, si) => {
      const row = document.createElement("div");
      row.className = "ol-sec";
      row.innerHTML = `<span class="no">${esc(sec.no)}</span>
        <input value="${esc(sec.title)}" onchange="outlineData.chapters[${ci}].sections[${si}].title=this.value">
        <span class="points" title="${esc(sec.points || "")}">${esc(sec.points || "")}</span>
        <button class="btn sm danger" onclick="delSection(${ci},${si})">删</button>`;
      chDiv.appendChild(row);
    });
    const add = document.createElement("button");
    add.className = "btn sm ol-add";
    add.textContent = "+ 新增节";
    add.onclick = () => addSection(ci);
    chDiv.appendChild(add);
    box.appendChild(chDiv);
  });
}

function delChapter(ci) { outlineData.chapters.splice(ci, 1); renderOutlineEditor(); }
function delSection(ci, si) { outlineData.chapters[ci].sections.splice(si, 1); renderOutlineEditor(); }
function addSection(ci) {
  const ch = outlineData.chapters[ci];
  ch.sections.push({ no: `${ch.no}.${ch.sections.length + 1}`, title: "新增节（请修改标题）", points: "" });
  renderOutlineEditor();
}

async function confirmOutline() {
  await api(`/api/tasks/${taskId}/outline`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(outlineData),
  });
  gotoPanel(3);
  startGenerate();
}

/* ---------- 面板3：分段生成 ---------- */
function allSections() {
  const out = [];
  (outlineData.chapters || []).forEach(ch => (ch.sections || []).forEach(sec => out.push({ ch, sec })));
  return out;
}

function buildGenNav() {
  const nav = $("#p3-nav");
  nav.innerHTML = "";
  (outlineData.chapters || []).forEach(ch => {
    const chDiv = document.createElement("div");
    chDiv.className = "nav-item ch";
    chDiv.textContent = `${ch.no} ${ch.title}`;
    nav.appendChild(chDiv);
    (ch.sections || []).forEach(sec => {
      const item = document.createElement("div");
      item.className = "nav-item";
      item.id = "nav-" + sec.no.replace(/\./g, "-");
      item.innerHTML = `<span class="mark"></span>${sec.no} ${esc(sec.title)}`;
      item.onclick = () => showSection(sec.no);
      nav.appendChild(item);
    });
  });
  Object.keys(chaptersLocal).forEach(no => markSection(no, "done"));
}

function markSection(no, st) {
  const el = $("#nav-" + no.replace(/\./g, "-"));
  if (!el) return;
  const m = el.querySelector(".mark");
  if (st === "done") m.innerHTML = `<span class="tick">✓</span>`;
  else if (st === "doing") m.innerHTML = `<span class="spin">●</span>`;
}

function updateProgress() {
  const total = allSections().length;
  const done = Object.keys(chaptersLocal).length;
  $("#p3-progress").style.setProperty("--p", total ? (done / total * 100) + "%" : "0%");
  $("#p3-progress-text").textContent = `${done} / ${total}`;
}

function showSection(no, streamingText) {
  currentSection = no;
  document.querySelectorAll("#p3-nav .nav-item").forEach(e => e.classList.remove("cur"));
  const el = $("#nav-" + no.replace(/\./g, "-"));
  if (el) el.classList.add("cur");
  const info = chaptersLocal[no];
  const title = allSections().find(x => x.sec.no === no);
  $("#p3-current-title").textContent = `${no} ${title ? title.sec.title : ""}`;
  if (streamingText !== undefined) {
    $("#p3-content").innerHTML = mdRender(streamingText) + '<span class="cursor"></span>';
    $("#p3-content").scrollTop = $("#p3-content").scrollHeight;
  } else {
    $("#p3-content").innerHTML = info ? mdRender(info.content) : '<p class="hint">本节尚未生成</p>';
    renderRefs("#p3-refs", info ? info.refs : []);
  }
}

function renderTerms(terms) {
  $("#p3-terms").innerHTML = Object.keys(terms || {}).length
    ? Object.entries(terms).map(([k, v]) => `<div class="term"><b>${esc(k)}</b> → ${esc(v)}</div>`).join("")
    : `<p class="hint">暂无术语</p>`;
}

async function startGenerate() {
  buildGenNav();
  updateProgress();
  let streamBuf = "";
  const termsAll = {};
  try {
    await sse(`/api/tasks/${taskId}/generate`, ev => {
      if (ev.type === "section_start") {
        streamBuf = "";
        markSection(ev.no, "doing");
        renderRefs("#p3-refs", ev.refs);
        showSection(ev.no, "");
      } else if (ev.type === "delta") {
        streamBuf += ev.text;
        if (currentSection === ev.no) showSection(ev.no, streamBuf);
      } else if (ev.type === "section_done") {
        if (!chaptersLocal[ev.no]) chaptersLocal[ev.no] = { content: streamBuf, refs: [] };
        if (streamBuf) chaptersLocal[ev.no].content = streamBuf || chaptersLocal[ev.no].content;
        Object.assign(termsAll, ev.terms || {});
        renderTerms(termsAll);
        markSection(ev.no, "done");
        updateProgress();
        showSection(ev.no);
      } else if (ev.type === "done") {
        $("#p3-next").style.display = "";
        toast("全部章节生成完成");
        refreshHistory();
      } else if (ev.type === "error") { toast("生成中断：" + ev.message); }
    });
  } catch (e) { toast("出错：" + e.message); }
  // 生成结束后从服务端拉一次权威状态（含每节 refs 与完整术语表）
  const t = await api("/api/tasks/" + taskId);
  chaptersLocal = t.chapters || chaptersLocal;
  renderTerms(t.terms || termsAll);
  updateProgress();
}

/* ---------- 面板4：整合校验 ---------- */
async function startReview() {
  $("#p4-start").disabled = true;
  $("#p4-start").textContent = "校验中…";
  try {
    const r = await api(`/api/tasks/${taskId}/review`, { method: "POST" });
    renderReview(r);
    $("#p4-export").style.display = "";
    refreshHistory();
  } catch (e) { toast("校验失败：" + e.message); }
  $("#p4-start").disabled = false;
  $("#p4-start").textContent = "重新校验";
}

function renderReview(r) {
  const sm = $("#p4-summary");
  sm.style.display = "block";
  sm.textContent = r.summary || "校验完成";
  const issues = r.issues || [];
  $("#p4-issues").innerHTML = issues.length
    ? `<table class="table"><tr><th>类型</th><th>章节</th><th>问题</th><th>建议</th></tr>` +
      issues.map(i =>
        `<tr><td><span class="issue-type ${esc(i.type)}">${esc(i.type)}</span></td>` +
        `<td><span class="link" onclick="jumpTo('${esc(i.chapter)}')">${esc(i.chapter)}</span></td>` +
        `<td>${esc(i.desc)}</td><td>${esc(i.suggestion)}</td></tr>`).join("") + "</table>"
    : `<p class="hint" style="font-size:14px">✅ 未发现问题，可直接导出</p>`;
}

function jumpTo(no) {
  gotoPanel(3);
  if (no && no !== "undefined") showSection(no);
}

function exportDocx() { window.open(`/api/tasks/${taskId}/export`); toast("已开始下载 Word 文档"); }

/* ---------- 知识库 ---------- */
const STAT = { 1: ["处理中", "doing"], 2: ["成功", "ok"], 3: ["失败", "fail"] };

async function refreshKb() {
  try {
    const info = await api("/api/kb");
    $("#kb-meta").textContent = `知识库 ID：${info.kb_id} · 共 ${info.docs.length} 份文档`;
    $("#kb-tbody").innerHTML = info.docs.map(d => {
      // 智谱侧 embedding_stat=2 也可能带 failInfo，以 fail 为准
      const [txt, cls] = d.fail ? ["失败", "fail"] : (STAT[d.embedding_stat] || [`状态${d.embedding_stat}`, "doing"]);
      return `<tr><td>${esc(d.name)}</td>
        <td><span class="badge ${cls}">${txt}</span>${d.fail ? ` <span class="hint-inline">${esc(d.fail)}</span>` : ""}</td>
        <td><button class="btn sm danger" onclick="kbDelete('${d.id}')">删除</button></td></tr>`;
    }).join("") || `<tr><td colspan="3" class="hint">暂无文档，请上传历史技术方案</td></tr>`;
    clearTimeout(kbTimer);
    if (info.docs.some(d => d.embedding_stat === 1))
      kbTimer = setTimeout(refreshKb, 5000);
  } catch (e) { toast("知识库加载失败：" + e.message); }
}

async function kbUpload() {
  const f = $("#kb-file").files[0];
  if (!f) { toast("请先选择文件"); return; }
  const btn = $("#kb-upload-btn");
  btn.disabled = true; btn.textContent = "上传中…";
  try {
    const fd = new FormData();
    fd.append("file", f);
    await api("/api/kb/upload", { method: "POST", body: fd });
    toast("上传成功，向量化处理中");
    $("#kb-file").value = "";
    refreshKb();
  } catch (e) { toast("上传失败：" + e.message); }
  btn.disabled = false; btn.textContent = "上传到知识库";
}

async function kbDelete(id) {
  await api("/api/kb/docs/" + id, { method: "DELETE" });
  toast("已删除");
  refreshKb();
}

/* ---------- 提示词弹层 ---------- */
let promptsCache = {};
async function openPrompts() {
  if (!taskId) { toast("请先上传招标文件创建任务，再自定义提示词"); return; }
  promptsCache = await api(`/api/tasks/${taskId}/prompts`);
  $("#modal-prompts").style.display = "flex";
  loadPromptToEditor();
}
function loadPromptToEditor() { $("#prompt-editor").value = promptsCache[$("#prompt-name").value] || ""; }
function closePrompts() { $("#modal-prompts").style.display = "none"; }
async function savePrompt() {
  const name = $("#prompt-name").value;
  await api(`/api/tasks/${taskId}/prompts`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, content: $("#prompt-editor").value }),
  });
  promptsCache[name] = $("#prompt-editor").value;
  toast("提示词已保存（仅当前任务生效）");
}
async function resetPrompt() {
  const name = $("#prompt-name").value;
  await api(`/api/tasks/${taskId}/prompts`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, content: "" }),
  });
  promptsCache = await api(`/api/tasks/${taskId}/prompts`);
  loadPromptToEditor();
  toast("已恢复默认提示词");
}

/* ---------- 启动 ---------- */
gotoPanel(1);
refreshHistory();
