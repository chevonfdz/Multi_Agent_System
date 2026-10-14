// Chat page: conversation sidebar (FR-1) and the chat with the central agent.
(function () {
  const state = { me: null, conversationId: null, conversations: [], busy: false };
  const el = {
    who: document.getElementById("who"),
    adminLink: document.getElementById("admin-link"),
    list: document.getElementById("conversations"),
    inner: document.getElementById("messages-inner"),
    scroller: document.getElementById("messages"),
    form: document.getElementById("composer"),
    input: document.getElementById("message"),
    send: document.getElementById("send"),
    sidebar: document.getElementById("sidebar"),
  };
  const EXAMPLES = [
    "Cheapest rice?",
    "Laptops under $500 with 8GB RAM",
    "A rain jacket and a power bank",
    "A shirt and a phone charger under $40",
    "Running shoes and earphones under $150 in total",
    "Apple",
  ];

  function scrollToBottom() { el.scroller.scrollTop = el.scroller.scrollHeight; }

  function badgeHtml(categories) {
    if (!categories || !categories.length) return "";
    return `<div class="badges">${categories.map((c) =>
      `<span class="badge ${escapeHtml(c)}">${escapeHtml(c)} agent</span>`).join("")}</div>`;
  }

  function addMessage(sender, content, categories) {
    const wrap = document.createElement("div");
    wrap.className = `msg ${sender}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    if (sender === "customer") {
      bubble.textContent = content;
    } else {
      bubble.innerHTML = badgeHtml(categories) + renderMarkdown(content);
    }
    wrap.appendChild(bubble);
    el.inner.appendChild(wrap);
    scrollToBottom();
    return wrap;
  }

  function showWelcome() {
    const name = state.me ? escapeHtml(state.me.name.split(" ")[0]) : "";
    el.inner.innerHTML = `
      <div class="welcome">
        <h1>Hi ${name}, what are you shopping for?</h1>
        <p>Three agents search food, clothes and electronics shops for you, and combine the
           answers when you ask about more than one category.</p>
        <div class="chips">${EXAMPLES.map((e) => `<button class="chip" type="button">${escapeHtml(e)}</button>`).join("")}</div>
      </div>`;
    el.inner.querySelectorAll(".chip").forEach((chip) =>
      chip.addEventListener("click", () => sendMessage(chip.textContent)));
  }

  function renderConversations() {
    el.list.innerHTML = "";
    if (!state.conversations.length) {
      el.list.innerHTML = '<li class="empty-note">No conversations yet.</li>';
      return;
    }
    for (const c of state.conversations) {
      const li = document.createElement("li");
      li.className = "conv-item" + (c.conversation_id === state.conversationId ? " active" : "");
      li.innerHTML = `<div class="title"><div>${escapeHtml(c.title)}</div><small>${escapeHtml(formatDate(c.updated_at))}</small></div>
        <button class="icon-btn" type="button" title="Delete conversation" aria-label="Delete conversation">&times;</button>`;
      li.addEventListener("click", () => openConversation(c.conversation_id));
      li.querySelector(".icon-btn").addEventListener("click", (event) => {
        event.stopPropagation();
        deleteConversation(c);
      });
      el.list.appendChild(li);
    }
  }

  async function loadConversations() {
    state.conversations = await api("/api/conversations");
    renderConversations();
  }

  async function openConversation(id) {
    el.sidebar.classList.remove("open");
    const data = await api(`/api/conversations/${id}`);
    state.conversationId = id;
    el.inner.innerHTML = "";
    for (const m of data.messages) addMessage(m.sender, m.content, m.categories);
    if (!data.messages.length) showWelcome();
    renderConversations();
    el.input.focus();
  }

  async function deleteConversation(c) {
    if (!confirm(`Delete the conversation "${c.title}"?`)) return;
    await api(`/api/conversations/${c.conversation_id}`, { method: "DELETE" });
    if (state.conversationId === c.conversation_id) newChat();
    await loadConversations();
  }

  function newChat() {
    state.conversationId = null;
    showWelcome();
    renderConversations();
    el.sidebar.classList.remove("open");
    el.input.focus();
  }

  async function sendMessage(text) {
    text = (text || "").trim();
    if (!text || state.busy) return;
    if (!state.conversationId) el.inner.innerHTML = "";
    state.busy = true;
    el.send.disabled = true;
    el.input.value = "";
    autoGrow();
    addMessage("customer", text);
    const typing = addMessage("assistant", "_The agents are searching..._");
    typing.classList.add("typing");
    try {
      const data = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify({ conversation_id: state.conversationId, message: text }),
      });
      typing.remove();
      addMessage("assistant", data.reply, data.categories);
      const isNew = state.conversationId !== data.conversation_id;
      state.conversationId = data.conversation_id;
      if (isNew) await loadConversations();
      else {
        // Move the active conversation to the top of the list.
        const c = state.conversations.find((x) => x.conversation_id === data.conversation_id);
        if (c) { c.updated_at = new Date().toISOString(); state.conversations.sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1)); }
        renderConversations();
      }
    } catch (e) {
      typing.remove();
      addMessage("assistant", `Sorry, the message could not be sent: ${e.message}`);
    } finally {
      state.busy = false;
      el.send.disabled = false;
      el.input.focus();
    }
  }

  function autoGrow() {
    el.input.style.height = "auto";
    el.input.style.height = Math.min(el.input.scrollHeight, 160) + "px";
  }

  el.form.addEventListener("submit", (event) => { event.preventDefault(); sendMessage(el.input.value); });
  el.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendMessage(el.input.value); }
  });
  el.input.addEventListener("input", autoGrow);
  document.getElementById("new-chat").addEventListener("click", newChat);
  document.getElementById("logout").addEventListener("click", logout);
  document.getElementById("menu-toggle").addEventListener("click", () => el.sidebar.classList.toggle("open"));

  document.addEventListener("DOMContentLoaded", async () => {
    state.me = await requireLogin();
    if (!state.me) return;
    el.who.textContent = `${state.me.name} (${state.me.role})`;
    if (state.me.role === "admin") el.adminLink.classList.remove("hidden");
    showWelcome();
    await loadConversations();
    el.input.focus();
  });
})();
