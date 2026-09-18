"use strict";

const labels = {
  overview: ["业务总览", "把市场信号，变成可验证的商机。"],
  discovery: ["情报与商机", "先理解客户问题，再建立商业假设。"],
  resources: ["资源匹配", "找到合适资源，逐项核实交付能力。"],
  marketing: ["营销内容", "让内容制作围绕客户价值展开。"],
  crm: ["客户与沟通", "把客户信息与沟通线索连接起来。"],
  delivery: ["交付与 ESG", "把商业承诺转为可验收的任务。"],
  audit: ["过程审计", "保留操作依据，让过程可追溯。"]
};
const names = {
  brokerage: "信息与资源中介", product: "硬件或产品销售", software: "软件开发", hardware: "硬件设计与验证", contract: "商业合同", esg: "ESG 证据与报告",
  draft: "待评审草稿", accepted: "内部评审通过", rejected: "评审退回", unverified: "待核实", done: "已记录完成", blocked: "存在阻塞", open: "待执行", pending: "待执行",
  inbound: "客户来询记录", outbound: "已发生的跟进记录", internal: "内部备注", estimate: "估算数据", confirmed_inputs: "输入已确认", incomplete: "成本不完整",
  capture_signal: "录入情报", propose_opportunity: "建立商机", add_resource: "加入资源池", draft_content: "保存内容草稿", review_content: "记录内部评审", add_contact: "保存客户", record_note: "记录沟通", create_task: "创建交付任务", record_task_result: "记录交付结果",
  CONTENT_REVIEW_PENDING: "内容尚未完成评审", MARKET_PROFILE_PENDING: "目标市场尚未确认", TECHNICAL_REVIEW_FAILED: "技术验证未通过", NO_QUALIFIED_RESOURCE: "缺少已核实资源", PROFIT_NOT_VALIDATED: "利润假设尚未验证", END_STATE_NOT_COMPARABLE: "期末储能状态不可比", INCOMPLETE_BILLING_PERIOD: "计费周期不完整",
  resource_verified: "资源验证阶段", opportunity: "商机阶段", model_validated: "模式验证阶段", campaign_recorded: "营销记录阶段", quoted: "报价阶段", contracted: "合同阶段", delivered: "交付阶段", reconciled: "对账阶段", reviewed: "复盘阶段"
};
let dashboard = null;
let selectedCase = "";
let refreshSequence = 0;
let caseSequence = 0;
let selectedTab = "overview";

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
function translated(value) { return names[value] || value || "—"; }
function badge(text, kind = "neutral") { return element("span", text, `badge ${kind}`); }
function dateText(value) {
  if (!value) return "时间未提供";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("zh-CN", { hour12: false });
}
function money(value) {
  if (value === null || value === undefined || value === "") return "待核实";
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("zh-CN", { maximumFractionDigits: 2 }) : String(value);
}
function showFeedback(message, error = false) {
  const box = document.getElementById("feedback");
  box.textContent = message;
  box.classList.toggle("error", error);
  box.setAttribute("role", error ? "alert" : "status");
  box.hidden = false;
}
async function api(path, options = {}) {
  const response = await fetch(path, { credentials: "same-origin", ...options });
  let data;
  try { data = await response.json(); } catch { throw new Error("服务返回了无法读取的结果，请检查本地服务日志。"); }
  if (!response.ok) throw new Error(data.error || `请求失败（${response.status}）`);
  return data;
}
function activateTab(id, focus = false) {
  if (!labels[id]) id = "overview";
  selectedTab = id;
  document.querySelectorAll(".tab-panel").forEach(panel => { panel.hidden = panel.id !== id; });
  document.querySelectorAll("[data-tab]").forEach(button => {
    const active = button.dataset.tab === id;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
  });
  document.getElementById("breadcrumb-current").textContent = labels[id][0];
  document.getElementById("page-title").textContent = labels[id][1];
  document.title = `${labels[id][0]} · SmartBusiness`;
  history.replaceState(null, "", `#${id}`);
  if (focus) document.getElementById(`tab-${id}`).focus();
}
function setStatus(id, message, active) {
  const container = document.getElementById(id);
  container.replaceChildren(element("i", null, `dot ${active ? "teal" : "amber"}`), document.createTextNode(message));
}
function emptyMessage(container, message) { container.replaceChildren(element("p", message, "empty")); }
function records(containerId, items, blank, renderer) {
  const container = document.getElementById(containerId);
  if (!items.length) return emptyMessage(container, blank);
  const list = element("div", undefined, "records");
  [...items].reverse().forEach(item => list.append(renderer(item)));
  container.replaceChildren(list);
}
function recordCard(title, item, status, tone) {
  const card = element("article", undefined, "record");
  const header = element("div", undefined, "record-header");
  header.append(element("h4", title));
  if (status) header.append(badge(status, tone));
  card.append(header, element("div", `${item.id || ""} · ${dateText(item.created_at)}`, "record-meta"));
  return card;
}
function paragraph(card, label, value) {
  if (value === undefined || value === null || value === "") return;
  card.append(element("span", label, "record-label"), element("p", value));
}
function safeLink(card, url) {
  if (!url) return;
  try {
    const parsed = new URL(url);
    if (!["https:", "http:"].includes(parsed.protocol)) throw new Error("unsupported");
    const line = element("p");
    const link = element("a", url);
    link.href = parsed.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    line.append(link);
    card.append(line);
  } catch { paragraph(card, "来源引用", url); }
}
function optionsFor(name) {
  const items = dashboard[name] || [];
  return items.map(item => ({ id: item.id, title: item.title || item.name || item.value_proposition || item.id }));
}
function updateSelects() {
  document.querySelectorAll("select[data-options]").forEach(select => {
    const previous = select.value;
    const options = optionsFor(select.dataset.options);
    const placeholder = element("option", options.length ? "请选择…" : "暂无记录，请先完成上一步");
    placeholder.value = "";
    select.replaceChildren(placeholder);
    options.forEach(item => { const option = element("option", `${item.id} · ${item.title}`); option.value = item.id; select.append(option); });
    if (options.some(item => item.id === previous)) select.value = previous;
    if (select.dataset.options === "cases" && !select.value && options.some(item => item.id === selectedCase)) select.value = selectedCase;
    select.disabled = !options.length;
    const form = select.closest("form");
    if (form) form.querySelectorAll('button[type="submit"]').forEach(button => { button.disabled = !options.length; });
  });
}
function renderMetrics() {
  const definitions = [
    ["已录入情报", dashboard.signals.length, "⌕", "为市场判断保留证据"],
    ["商机假设", dashboard.opportunities.length, "◇", "客户价值与变现方式"],
    ["候选资源", dashboard.resources.length, "◎", "待逐项核实交付能力"],
    ["待推进任务", dashboard.tasks.filter(task => task.status !== "done" && task.outcome !== "done").length, "▤", "软件 · 硬件 · 合同 · ESG"]
  ];
  const container = document.getElementById("metrics");
  container.replaceChildren();
  definitions.forEach(([label, count, symbol, note]) => {
    const card = element("article", undefined, "metric");
    const top = element("div", undefined, "metric-top");
    top.append(element("span", label), element("span", symbol, "metric-symbol"));
    card.append(top, element("strong", count, "metric-value"), element("span", note, "metric-note"));
    container.append(card);
  });
}
function renderCase(caseData) {
  const container = document.getElementById("case-detail");
  if (!caseData) return emptyMessage(container, "暂无可用案例，请检查本地案例文件。");
  const finance = caseData.finance || {};
  const technical = caseData.technical || {};
  const titleRow = element("div", undefined, "case-title-row");
  const title = element("div");
  title.append(element("h3", caseData.title), element("div", `${caseData.id} · ${caseData.market || "市场待确定"}`, "case-meta"));
  titleRow.append(title, badge(translated(caseData.cycle_stage), "neutral"));
  const financial = element("div", undefined, "finance-grid");
  [["净收入", finance.net_revenue], ["毛利润", finance.gross_profit], ["贡献利润", finance.contribution_profit]].forEach(([label, value]) => {
    const cell = element("div", undefined, "finance-cell");
    cell.append(element("span", label), element("strong", money(value)), element("small", `${finance.currency || ""} · ${translated(finance.status)}`));
    financial.append(cell);
  });
  const blockers = caseData.blockers || [];
  const blockerTitle = element("div", undefined, "blocker-heading");
  blockerTitle.append(element("span", "下一步需要解决"), element("span", `${blockers.length} 项`, "muted"));
  const blockerList = element("ul", undefined, "blocker-list");
  blockers.forEach(reason => { const item = element("li", translated(reason)); item.title = reason; blockerList.append(item); });
  if (!blockers.length) blockerList.append(element("li", "当前合成检查未列出阻塞；仍需真实业务验证"));
  const techLine = element("div", undefined, "technical-line");
  techLine.append(element("span", "合成技术输入检查"), badge(technical.feasible === true ? "输入满足模型约束" : technical.feasible === false ? "存在技术问题" : "查看模型结果", technical.feasible === true ? "success" : "warning"));
  const details = element("details", undefined, "technical-details");
  details.append(element("summary", "展开领域计算与验证结果"), element("pre", JSON.stringify(technical, null, 2), "code-block"));
  container.replaceChildren(titleRow, financial, element("p", finance.scope || "经营估算口径，非净利润；不代表真实交易。", "financial-scope"), blockerTitle, blockerList, techLine, details);
}
function renderCaseTable() {
  const table = element("table");
  const head = element("thead");
  const row = element("tr");
  ["行业案例", "币种", "估算净收入", "估算贡献利润", "当前检查"].forEach(name => { const th = element("th", name); th.scope = "col"; row.append(th); });
  head.append(row);
  const body = element("tbody");
  dashboard.cases.forEach(item => {
    const tr = element("tr");
    const cell = element("td");
    const button = element("button", item.title, "text-button table-title");
    button.type = "button";
    button.addEventListener("click", () => { document.getElementById("case-select").value = item.id; selectCase(item.id); document.getElementById("case-select").focus(); });
    cell.append(button, element("span", item.id, "table-subtitle"));
    const finance = item.finance || {};
    const check = element("td");
    check.append(badge(`${(item.blockers || []).length} 项待处理`, (item.blockers || []).length ? "warning" : "neutral"));
    tr.append(cell, element("td", finance.currency || "—"), element("td", money(finance.net_revenue), "number-cell"), element("td", money(finance.contribution_profit), "number-cell"), check);
    body.append(tr);
  });
  table.append(head, body);
  const wrap = element("div", undefined, "table-wrap");
  wrap.append(table);
  document.getElementById("case-table").replaceChildren(wrap);
}
async function selectCase(id) {
  selectedCase = id;
  const sequence = ++caseSequence;
  renderCase(dashboard.cases.find(item => item.id === id));
  if (!id) return;
  try {
    const data = await api(`/api/cases/${encodeURIComponent(id)}`);
    if (sequence === caseSequence) renderCase(data.result);
  } catch (error) { if (sequence === caseSequence) showFeedback(`案例详情读取失败：${error.message}`, true); }
}
function appendInput(form, text, name, type = "text", required = true) {
  const label = element("label", text);
  const input = element(type === "textarea" ? "textarea" : "input");
  input.name = name;
  input.required = required;
  if (type !== "textarea") input.type = type;
  else input.rows = 2;
  label.append(input);
  form.append(label);
  return input;
}
function appendSelect(form, text, name, values) {
  const label = element("label", text);
  const select = element("select");
  select.name = name;
  values.forEach(([value, title]) => { const option = element("option", title); option.value = value; select.append(option); });
  label.append(select);
  form.append(label);
}
function actionForm(operation, key, id) {
  const form = element("form", undefined, "record-action");
  form.dataset.operation = operation;
  const input = element("input");
  input.type = "hidden";
  input.name = key;
  input.value = id;
  form.append(input);
  return form;
}
function submitButton(text) { const button = element("button", text, "button secondary"); button.type = "submit"; return button; }
function renderData() {
  renderMetrics();
  renderCaseTable();
  records("signals-list", dashboard.signals, "还没有情报。先录入一个市场信号，保留来源与客户问题。", item => {
    const card = recordCard(item.title, item, item.case_id, "neutral");
    paragraph(card, "客户问题", item.customer_problem);
    paragraph(card, "原文片段", item.excerpt);
    safeLink(card, item.source_url);
    return card;
  });
  records("opportunities-list", dashboard.opportunities, "还没有商机。选择已有情报，提出一个可以验证的价值主张。", item => {
    const card = recordCard(item.value_proposition, item, translated(item.monetization), "neutral");
    paragraph(card, "客户与市场", `${item.customer_segment} · ${item.market}`);
    paragraph(card, "依据情报", item.signal_id);
    return card;
  });
  records("resources-list", dashboard.resources, "资源池为空。加入候选资源，并保留报价、来源和能力范围。", item => {
    const card = recordCard(item.name, item, translated(item.status || "unverified"), "warning");
    paragraph(card, "资源类型与案例", `${item.kind} · ${item.case_id}`);
    paragraph(card, "能力与限制", item.capabilities);
    paragraph(card, "待核实报价", `${money(item.quote_amount)} ${item.currency}`);
    safeLink(card, item.source_url);
    return card;
  });
  records("contents-list", dashboard.contents, "暂无内容草稿。先建立商机，再为目标客户制作内容。", item => {
    const card = recordCard(item.title, item, translated(item.status), item.status === "accepted" ? "success" : item.status === "rejected" ? "danger" : "neutral");
    paragraph(card, "渠道与版本", `${item.channel} · 版本 ${item.revision || 1} · ${item.opportunity_id}`);
    paragraph(card, "草稿正文", item.body);
    if (item.review_comment) paragraph(card, "评审意见", item.review_comment);
    if (item.status === "draft") {
      const form = actionForm("review_content", "content_id", item.id);
      appendSelect(form, "内部评审决定", "decision", [["accepted", "内部评审通过（不会发布）"], ["rejected", "退回修改"]]);
      appendInput(form, "评审依据与意见", "comment", "textarea");
      form.append(submitButton("记录评审决定"));
      card.append(form);
    }
    return card;
  });
  records("contacts-list", dashboard.contacts, "还没有客户档案。添加联系人后，可以记录沟通内容。", item => {
    const card = recordCard(item.name, item, item.channel, "neutral");
    paragraph(card, "公司", item.company);
    paragraph(card, "渠道标识", item.external_ref);
    return card;
  });
  records("notes-list", dashboard.notes, "暂无沟通记录。这里记录已经发生的沟通与内部备注，不发送消息。", item => {
    const contact = dashboard.contacts.find(contact => contact.id === item.contact_id);
    const card = recordCard(contact ? contact.name : item.contact_id, item, translated(item.direction), "neutral");
    paragraph(card, "沟通记录", item.body);
    return card;
  });
  records("tasks-list", dashboard.tasks, "还没有交付任务。围绕商机创建工作项，并写清验收标准。", item => {
    const status = item.outcome || item.status || "pending";
    const card = recordCard(item.title, item, translated(status), status === "done" ? "success" : status === "blocked" ? "warning" : "neutral");
    paragraph(card, "工作领域与商机", `${translated(item.kind)} · ${item.opportunity_id}`);
    paragraph(card, "验收标准", item.acceptance);
    if (item.evidence_ref) paragraph(card, "结果证据", item.evidence_ref);
    if (item.notes) paragraph(card, "结果说明", item.notes);
    if (status !== "done") {
      const form = actionForm("record_task_result", "task_id", item.id);
      appendSelect(form, "执行结果", "outcome", [["done", "已完成并提供证据"], ["blocked", "存在阻塞"]]);
      appendInput(form, "证据引用", "evidence_ref");
      appendInput(form, "结果说明 / 阻塞原因", "notes", "textarea");
      form.append(submitButton("记录任务结果"));
      card.append(form);
    }
    return card;
  });
  const eventsContainer = document.getElementById("events-list");
  document.getElementById("event-count").textContent = `${dashboard.events.length} 条`;
  if (!dashboard.events.length) emptyMessage(eventsContainer, "暂无操作事件。保存情报、内容、客户或交付任务后，这里将显示记录。");
  else {
    const list = element("ol", undefined, "timeline");
    [...dashboard.events].reverse().forEach(item => {
      const li = element("li");
      const title = element("div", undefined, "timeline-title");
      title.append(element("span", translated(item.operation || item.type || item.event_type || "业务事件")), element("time", dateText(item.created_at || item.occurred_at), "timeline-time"));
      const details = element("details");
      details.append(element("summary", "查看事件详情"), element("pre", JSON.stringify(item, null, 2), "code-block"));
      li.append(title, element("div", item.id || "", "record-ref"), details);
      list.append(li);
    });
    eventsContainer.replaceChildren(list);
  }
  updateSelects();
}
async function refresh() {
  const sequence = ++refreshSequence;
  const refreshButton = document.getElementById("refresh-button");
  refreshButton.disabled = true;
  try {
    const data = await api("/api/dashboard");
    if (sequence !== refreshSequence) return;
    ["cases", "signals", "opportunities", "resources", "contents", "contacts", "notes", "tasks", "events"].forEach(key => { if (!Array.isArray(data[key])) data[key] = []; });
    dashboard = data;
    setStatus("model-status", data.runtime && data.runtime.model_connected ? "模型已连接" : "模型状态未探测", Boolean(data.runtime && data.runtime.model_connected));
    setStatus("publication-status", data.runtime && data.runtime.publication_enabled ? "发布连接器已启用" : "外部发布未启用", Boolean(data.runtime && data.runtime.publication_enabled));
    const select = document.getElementById("case-select");
    select.replaceChildren();
    data.cases.forEach(item => { const option = element("option", `${item.id} · ${item.title}`); option.value = item.id; select.append(option); });
    if (!data.cases.some(item => item.id === selectedCase)) selectedCase = data.cases[0] ? data.cases[0].id : "";
    select.value = selectedCase;
    select.disabled = !data.cases.length;
    renderData();
    await selectCase(selectedCase);
  } finally { if (sequence === refreshSequence) refreshButton.disabled = false; }
}
async function submitCommand(form) {
  if (!form.reportValidity()) return;
  if ([...form.querySelectorAll("select[required]")].some(select => select.disabled)) return showFeedback("请先建立所需的关联记录，再提交。", true);
  const payload = Object.fromEntries(new FormData(form).entries());
  Object.keys(payload).forEach(key => { if (typeof payload[key] === "string") payload[key] = payload[key].trim(); });
  const operation = form.dataset.operation;
  const fingerprint = JSON.stringify({ operation, payload });
  if (form.dataset.pendingFingerprint !== fingerprint) {
    form.dataset.idempotencyKey = crypto.randomUUID();
    form.dataset.pendingFingerprint = fingerprint;
  }
  const buttons = [...form.querySelectorAll('button[type="submit"]')];
  buttons.forEach(button => { button.disabled = true; });
  let saved = false;
  try {
    const response = await api("/api/commands", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ operation, payload, idempotency_key: form.dataset.idempotencyKey }) });
    saved = true;
    delete form.dataset.idempotencyKey;
    delete form.dataset.pendingFingerprint;
    form.reset();
    showFeedback(`${translated(operation)}成功。${response.replayed ? "已识别为重复提交，没有重复创建记录。" : "已保存到本地业务记录。"}${operation === "review_content" ? "内部评审不会触发外部发布。" : ""}`);
    await refresh();
  } catch (error) {
    showFeedback(saved ? `操作已保存，但列表刷新失败：${error.message}。请刷新页面查看。` : `操作未确认完成：${error.message}。保留相同内容重试会使用同一幂等键。`, true);
  } finally { buttons.forEach(button => { button.disabled = false; }); }
}
document.querySelectorAll("[data-tab]").forEach(button => button.addEventListener("click", () => activateTab(button.dataset.tab)));
document.querySelectorAll("[data-jump]").forEach(button => button.addEventListener("click", () => { activateTab(button.dataset.jump); document.querySelector(`#${button.dataset.jump} input`)?.focus(); }));
document.querySelector(".navigation").addEventListener("keydown", event => {
  const keys = Object.keys(labels);
  let index = keys.indexOf(selectedTab);
  if (["ArrowDown", "ArrowRight"].includes(event.key)) index = (index + 1) % keys.length;
  else if (["ArrowUp", "ArrowLeft"].includes(event.key)) index = (index - 1 + keys.length) % keys.length;
  else if (event.key === "Home") index = 0;
  else if (event.key === "End") index = keys.length - 1;
  else return;
  event.preventDefault();
  activateTab(keys[index], true);
});
document.addEventListener("submit", event => {
  if (!event.target.matches("form[data-operation]")) return;
  event.preventDefault();
  submitCommand(event.target);
});
document.getElementById("case-select").addEventListener("change", event => selectCase(event.target.value));
document.getElementById("refresh-button").addEventListener("click", () => refresh().then(() => showFeedback("已刷新本地业务数据。")).catch(error => showFeedback(`数据读取失败：${error.message}`, true)));
window.addEventListener("hashchange", () => activateTab(location.hash.slice(1)));
activateTab(location.hash.slice(1));
refresh().catch(error => { setStatus("model-status", "服务状态待检查", false); showFeedback(`无法读取工作台数据：${error.message}。请确认本地服务已启动。`, true); emptyMessage(document.getElementById("case-detail"), "行业数据暂时无法读取。修复本地服务后，点击右上角刷新。"); });
