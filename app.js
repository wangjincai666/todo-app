const API_BASE = (location.hostname === "127.0.0.1" || location.hostname === "localhost")
  ? "http://127.0.0.1:5000"
  : "https://todo-app-yloz.onrender.com";
async function load() {
  const list = document.querySelector("#list");
  list.innerHTML = "<li>加载中…</li>";

  try {
    const res = await fetch(`${API_BASE}/api/items`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const body = await res.json();
    if (body.code !== 0) throw new Error(body.msg);

    if (body.data.length === 0) {
      list.innerHTML = "<li>还没有待办，加一条试试</li>";
      return;
    }

    list.innerHTML = body.data
      .map(it => `
        <li class="${it.done ? "done" : ""}">
          <input type="checkbox" data-done="${it.id}" ${it.done ? "checked" : ""}>
          <span>${it.title}</span>
          <button data-edit="${it.id}">改</button>
          <button data-id="${it.id}">删</button>
        </li>`)
      .join("");
  } catch (e) {
    list.innerHTML = `<li>加载失败：${e.message} <button id="retry">重试</button></li>`;
    document.querySelector("#retry").addEventListener("click", load);
  }
}

document.querySelector("#add-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.querySelector("#title");
  const title = input.value.trim();
  if (!title) return;

  await fetch(`${API_BASE}/api/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });

  input.value = "";
  load();
});

document.querySelector("#list").addEventListener("click", async (e) => {
  const editId = e.target.dataset.edit;
  if (editId) {
    const li = e.target.closest("li");
    const old = li.querySelector("span").textContent;
    const next = prompt("改成什么？", old);
    if (!next || !next.trim()) return;
    await fetch(`${API_BASE}/api/items/${editId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: next.trim() }),
    });
    load();
    return;
  }

  const id = e.target.dataset.id;
  if (!id) return;
  await fetch(`${API_BASE}/api/items/${id}`, { method: "DELETE" });
  load();
});

document.querySelector("#list").addEventListener("change", async (e) => {
  const box = e.target;
  if (box.type !== "checkbox") return;
  await fetch(`${API_BASE}/api/items/${box.dataset.done}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ done: box.checked ? 1 : 0 }),
  });
  load();
});

load();
const SYSTEM_PROMPT = "你是一个待办助手，回答简短，不超过三句话。";

const history = [];
let controller = null;

function addBubble(role, text) {
  const box = document.querySelector("#chat-log");
  const el = document.createElement("div");
  el.className = `bubble ${role}`;
  el.textContent = text;
  box.appendChild(el);
  box.scrollTop = box.scrollHeight;
  return el;
}

async function sendChat() {
  const input = document.querySelector("#chat-input");
  const text = input.value.trim();
  if (!text) return;

  addBubble("user", text);
  history.push({ role: "user", content: text });
  input.value = "";

  const bubble = addBubble("assistant", "");
  let full = "";
  controller = new AbortController();

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: [{ role: "system", content: SYSTEM_PROMPT }, ...history] }),
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop();
      for (const part of parts) {
        if (!part.startsWith("data: ")) continue;
        const { t } = JSON.parse(part.slice(6));
        full += t;
        bubble.textContent = full;
      }
    }
    history.push({ role: "assistant", content: full });
  } catch (e) {
    const msg = e.name === "AbortError" ? "（已停止）" : `（出错：${e.message}）`;
    bubble.textContent = full + msg;
    if (full) history.push({ role: "assistant", content: full });
  }
}

document.querySelector("#chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  sendChat();
});
document.querySelector("#stop-btn").addEventListener("click", () => controller?.abort());
document.querySelector("#agent-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.querySelector("#agent-input");
  const text = input.value.trim();
  if (!text) return;

  const log = document.querySelector("#agent-log");
  log.textContent = "思考中…";
  input.value = "";

  try {
    const res = await fetch(`${API_BASE}/api/agent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const body = await res.json();
    if (body.code !== 0) throw new Error(body.msg);

    const { logs, reply } = body.data;
    log.textContent =
      (logs.length
        ? logs.map(l => `🔧 ${l.tool}(${JSON.stringify(l.args)}) → ${JSON.stringify(l.result)}`).join("\n")
        : "（这次没有调用工具）") + "\n\n" + reply;

    load();
  } catch (err) {
    log.textContent = "出错：" + err.message;
  }
});