const API = "";
const state = {
  token: localStorage.getItem("token") || "",
  user: JSON.parse(localStorage.getItem("user") || "null"),
  view: "projects",
  projects: [],
  weather: [],
  systems: [],
  currentProject: null,
  currentSystem: null,
  params: null,
  activeTab: "config",
  editingTab: null,
  editDraft: null,
  validationMessage: "",
  jobs: [],
  result: null,
  filters: { projects: "", weather: "", systems: "", jobs: "", users: "" },
};

const $ = (id) => document.getElementById(id);

async function api(path, opts = {}) {
  const headers = opts.headers || {};
  if (!(opts.body instanceof FormData)) headers["Content-Type"] = "application/json";
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const res = await fetch(API + path, { ...opts, headers });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  const type = res.headers.get("content-type") || "";
  return type.includes("application/json") ? res.json() : res.blob();
}

function setSession(data) {
  state.token = data.token;
  state.user = data.user;
  localStorage.setItem("token", data.token);
  localStorage.setItem("user", JSON.stringify(data.user));
}

function logout() {
  localStorage.clear();
  state.token = "";
  state.user = null;
  state.view = "projects";
  render();
}

function render() {
  if (!state.token) return renderLogin();
  document.body.innerHTML = `<div id="app"></div>`;
  $("app").innerHTML = `
    <div class="app">
      <aside class="sidebar">
        <button class="logo" onclick="goHome()" title="返回项目管理"><div class="logo-mark">冷</div><div>制冷站能耗模拟平台</div></button>
        <div class="nav">
          ${state.currentProject ? projectNav() : rootNav()}
        </div>
      </aside>
      <main class="main">
        <div class="topbar">
          <h2>${topTitle()}</h2>
          <div class="spacer"></div>
          <span class="muted">${state.user?.username || ""}</span>
          <button onclick="logout()">退出</button>
        </div>
        <div class="content" id="content"></div>
      </main>
    </div>`;
  if (state.view === "projects") renderProjects();
  if (state.view === "weather") renderWeather();
  if (state.view === "users") renderUsers();
  if (state.view === "system") renderSystem();
}

function renderLogin() {
  document.body.innerHTML = `<div id="app"></div>`;
  $("app").innerHTML = `
    <div class="login">
      <form class="login-card" onsubmit="login(event)">
        <h1>制冷站能耗模拟平台</h1>
        <p>请输入账号密码登录</p>
        <div class="field"><label>账号</label><input id="username" value="admin" required /></div>
        <div class="field"><label>密码</label><input id="password" type="password" value="admin123456" required /></div>
        <button class="primary" style="width:100%">登录</button>
        <div id="loginError" class="error"></div>
      </form>
    </div>`;
}

async function login(e) {
  e.preventDefault();
  try {
    const data = await api("/api/auth/login", { method: "POST", body: JSON.stringify({ username: $("username").value, password: $("password").value }) });
    setSession(data);
    await loadBase();
    render();
  } catch (err) {
    $("loginError").textContent = err.message;
  }
}

function rootNav() {
  return `
    <button class="nav-item ${state.view === "projects" ? "active" : ""}" onclick="goRoot('projects')"><span>项目管理</span></button>
    <button class="nav-item ${state.view === "weather" ? "active" : ""}" onclick="goRoot('weather')"><span>参数库</span></button>
    ${state.user?.role === "admin" ? `<button class="nav-item ${state.view === "users" ? "active" : ""}" onclick="goRoot('users')"><span>账号管理</span></button>` : ""}
  `;
}

function projectNav() {
  return `
    ${state.systems.map(s => `<div class="system-nav-row ${state.currentSystem?.id === s.id ? "active" : ""}">
      <button class="nav-item ${state.currentSystem?.id === s.id ? "active" : ""}" onclick="openSystem(${s.id})"><span>${esc(s.name)}</span></button>
      <button class="nav-icon" title="编辑系统" onclick="showSystemModal(${s.id})">编辑</button>
      <button class="nav-icon danger" title="删除系统" onclick="deleteSystem(${s.id})">删除</button>
    </div>`).join("")}
    <button class="nav-item" onclick="showSystemModal()"><span>+ 新建系统</span></button>
  `;
}

function goHome() {
  goRoot("projects");
}

function topTitle() {
  if (state.currentProject && state.currentSystem) return `${state.currentProject.name} / ${state.currentSystem.name}`;
  if (state.currentProject) return state.currentProject.name;
  return state.view === "weather" ? "参数库" : state.view === "users" ? "账号管理" : "项目管理";
}

async function loadBase() {
  state.weather = await api("/api/weather");
  state.projects = await api("/api/projects");
}

function goRoot(view) {
  state.currentProject = null;
  state.currentSystem = null;
  state.view = view;
  loadBase().then(render);
}

async function renderProjects() {
  await loadBase();
  const projects = filteredProjects();
  $("content").innerHTML = `
    <div class="filterbar">
      <div class="field"><label>项目筛选</label><input placeholder="项目名称 / 气象城市 / 备注" value="${esc(state.filters.projects)}" oninput="state.filters.projects=this.value; renderProjects()" /></div>
      <button class="primary" onclick="showProjectModal()">新建项目</button>
    </div>
    <div class="grid">
      ${projects.map(p => `
        <div class="card">
          <h3>${esc(p.name)}</h3>
          <p>气象数据：${esc(p.weather_city)} / ${esc(p.weather_year || "")}</p>
          <p>系统数量：${p.system_count}</p>
          <p class="card-remark">${p.remark ? esc(p.remark) : "&nbsp;"}</p>
          <div class="card-actions">
            <button class="primary" onclick="enterProject(${p.id})">进入项目</button>
            <button onclick="showProjectModal(${p.id})">编辑</button>
            <button onclick="copyProject(${p.id})">复制</button>
            <button class="danger" onclick="deleteProject(${p.id})">删除</button>
          </div>
        </div>`).join("") || `<div class="notice">暂无项目</div>`}
    </div>
    ${modalHtml("projectModal", "项目信息", projectFormHtml(), "saveProject()")}
    ${modalHtml("systemModal", "系统信息", systemFormHtml(), "saveSystem()")}`;
}

function filteredProjects() {
  const q = state.filters.projects.trim().toLowerCase();
  if (!q) return state.projects;
  return state.projects.filter(p => [p.name, p.weather_city, p.weather_year, p.remark].some(v => String(v ?? "").toLowerCase().includes(q)));
}

function projectFormHtml() {
  return `<input type="hidden" id="projectId" />
    <div class="field"><label>项目名称 *</label><input id="projectName" required /></div>
    <div class="field"><label>引用城市 *</label><select id="projectCity" onchange="updateProjectYears()">${weatherGroups().map(g => `<option value="${esc(g.city)}">${esc(g.city)}</option>`).join("")}</select></div>
    <div class="field"><label>气象年份 *</label><select id="projectWeather"></select></div>
    <div class="field"><label>备注</label><textarea id="projectRemark"></textarea></div>`;
}

function weatherGroups() {
  const map = new Map();
  for (const w of state.weather) {
    if (!map.has(w.city)) map.set(w.city, []);
    map.get(w.city).push(w);
  }
  return Array.from(map.entries()).map(([city, years]) => ({
    city,
    years: years.sort((a, b) => Number(b.year || 0) - Number(a.year || 0)),
  }));
}

function updateProjectYears(selectedId) {
  const city = $("projectCity")?.value;
  const group = weatherGroups().find(g => g.city === city);
  const options = group?.years || [];
  $("projectWeather").innerHTML = options.map(w => `<option value="${w.id}">${esc(w.year)}</option>`).join("");
  if (selectedId) $("projectWeather").value = selectedId;
}

function showProjectModal(id) {
  const p = id ? state.projects.find(x => x.id === id) : null;
  $("projectId").value = p?.id || "";
  $("projectName").value = p?.name || "";
  $("projectCity").value = p?.weather_city || state.weather[0]?.city || "";
  updateProjectYears(p?.weather_library_id || state.weather[0]?.id || "");
  $("projectRemark").value = p?.remark || "";
  $("projectModal").showModal();
}

async function saveProject() {
  const id = $("projectId").value;
  const body = { name: $("projectName").value, weather_library_id: Number($("projectWeather").value), remark: $("projectRemark").value };
  await api(id ? `/api/projects/${id}` : "/api/projects", { method: id ? "PUT" : "POST", body: JSON.stringify(body) });
  $("projectModal").close();
  renderProjects();
}

async function deleteProject(id) {
  if (!confirm("确认删除该项目？项目下系统和结果也会删除。")) return;
  await api(`/api/projects/${id}`, { method: "DELETE" });
  renderProjects();
}

async function copyProject(id) {
  const data = await api(`/api/projects/${id}/copy`, { method: "POST", body: "{}" });
  await loadBase();
  await enterProject(data.id);
}

async function enterProject(id) {
  state.currentProject = state.projects.find(p => p.id === id);
  state.systems = await api(`/api/projects/${id}/systems`);
  state.currentSystem = state.systems[0] || null;
  state.view = state.currentSystem ? "system" : "system";
  if (state.currentSystem) await loadSystem(state.currentSystem.id);
  render();
}

function leaveProject() {
  state.currentProject = null;
  state.currentSystem = null;
  state.view = "projects";
  render();
}

function systemFormHtml() {
  return `<input type="hidden" id="systemId" />
    <div class="field"><label>系统名称 *</label><input id="systemName" required /></div>
    <div class="field"><label>备注</label><textarea id="systemRemark"></textarea></div>`;
}

function showSystemModal(id) {
  const s = id ? state.systems.find(x => x.id === id) : state.currentSystem;
  $("systemId").value = id ? s?.id || "" : "";
  $("systemName").value = id ? s?.name || "" : "";
  $("systemRemark").value = id ? s?.remark || "" : "";
  $("systemModal").showModal();
}

async function saveSystem() {
  const id = $("systemId").value;
  const body = { name: $("systemName").value, remark: $("systemRemark").value };
  await api(id ? `/api/systems/${id}` : `/api/projects/${state.currentProject.id}/systems`, { method: id ? "PUT" : "POST", body: JSON.stringify(body) });
  $("systemModal").close();
  state.systems = await api(`/api/projects/${state.currentProject.id}/systems`);
  if (!state.currentSystem && state.systems[0]) await loadSystem(state.systems[0].id);
  render();
}

async function openSystem(id) {
  await loadSystem(id);
  render();
}

async function loadSystem(id) {
  const data = await api(`/api/systems/${id}/parameters`);
  state.currentSystem = { ...data.system };
  state.params = data.parameters;
  state.jobs = await api(`/api/systems/${id}/jobs`);
  state.result = null;
}

function renderSystem() {
  if (!state.currentSystem) {
    $("content").innerHTML = `<div class="toolbar"><button class="primary" onclick="showSystemModal()">新建系统</button></div><div class="notice">当前项目暂无系统</div>${modalHtml("systemModal", "系统信息", systemFormHtml(), "saveSystem()")}`;
    return;
  }
  $("content").innerHTML = `
    <div class="toolbar">
      <button class="primary" onclick="startSim()">参数模拟</button>
    </div>
    <div class="panel">
      <div class="tabs">
        ${tabBtn("config", "系统配置")}
        ${tabBtn("simu", "修正系数")}
        ${tabBtn("basic", "基础配置")}
        ${tabBtn("load", "负载率")}
        ${tabBtn("chiller", "变水温报告")}
        ${tabBtn("result", "结果")}
      </div>
      <div id="tabContent"></div>
    </div>
    ${modalHtml("systemModal", "系统信息", systemFormHtml(), "saveSystem()")}`;
  renderTab();
}

function tabBtn(id, text) {
  return `<button class="tab ${state.activeTab === id ? "active" : ""}" onclick="switchTab('${id}')">${text}</button>`;
}

function switchTab(id) {
  if (state.editingTab && state.editingTab !== id) {
    if (!confirm("当前参数正在编辑，切换页签会放弃未确认的修改，是否继续？")) return;
    cancelEdit(false);
  }
  state.activeTab = id;
  state.validationMessage = "";
  renderSystem();
}

function renderTab() {
  const el = $("tabContent");
  if (state.activeTab === "config") el.innerHTML = paramTabShell("系统配置", configHtml());
  if (state.activeTab === "simu") el.innerHTML = paramTabShell("修正系数", valueOnlyTable("simu_values", workingParams().simu_values, ["group", "key", "name", "unit", "value"], { group: "分组", key: "编码", name: "参数名称", unit: "单位", value: "value" }));
  if (state.activeTab === "basic") el.innerHTML = paramTabShell("基础配置", valueOnlyTable("basic_config", workingParams().basic_config, ["key", "name", "unit", "remark", "value"], { key: "编码", name: "参数名称", unit: "单位", remark: "备注", value: "value" }));
  if (state.activeTab === "load") el.innerHTML = paramTabShell("负载率", loadHtml());
  if (state.activeTab === "chiller") el.innerHTML = paramTabShell("变水温报告", chillerHtml());
  if (state.activeTab === "result") renderResultTab();
}

function paramTabShell(title, body) {
  const editing = isEditing();
  const invalid = !isTabComplete(state.activeTab, workingParams());
  const warning = state.validationMessage || (invalid ? "参数未填写完整，请补充" : "");
  return `
    <div class="tab-head">
      <div>
        <h3>${title}</h3>
        ${warning ? `<div class="form-warning">${warning}</div>` : ""}
      </div>
      <div class="inline-actions">
        ${editing
          ? `<button onclick="cancelEdit()">取消</button><button class="primary" onclick="confirmEdit()">确认</button>`
          : `<button class="primary" onclick="beginEdit()">编辑</button>`}
      </div>
    </div>
    ${body}`;
}

function beginEdit() {
  state.editingTab = state.activeTab;
  state.editDraft = deepClone(state.params);
  state.validationMessage = "";
  renderTab();
}

function cancelEdit(render = true) {
  state.editingTab = null;
  state.editDraft = null;
  state.validationMessage = "";
  if (render) renderTab();
}

async function confirmEdit() {
  if (!state.editingTab) return;
  normalizeConfig(workingParams());
  if (!isTabComplete(state.editingTab, workingParams())) {
    state.validationMessage = "参数未填写完整，请补充";
    renderTab();
    return;
  }
  const changed = !sameJson(state.params, state.editDraft);
  if (changed && hasSuccessResult()) {
    const ok = confirm("重新编辑参数会清空结果，需要对项目进行重新模拟。");
    if (!ok) return;
  }
  state.params = deepClone(state.editDraft);
  state.editingTab = null;
  state.editDraft = null;
  state.validationMessage = "";
  if (changed) {
    const data = await saveParams(false);
    if (data.results_cleared) state.result = null;
  }
  state.jobs = await api(`/api/systems/${state.currentSystem.id}/jobs`);
  renderSystem();
}

function configHtml() {
  normalizeConfig(workingParams());
  const c = workingParams().config;
  const editing = isEditing();
  return `
    <div class="form-grid">
      ${selectField("PumpFormChwPri", "冷冻一次泵形式", c.PumpFormChwPri, [["1","一对一"],["2","并联"]])}
      ${selectField("PumpFormCwPri", "冷却泵形式", c.PumpFormCwPri, [["1","一对一"],["2","并联"]])}
      ${selectField("PumpFormChwSec", "冷冻二次泵形式", c.PumpFormChwSec, [["0","无"],["2","并联"]])}
    </div>
    <div class="subhead"><h3>冷机型号</h3>${editing ? `<button onclick="addModel()">新增冷机</button>` : ""}</div>
    ${arrayTable("model_num_dict", c.model_num_dict, ["冷机型号", "冷机台数", "冷机容量RT"])}
    <div class="subhead"><h3>冷冻一次泵参数</h3>${Number(c.PumpFormChwPri) === 2 && editing ? `<button onclick="addPump('chwp_pump_config_list','冷冻一次泵')">新增水泵</button>` : `<span class="muted">一对一时数量由冷机台数自动同步</span>`}</div>
    ${arrayTable("chwp_pump_config_list", c.chwp_pump_config_list, ["name", "flow", "head", "power"], Number(c.PumpFormChwPri) === 1)}
    <div class="subhead"><h3>冷却水泵参数</h3>${Number(c.PumpFormCwPri) === 2 && editing ? `<button onclick="addPump('cwp_pump_config_list','冷却泵')">新增水泵</button>` : `<span class="muted">一对一时数量由冷机台数自动同步</span>`}</div>
    ${arrayTable("cwp_pump_config_list", c.cwp_pump_config_list, ["name", "flow", "head", "power"], Number(c.PumpFormCwPri) === 1)}
    <div class="subhead"><h3>冷冻二次泵参数</h3>${Number(c.PumpFormChwSec) === 2 && editing ? `<button onclick="addPump('chwp_sec_pump_config_list','冷冻二次泵')">新增水泵</button>` : `<span class="muted">形式为无时不启用</span>`}</div>
    ${Number(c.PumpFormChwSec) === 2 ? arrayTable("chwp_sec_pump_config_list", c.chwp_sec_pump_config_list, ["name", "flow", "head", "power"], false) : `<div class="notice">冷冻二次泵形式为无，无需填写水泵参数</div>`}`;
}

function selectField(key, label, value, options) {
  return `<div class="field"><label>${label}</label><select required ${disabledAttr()} onchange="workingParams().config.${key}=Number(this.value); normalizeConfig(workingParams()); renderTab()">${options.map(o => `<option value="${o[0]}" ${String(value)===o[0]?"selected":""}>${o[1]}</option>`).join("")}</select></div>`;
}

function valueOnlyTable(key, rows, cols, labels = {}) {
  return `<table><thead><tr>${cols.map(c => `<th>${esc(labels[c] || c)}</th>`).join("")}</tr></thead><tbody>
    ${rows.map((r,i) => `<tr>${cols.map(c => `<td>${c === "value" ? `<input required ${disabledAttr()} value="${esc(r[c] ?? "")}" oninput="workingParams()['${key}'][${i}]['${c}']=numOrStr(this.value)" />` : esc(r[c] ?? "")}</td>`).join("")}</tr>`).join("")}
  </tbody></table>`;
}

function arrayTable(key, rows, cols, lockCount = false) {
  const labels = { name: "水泵名称", flow: "流量", head: "扬程", power: "功率" };
  return `<table><thead><tr>${cols.map(c => `<th>${labels[c] || c}</th>`).join("")}<th></th></tr></thead><tbody>
    ${rows.map((r,i) => `<tr>${cols.map(c => `<td><input required ${disabledAttr()} value="${esc(r[c] ?? "")}" oninput="workingParams().config.${key}[${i}]['${c}']=numOrStr(this.value)" onchange="${key === "model_num_dict" ? "normalizeConfig(workingParams()); renderTab()" : ""}" /></td>`).join("")}<td>${!isEditing() ? "" : lockCount ? `<span class="muted">自动</span>` : `<button class="danger" onclick="deleteConfigRow('${key}', ${i})">删除</button>`}</td></tr>`).join("")}
  </tbody></table>`;
}

function addModel() {
  if (!isEditing()) return;
  workingParams().config.model_num_dict.push({ "冷机型号": "", "冷机台数": 1, "冷机容量RT": "" });
  normalizeConfig(workingParams());
  renderTab();
}
function addPump(key, prefix = "水泵") {
  if (!isEditing()) return;
  workingParams().config[key].push({ name: `${prefix}${workingParams().config[key].length + 1}`, flow: "", head: "", power: "" });
  renderTab();
}
function deleteConfigRow(key, index) {
  if (!isEditing()) return;
  workingParams().config[key].splice(index, 1);
  if (key === "model_num_dict") normalizeConfig(workingParams());
  renderTab();
}

function normalizeConfig(params = workingParams()) {
  const c = params.config;
  c.model_num_dict ||= [];
  c.chwp_pump_config_list ||= [];
  c.cwp_pump_config_list ||= [];
  c.chwp_sec_pump_config_list ||= [];
  if (Number(c.PumpFormChwPri) === 1) syncPumpRows(params, "chwp_pump_config_list", "冷冻一次泵");
  if (Number(c.PumpFormCwPri) === 1) syncPumpRows(params, "cwp_pump_config_list", "冷却泵");
  if (Number(c.PumpFormChwSec) === 0) c.chwp_sec_pump_config_list = [];
  syncReportsFromModels(params);
}

function syncPumpRows(params, key, prefix) {
  const c = params.config;
  const total = c.model_num_dict.reduce((sum, model) => sum + Math.max(0, Number(model["冷机台数"] || 0)), 0);
  while (c[key].length < total) {
    c[key].push({
      name: `${prefix}${c[key].length + 1}`,
      flow: "",
      head: "",
      power: "",
    });
  }
  if (c[key].length > total) c[key] = c[key].slice(0, total);
}

function reportNameFromModel(model) {
  const name = String(model["冷机型号"] || "").trim() || "冷机型号";
  const cap = String(model["冷机容量RT"] || "").trim();
  return cap && !name.toUpperCase().replace(/\s/g, "").includes(`${cap}RT`) ? `${name} ${cap}RT` : name;
}

function defaultReportRows() {
  const rows = [];
  for (let t = 32; t >= 18; t--) rows.push({ CondEWT: t, "1": "", "0.85": "", "0.8": "", "0.7": "", "0.6": "", "0.5": "", "0.4": "", "0.3": "", "0.2": "", "0.15": "" });
  return rows;
}

function syncReportsFromModels(params = workingParams()) {
  const existing = new Map((params.chiller_reports || []).map(r => [r.name, r]));
  params.chiller_reports = (params.config.model_num_dict || []).map(model => {
    const name = reportNameFromModel(model);
    const found = existing.get(name) || {};
    return { name, capacity_rt: model["冷机容量RT"], count: model["冷机台数"], rows: found.rows || defaultReportRows() };
  });
}

function loadHtml() {
  const params = workingParams();
  return `<div class="subhead"><h3>逐月负载率</h3></div>${loadTable("load_ratio_month", params.load_ratio_month, "month", "load1", "月份")}
    <div class="subhead"><h3>逐时负载率</h3></div>${loadTable("load_ratio_hour", params.load_ratio_hour, "hour", "CL_hour", "时间（h）")}`;
}

function loadTable(key, rows, fixedKey, valueKey, fixedLabel) {
  return `<table><thead><tr><th>${fixedLabel}</th><th>负载率（%）</th></tr></thead><tbody>
    ${rows.map((r,i) => `<tr><td>${esc(r[fixedKey])}</td><td><input required ${disabledAttr()} value="${esc(r[valueKey] ?? "")}" oninput="workingParams()['${key}'][${i}]['${valueKey}']=numOrStr(this.value)" /></td></tr>`).join("")}
  </tbody></table>`;
}

function chillerHtml() {
  normalizeConfig(workingParams());
  return `${workingParams().chiller_reports.map((r,ri) => `
    <div class="panel">
      <div class="subhead">
        <div>
          <h3>${esc(r.name)}</h3>
          <div class="meta-line">冷机容量：${esc(r.capacity_rt || "")} RT　台数：${esc(r.count || 0)}</div>
        </div>
        <div class="inline-actions">
          <button onclick="downloadAuth('/api/systems/${state.currentSystem.id}/chiller/${ri}/template','${esc(r.name)}_变水温报告模板.xlsx')">下载模板</button>
          ${isEditing() ? `<button onclick="chooseChillerReportFile(${ri})">上传数据</button>` : ""}
        </div>
      </div>
      ${reportTable(ri, r.rows || [])}
    </div>`).join("") || `<div class="notice">请先在系统配置中填写冷机型号、容量 RT 和台数</div>`}
    <input class="hidden-file" type="file" id="chillerUploadInput" accept=".xls,.xlsx" onchange="uploadSelectedChillerReport()" />`;
}

function reportTable(ri, rows) {
  const baseCols = rows[0] ? Object.keys(rows[0]) : ["CondEWT","1","0.85","0.8","0.7","0.6","0.5","0.4","0.3","0.2","0.15"];
  const loadCols = ["1","0.85","0.8","0.7","0.6","0.5","0.4","0.3","0.2","0.15"].filter(c => baseCols.includes(c));
  const cols = ["CondEWT", ...loadCols];
  return `<table><thead><tr>${cols.map(c => `<th>${c === "CondEWT" ? "冷却水出水温度（℃）" : `负载率 ${esc(c)}`}</th>`).join("")}</tr></thead><tbody>
    ${rows.map((r,i) => `<tr>${cols.map(c => `<td>${c === "CondEWT" ? esc(r[c] ?? "") : `<input required ${disabledAttr()} value="${esc(r[c] ?? "")}" oninput="workingParams().chiller_reports[${ri}].rows[${i}]['${c}']=numOrStr(this.value)" />`}</td>`).join("")}</tr>`).join("")}
  </tbody></table>`;
}

function chooseChillerReportFile(index) {
  const input = $("chillerUploadInput");
  input.dataset.reportIndex = String(index);
  input.value = "";
  input.click();
}

async function uploadSelectedChillerReport() {
  const input = $("chillerUploadInput");
  const index = Number(input.dataset.reportIndex);
  const file = input.files[0];
  if (!file || Number.isNaN(index)) return;
  if (!isEditing()) return;
  const fd = new FormData();
  fd.append("file", file);
  const data = await api("/api/chiller/preview", { method: "POST", body: fd, headers: {} });
  workingParams().chiller_reports[index].rows = data.rows;
  input.value = "";
  renderTab();
}

function parseRt(name) {
  const m = String(name).match(/(\d+(?:\.\d+)?)\s*RT/i);
  return m ? Number(m[1]) : "";
}

function isEditing() {
  return state.editingTab === state.activeTab && state.editDraft;
}

function workingParams() {
  return isEditing() ? state.editDraft : state.params;
}

function disabledAttr() {
  return isEditing() ? "" : "disabled";
}

function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

function sameJson(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function hasSuccessResult() {
  return state.jobs.some(j => j.status === "success");
}

function filled(value) {
  return value !== "" && value !== null && value !== undefined;
}

function rowsComplete(rows, fields) {
  return Array.isArray(rows) && rows.length > 0 && rows.every(row => fields.every(field => filled(row?.[field])));
}

function isTabComplete(tab, params = state.params) {
  if (!params) return false;
  if (tab === "config") {
    normalizeConfig(params);
    const c = params.config || {};
    if (!rowsComplete(c.model_num_dict, ["冷机型号", "冷机台数", "冷机容量RT"])) return false;
    const chillerCount = (c.model_num_dict || []).reduce((sum, model) => sum + Math.max(0, Number(model["冷机台数"] || 0)), 0);
    if (Number(c.PumpFormChwPri) === 1 || Number(c.PumpFormChwPri) === 2) {
      if (!rowsComplete(c.chwp_pump_config_list, ["name", "flow", "head", "power"])) return false;
    }
    if (Number(c.PumpFormChwPri) === 1 && (c.chwp_pump_config_list || []).length !== chillerCount) return false;
    if (Number(c.PumpFormCwPri) === 1 || Number(c.PumpFormCwPri) === 2) {
      if (!rowsComplete(c.cwp_pump_config_list, ["name", "flow", "head", "power"])) return false;
    }
    if (Number(c.PumpFormCwPri) === 1 && (c.cwp_pump_config_list || []).length !== chillerCount) return false;
    if (Number(c.PumpFormChwSec) === 2 && !rowsComplete(c.chwp_sec_pump_config_list, ["name", "flow", "head", "power"])) return false;
    return true;
  }
  if (tab === "simu") return rowsComplete(params.simu_values, ["value"]);
  if (tab === "basic") return rowsComplete(params.basic_config, ["value"]);
  if (tab === "load") {
    return rowsComplete(params.load_ratio_month, ["load1"]) && rowsComplete(params.load_ratio_hour, ["CL_hour"]);
  }
  if (tab === "chiller") {
    normalizeConfig(params);
    const cols = ["1","0.85","0.8","0.7","0.6","0.5","0.4","0.3","0.2","0.15"];
    return Array.isArray(params.chiller_reports) && params.chiller_reports.length > 0
      && params.chiller_reports.every(report => rowsComplete(report.rows, cols));
  }
  return true;
}

function validateAllParams(params = state.params) {
  for (const tab of ["config", "simu", "basic", "load", "chiller"]) {
    if (!isTabComplete(tab, params)) return false;
  }
  return true;
}

async function saveParams(showAlert = true) {
  normalizeConfig(state.params);
  const data = await api(`/api/systems/${state.currentSystem.id}/parameters`, { method: "PUT", body: JSON.stringify({ parameters: state.params }) });
  state.jobs = await api(`/api/systems/${state.currentSystem.id}/jobs`);
  if (showAlert) alert(data.results_cleared ? "参数已保存，原有运算结果已清空，请重新核算。" : "参数已保存");
  return data;
}

async function startSim() {
  if (state.editingTab) {
    alert("请先确认或取消当前正在编辑的参数。");
    return;
  }
  if (!validateAllParams(state.params)) {
    alert("参数未填写完整，请补充");
    return;
  }
  await saveParams(false);
  const job = await api(`/api/systems/${state.currentSystem.id}/simulate`, { method: "POST", body: "{}" });
  alert(`任务已提交：${job.id}`);
  state.activeTab = "result";
  await loadSystem(state.currentSystem.id);
  renderSystem();
}

async function renderResultTab() {
  state.jobs = await api(`/api/systems/${state.currentSystem.id}/jobs`);
  const jobs = state.jobs;
  const latestSuccess = jobs.find(j => j.status === "success");
  const hasResult = Boolean(latestSuccess);
  $("tabContent").innerHTML = `
    <div class="result-head">
      <h3>运算结果</h3>
      <div class="inline-actions">
      <button onclick="renderResultTab()">刷新</button>
        <button class="primary" onclick="startSim()">${hasResult ? "重新核算" : "能耗核算"}</button>
      </div>
    </div>
    <table><thead><tr><th>ID</th><th>状态</th><th>进度</th><th>消息</th><th>时间</th><th>操作</th></tr></thead><tbody>
      ${jobs.map(j => `<tr><td>${j.id}</td><td><span class="status ${j.status}">${j.status}</span></td><td>${j.progress}%</td><td>${esc(j.message || "")}</td><td>${formatChinaTime(j.updated_at)}</td><td>${j.status==="success" ? `<button onclick="loadResult(${j.id})">查看</button><button onclick="downloadAuth('/api/jobs/${j.id}/download','simulation_result_${j.id}.xlsx')">下载</button>` : ""}</td></tr>`).join("") || `<tr><td colspan="6" class="muted">暂无运算任务</td></tr>`}
    </tbody></table>
    <div id="resultBox" style="margin-top:16px"></div>`;
  if (latestSuccess) await loadResult(latestSuccess.id);
}

function filteredJobs() {
  const q = state.filters.jobs.trim().toLowerCase();
  if (!q) return state.jobs;
  return state.jobs.filter(j => [j.id, j.status, j.message, j.updated_at].some(v => String(v ?? "").toLowerCase().includes(q)));
}

async function loadResult(id) {
  const data = await api(`/api/jobs/${id}/result`);
  state.result = data;
  const box = $("resultBox");
  if (!box) return;
  box.innerHTML = `<div class="charts"><div id="chartEnergy" class="chart"></div><div id="chartHourly" class="chart"></div></div>
    <div class="subhead"><h3>月汇总值</h3></div>${simpleTable(data.monthly)}
    <div class="subhead"><h3>逐时值预览</h3></div>${simpleTable(data.hourly.slice(0, 50))}`;
  drawCharts(data.monthly, data.hourly);
}

function drawCharts(rows, hourlyRows = []) {
  const months = rows.map(r => r.month);
  const energy = echarts.init($("chartEnergy"));
  energy.setOption({
    tooltip: {
      trigger: "axis",
      valueFormatter: value => `${fmt(Number(value))} kWh`,
    },
    legend: {},
    grid: { left: 58, right: 28, top: 46, bottom: 42 },
    xAxis: { type: "category", data: months, name: "月份" },
    yAxis: { type: "value", name: "kWh" },
    series: [
      { name: "总耗电量", type: "bar", data: rows.map(r => r["总耗电量"]) },
      { name: "冷负荷", type: "line", smooth: true, data: rows.map(r => r["冷负荷"]) },
    ],
  });
  const hourly = echarts.init($("chartHourly"));
  const hourlyLabels = hourlyRows.map((r, index) => hourlyLabel(r, index));
  hourly.setOption({
    tooltip: {
      trigger: "axis",
      valueFormatter: value => `${fmt(Number(value))} kWh`,
    },
    legend: {},
    grid: { left: 58, right: 28, top: 46, bottom: 72 },
    dataZoom: [
      { type: "slider", height: 22, bottom: 24, start: 0, end: Math.min(100, hourlyRows.length ? 10 : 100) },
      { type: "inside" },
    ],
    xAxis: { type: "category", data: hourlyLabels, name: "小时", boundaryGap: false },
    yAxis: { type: "value", name: "kWh" },
    series: [
      {
        name: "冷负荷",
        type: "line",
        showSymbol: false,
        smooth: true,
        sampling: "lttb",
        data: hourlyRows.map(r => Number(r.CL_real ?? r.CL ?? r["冷负荷"] ?? 0)),
      },
      {
        name: "总耗电量",
        type: "line",
        showSymbol: false,
        smooth: true,
        sampling: "lttb",
        data: hourlyRows.map(r => Number(r.power ?? r["总耗电量"] ?? 0)),
      },
    ],
  });
}

function hourlyLabel(row, index) {
  const month = row.month ?? "";
  const day = row.day ?? "";
  const hour = row.hour ?? "";
  return month && day ? `${month}/${day} ${hour}:00` : `H${index + 1}`;
}

function simpleTable(rows) {
  if (!rows.length) return `<div class="notice">暂无数据</div>`;
  const cols = Object.keys(rows[0]).slice(0, 14);
  return `<table><thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr>${cols.map(c => `<td>${esc(fmt(r[c]))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

async function deleteSystem(id) {
  if (!confirm("确认删除该系统？")) return;
  await api(`/api/systems/${id}`, { method: "DELETE" });
  state.systems = await api(`/api/projects/${state.currentProject.id}/systems`);
  state.currentSystem = state.systems[0] || null;
  if (state.currentSystem) await loadSystem(state.currentSystem.id);
  render();
}

async function renderWeather() {
  await loadBase();
  const groups = filteredWeatherGroups();
  $("content").innerHTML = `
    <div class="filterbar">
      <div class="field"><label>气象城市筛选</label><input placeholder="城市 / 年份 / 备注" value="${esc(state.filters.weather)}" oninput="state.filters.weather=this.value; renderWeather()" /></div>
      <button class="primary" onclick="showWeatherModal()">新建城市年份数据</button>
    </div>
    <div class="grid">${groups.map(g => `<div class="card"><h3>${esc(g.city)}</h3><p>已管理年份：${g.years.map(w => esc(w.year)).join("、")}</p><p>数据行数：${g.years.reduce((sum,w)=>sum+Number(w.row_count||0),0)}</p><p>${esc(g.years.map(w=>w.remark).filter(Boolean).join("；"))}</p><div class="card-actions"><button onclick="showWeatherRowsByCity('${escAttr(g.city)}')">查看数据</button><button onclick="showWeatherModal('', '${escAttr(g.city)}')">新增年份</button><button onclick="showWeatherUploadByCity('${escAttr(g.city)}')">上传数据</button><button class="danger" onclick="deleteWeatherCity('${escAttr(g.city)}')">删除城市</button></div></div>`).join("") || `<div class="notice">暂无气象参数</div>`}</div>
    ${modalHtml("weatherModal", "城市气象参数", `<input type="hidden" id="weatherId" /><div class="field"><label>城市名称 *</label><input id="weatherCity" /></div><div class="field"><label>年份 *</label><select id="weatherYear">${yearOptions()}</select></div><div class="field"><label>备注</label><textarea id="weatherRemark"></textarea></div>`, "saveWeather()")}
    ${modalHtml("weatherUploadModal", "上传气象参数", `<input type="hidden" id="weatherUploadId" /><input type="hidden" id="weatherUploadCity" /><div class="field"><label>数据年份 *</label><select id="weatherUploadYear">${yearOptions()}</select></div><div class="field"><label>Excel 文件，需包含 times/month/day/hour/dry/rh/wb</label><input type="file" id="weatherFile" accept=".xls,.xlsx" /></div>`, "uploadWeather()")}
    <dialog id="weatherRowsModal" class="wide-dialog">
      <div class="modal-head"><strong id="weatherRowsTitle">气象参数预览</strong><div class="spacer"></div><button class="ghost" onclick="$('weatherRowsModal').close()">×</button></div>
      <div class="modal-body"><div id="weatherRowsBody"></div></div>
    </dialog>`;
}

function filteredWeatherGroups() {
  const q = state.filters.weather.trim().toLowerCase();
  return weatherGroups()
    .filter(g => !q || [g.city, ...g.years.flatMap(w => [w.year, w.remark])].some(v => String(v ?? "").toLowerCase().includes(q)));
}

function yearOptions() {
  const current = new Date().getFullYear();
  const years = [];
  for (let y = current + 1; y >= 2018; y--) years.push(y);
  return years.map(y => `<option value="${y}">${y}</option>`).join("");
}

function showWeatherModal(id, city = "") {
  const w = id ? state.weather.find(x => x.id === id) : null;
  $("weatherId").value = w?.id || "";
  $("weatherCity").value = w?.city || city || "";
  $("weatherYear").value = w?.year || new Date().getFullYear();
  $("weatherRemark").value = w?.remark || "";
  $("weatherModal").showModal();
}
async function saveWeather() {
  const id = $("weatherId").value;
  await api(id ? `/api/weather/${id}` : "/api/weather", { method: id ? "PUT" : "POST", body: JSON.stringify({ city: $("weatherCity").value, year: Number($("weatherYear").value), remark: $("weatherRemark").value }) });
  $("weatherModal").close();
  renderWeather();
}
function showWeatherUpload(id) {
  const w = state.weather.find(x => x.id === id);
  $("weatherUploadId").value = id;
  $("weatherUploadCity").value = w?.city || "";
  $("weatherUploadYear").value = w?.year || new Date().getFullYear();
  $("weatherUploadModal").showModal();
}
function showWeatherUploadByCity(city) {
  const group = weatherGroups().find(g => g.city === city);
  const w = group?.years[0];
  $("weatherUploadId").value = w?.id || "";
  $("weatherUploadCity").value = city;
  $("weatherUploadYear").value = w?.year || new Date().getFullYear();
  $("weatherUploadModal").showModal();
}
async function uploadWeather() {
  let id = Number($("weatherUploadId").value);
  const city = $("weatherUploadCity").value;
  const year = Number($("weatherUploadYear").value);
  let target = state.weather.find(w => w.city === city && Number(w.year) === year);
  if (!target) {
    target = await api("/api/weather", { method: "POST", body: JSON.stringify({ city, year, remark: `${city} ${year} 气象数据` }) });
    id = target.id;
  } else {
    id = target.id;
  }
  const fd = new FormData();
  fd.append("file", $("weatherFile").files[0]);
  await api(`/api/weather/${id}/upload`, { method: "POST", body: fd, headers: {} });
  $("weatherUploadModal").close();
  renderWeather();
}
async function showWeatherRows(id) {
  const data = await api(`/api/weather/${id}/rows`);
  $("weatherRowsTitle").textContent = `气象参数预览，共 ${data.total} 行`;
  $("weatherRowsBody").innerHTML = simpleTable(data.rows);
  $("weatherRowsModal").showModal();
}
async function showWeatherRowsByCity(city, selectedId = "") {
  const group = weatherGroups().find(g => g.city === city);
  if (!group) return;
  const id = selectedId || group.years[0].id;
  const data = await api(`/api/weather/${id}/rows`);
  $("weatherRowsTitle").textContent = `${city} 气象参数预览`;
  $("weatherRowsBody").innerHTML = `
    <div class="subhead">
      <h3>${esc(city)} 气象参数预览，共 ${data.total} 行</h3>
      <div class="inline-actions"><label class="select-label">年份</label><select onchange="showWeatherRowsByCity('${escAttr(city)}', this.value)">${group.years.map(w => `<option value="${w.id}" ${String(w.id)===String(id)?"selected":""}>${esc(w.year)}</option>`).join("")}</select></div>
    </div>
    ${simpleTable(data.rows)}
  `;
  if (!$("weatherRowsModal").open) $("weatherRowsModal").showModal();
}
async function deleteWeather(id) {
  if (!confirm("确认删除该城市气象参数？")) return;
  await api(`/api/weather/${id}`, { method: "DELETE" });
  renderWeather();
}
async function deleteWeatherCity(city) {
  const group = weatherGroups().find(g => g.city === city);
  if (!group || !confirm(`确认删除 ${city} 的全部年份气象参数？`)) return;
  for (const w of group.years) await api(`/api/weather/${w.id}`, { method: "DELETE" });
  renderWeather();
}

async function renderUsers() {
  const users = await api("/api/users");
  const q = state.filters.users.trim().toLowerCase();
  const filtered = q ? users.filter(u => [u.username, u.role, u.created_at].some(v => String(v ?? "").toLowerCase().includes(q))) : users;
  $("content").innerHTML = `<div class="panel"><div class="filterbar"><div class="field"><label>账号筛选</label><input placeholder="账号 / 角色" value="${esc(state.filters.users)}" oninput="state.filters.users=this.value; renderUsers()" /></div><button class="primary" onclick="showUserModal()">新建账号</button></div>${simpleTable(filtered)}</div>
  ${modalHtml("userModal", "新建账号", `<div class="field"><label>账号</label><input id="newUsername" /></div><div class="field"><label>密码</label><input id="newPassword" type="password" /></div><div class="field"><label>角色</label><select id="newRole"><option value="user">普通用户</option><option value="admin">管理员</option></select></div>`, "saveUser()")}`;
}
function showUserModal() { $("userModal").showModal(); }
async function saveUser() {
  await api("/api/users", { method: "POST", body: JSON.stringify({ username: $("newUsername").value, password: $("newPassword").value, role: $("newRole").value }) });
  $("userModal").close(); renderUsers();
}

function modalHtml(id, title, body, saveFn) {
  return `<dialog id="${id}"><div class="modal-head"><strong>${title}</strong><div class="spacer"></div><button class="ghost" onclick="$('${id}').close()">×</button></div><div class="modal-body">${body}</div><div class="modal-foot"><button onclick="$('${id}').close()">取消</button><button class="primary" onclick="${saveFn}">保存</button></div></dialog>`;
}
async function downloadAuth(path, filename) {
  const blob = await api(path, { headers: {} });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
function numOrStr(v) { const n = Number(v); return v !== "" && !Number.isNaN(n) ? n : v; }
function esc(v) { return String(v ?? "").replace(/[&<>"']/g, s => ({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;" }[s])); }
function escAttr(v) { return String(v ?? "").replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/\n/g, " "); }
function fmt(v) { return typeof v === "number" ? Number(v.toFixed(4)) : v; }
function formatChinaTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return esc(value);
  return date.toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

(async function init() {
  if (state.token) {
    try { await loadBase(); } catch { logout(); return; }
  }
  render();
})();
