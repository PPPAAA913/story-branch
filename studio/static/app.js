const $ = (id) => document.getElementById(id);
const state = { project: null, selectedId: null };

async function request(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "请求失败，请稍后重试。 ");
  return data;
}

function message(text, kind = "info") {
  const box = $("message");
  box.textContent = text;
  box.className = `message show ${kind}`;
}

function clearMessage() {
  $("message").className = "message";
  $("message").textContent = "";
}

function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

function renderConcept(concept) {
  const card = element("article", "concept-card");
  card.tabIndex = 0;
  card.setAttribute("role", "button");
  card.setAttribute("aria-label", `选择故事方向 ${concept.title}`);
  if (state.selectedId === concept.id) card.classList.add("selected");
  const top = element("div", "concept-top");
  top.append(element("h4", "", concept.title), element("span", "concept-id", concept.id.toUpperCase()));
  card.append(top, element("p", "", concept.logline));
  const hook = element("p");
  hook.append(element("strong", "", "开场钩子："), document.createTextNode(concept.hook));
  card.append(hook);
  const conflict = element("p");
  conflict.append(element("strong", "", "核心冲突："), document.createTextNode(concept.core_conflict));
  card.append(conflict);
  const select = () => {
    state.selectedId = concept.id;
    renderProject(state.project);
  };
  card.addEventListener("click", select);
  card.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(); } });
  return card;
}

function renderOutline(outline) {
  $("outline-section").hidden = false;
  $("outline-title").textContent = outline.series_title || "三集大纲";
  const characters = $("characters");
  characters.replaceChildren();
  (outline.characters || []).forEach((character) => characters.append(element("span", "character", `${character.name} · ${character.goal}`)));
  const episodes = $("episodes");
  episodes.replaceChildren();
  (outline.episodes || []).forEach((episode) => {
    const card = element("article", "episode");
    card.append(element("h4", "", `第 ${episode.number} 集`));
    [["开场", episode.opening], ["转折", episode.turn], ["悬念", episode.cliffhanger]].forEach(([label, value]) => {
      const p = element("p");
      p.append(element("strong", "", `${label}：`), document.createTextNode(value));
      card.append(p);
    });
    episodes.append(card);
  });
  $("production-note").textContent = outline.production_note || "";
}

function renderProject(project) {
  state.project = project;
  state.selectedId = state.selectedId && project.concepts.some((c) => c.id === state.selectedId)
    ? state.selectedId : project.selected_concept_id;
  $("project-id").textContent = `项目 ${project.id}`;
  $("project-id-input").value = project.id;
  $("empty-state").hidden = true;
  $("results").hidden = false;
  const list = $("concept-list");
  list.replaceChildren(...project.concepts.map(renderConcept));
  $("outline-button").disabled = !state.selectedId;
  if (project.outline && state.selectedId === project.selected_concept_id) renderOutline(project.outline);
  else $("outline-section").hidden = true;
  localStorage.setItem("shortDramaProjectId", project.id);
}

async function busy(button, work) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = "处理中…";
  clearMessage();
  try { await work(); }
  catch (error) { message(error.message, "error"); }
  finally { button.textContent = original; button.disabled = false; }
}

$("brief-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const brief = Object.fromEntries(new FormData(form).entries());
  busy($("create-button"), async () => {
    const project = await request("/api/action", { method: "POST", body: JSON.stringify({ action: "create", brief }) });
    state.selectedId = null;
    renderProject(project);
    message("已生成三个方向。请选择一个继续。 ");
  });
});

$("load-button").addEventListener("click", () => busy($("load-button"), async () => {
  const id = $("project-id-input").value.trim();
  if (!id) throw new Error("请先输入项目编号。 ");
  state.selectedId = null;
  renderProject(await request(`/api/projects/${encodeURIComponent(id)}`));
  message("已读取保存的项目。 ");
}));

$("outline-button").addEventListener("click", () => busy($("outline-button"), async () => {
  if (!state.project || !state.selectedId) throw new Error("请先选择故事方向。 ");
  const project = await request("/api/action", { method: "POST", body: JSON.stringify({ action: "outline", project_id: state.project.id, concept_id: state.selectedId }) });
  renderProject(project);
  message("大纲已保存，稍后可用项目编号继续。 ");
}));

$("revise-button").addEventListener("click", () => busy($("revise-button"), async () => {
  if (!state.project) throw new Error("请先创建项目。 ");
  const instruction = $("revision-input").value.trim();
  if (!instruction) throw new Error("请写下修改方向。 ");
  const project = await request("/api/action", { method: "POST", body: JSON.stringify({ action: "revise", project_id: state.project.id, instruction }) });
  state.selectedId = null;
  renderProject(project);
  message("已重新生成方向；此前大纲已清除。 ");
}));

request("/api/health").then((health) => {
  const badge = $("mode-badge");
  badge.textContent = health.model_mode === "demo" ? "样例生成模式" : (health.model_configured ? "OpenRouter 已配置" : "OpenRouter 未配置");
}).catch(() => { $("mode-badge").textContent = "服务未连接"; });

const savedId = localStorage.getItem("shortDramaProjectId");
if (savedId) $("project-id-input").value = savedId;
