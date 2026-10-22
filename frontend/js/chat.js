// Chat page: conversation sidebar (FR-1), the chat with the central agent, product cards and
// the product details panel (opens in the same tab).
(function () {
  const state = { me: null, conversationId: null, conversations: [], busy: false, productRequest: 0 };
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
    panel: document.getElementById("product-panel"),
    panelBody: document.getElementById("pp-body"),
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

  function traceLinkFor(msg) {
    if (!msg.message_id || !msg.trace || !state.conversationId) return null;   // older answers have no trace
    return `/architecture.html?conversation=${state.conversationId}&message=${msg.message_id}`;
  }

  function addCustomerMessage(text) {
    const wrap = document.createElement("div");
    wrap.className = "msg customer";
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    wrap.appendChild(bubble);
    el.inner.appendChild(wrap);
    scrollToBottom();
    return wrap;
  }

  function addAssistantMessage(msg) {
    const wrap = document.createElement("div");
    wrap.className = "msg assistant";
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = renderReplyHtml(msg, { traceLink: traceLinkFor(msg) });
    wrap.appendChild(bubble);
    el.inner.appendChild(wrap);
    loadCardImages(bubble);
    scrollToBottom();
    return wrap;
  }

  function showWelcome() {
    const name = state.me ? escapeHtml(state.me.name.split(" ")[0]) : "";
    el.inner.innerHTML = `
      <div class="welcome">
        <h1>Hi ${name}, what are you shopping for?</h1>
        <p>Three agents search food, clothes and electronics shops for you, and combine the
           answers when you ask about more than one category. Click any product to see its details.</p>
        <div class="chips">${EXAMPLES.map((e) => `<button class="chip" type="button">${escapeHtml(e)}</button>`).join("")}</div>
      </div>`;
    el.inner.querySelectorAll(".chip").forEach((chip) =>
      chip.addEventListener("click", () => sendMessage(chip.textContent)));
  }

  // ------------------------------------------------------------ conversations
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
    closeProduct();
    const data = await api(`/api/conversations/${id}`);
    state.conversationId = id;
    history.replaceState(null, "", `/index.html?conversation=${id}`);
    el.inner.innerHTML = "";
    for (const m of data.messages) {
      if (m.sender === "customer") addCustomerMessage(m.content);
      else addAssistantMessage(m);
    }
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
    history.replaceState(null, "", "/index.html");
    closeProduct();
    showWelcome();
    renderConversations();
    el.sidebar.classList.remove("open");
    el.input.focus();
  }

  // ------------------------------------------------------------ sending
  async function sendMessage(text) {
    text = (text || "").trim();
    if (!text || state.busy) return;
    if (!state.conversationId) el.inner.innerHTML = "";
    state.busy = true;
    el.send.disabled = true;
    el.input.value = "";
    autoGrow();
    addCustomerMessage(text);
    const typing = addAssistantMessage({ content: "_The agents are searching..._" });
    typing.classList.add("typing");
    try {
      const data = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify({ conversation_id: state.conversationId, message: text }),
      });
      typing.remove();
      const isNew = state.conversationId !== data.conversation_id;
      state.conversationId = data.conversation_id;
      if (isNew) history.replaceState(null, "", `/index.html?conversation=${data.conversation_id}`);
      addAssistantMessage({ ...data, content: data.reply });
      if (isNew) await loadConversations();
      else {
        const c = state.conversations.find((x) => x.conversation_id === data.conversation_id);
        if (c) { c.updated_at = new Date().toISOString(); state.conversations.sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1)); }
        renderConversations();
      }
    } catch (e) {
      typing.remove();
      addAssistantMessage({ content: `Sorry, the message could not be sent: ${e.message}` });
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

  // ------------------------------------------------------------ product panel
  function closeProduct() {
    el.panel.classList.add("hidden");
    el.inner.querySelectorAll(".product-card.selected").forEach((c) => c.classList.remove("selected"));
  }

  function showPanelLoading() {
    el.panel.classList.remove("hidden");
    el.panelBody.innerHTML = `<div class="gallery-main skeleton"></div>
      <div class="skeleton" style="height:22px;width:40%;margin-top:18px"></div>
      <div class="skeleton" style="height:30px;width:85%;margin-top:10px"></div>
      <div class="skeleton" style="height:34px;width:30%;margin-top:10px"></div>
      <div class="skeleton" style="height:90px;margin-top:16px"></div>`;
  }

  async function openProduct(category, id, card) {
    el.inner.querySelectorAll(".product-card.selected").forEach((c) => c.classList.remove("selected"));
    if (card) card.classList.add("selected");
    const request = ++state.productRequest;
    showPanelLoading();
    try {
      const p = await api(`/api/products/${encodeURIComponent(category)}/${encodeURIComponent(id)}`);
      if (request !== state.productRequest) return;   // another product was clicked meanwhile
      renderProduct(p);
    } catch (e) {
      if (request !== state.productRequest) return;
      el.panelBody.innerHTML = `<div class="error">Could not load this product: ${escapeHtml(e.message)}</div>`;
    }
  }

  function renderProduct(p) {
    const images = p.images || [];
    const main = images.length
      ? `<img id="pp-main-img" src="${escapeHtml(images[0])}" alt="${escapeHtml(p.name)}">`
      : `<span class="thumb" data-cat="${escapeHtml(p.category)}">${CATEGORY_ICONS[p.category] || ""}</span>`;
    const thumbs = images.length > 1 ? `<div class="gallery-thumbs">${images.map((src, i) =>
      `<button type="button" class="${i === 0 ? "active" : ""}" data-src="${escapeHtml(src)}" aria-label="Show photo ${i + 1}">
        <img src="${escapeHtml(src)}" alt=""></button>`).join("")}</div>` : "";
    const available = p.availability === "in_stock";
    const rating = p.rating ? `<div class="pp-rating">${starsHtml(p.rating)} ${Number(p.rating).toFixed(1)} / 5</div>` : "";
    const details = (p.details || []).map((d) =>
      `<tr><th>${escapeHtml(d.label)}</th><td>${escapeHtml(d.value)}</td></tr>`).join("");
    const source = p.is_api_source
      ? `<div>Source: <strong>${escapeHtml(p.source_site)}</strong> (product data API)</div>`
      : `<div>Sold on <strong>${escapeHtml(p.source_site)}</strong></div>
         <a class="btn secondary small" href="${escapeHtml(p.product_url)}" target="_blank" rel="noopener noreferrer">Open the original listing &#8599;</a>`;
    el.panelBody.innerHTML = `
      <div class="gallery-main">${main}</div>
      ${thumbs}
      <div class="pp-crumbs">${escapeHtml(p.category)} &rsaquo; ${escapeHtml(p.sub_category || p.category)}</div>
      <h2 class="pp-name">${escapeHtml(p.name)}</h2>
      <div class="pp-price-row">
        <span class="pp-price">${escapeHtml(p.price_text)}</span>
        <span class="avail ${available ? "" : "out"}">${available ? "In stock" : "Out of stock"}</span>
      </div>
      ${rating}
      ${p.description ? `<p class="pp-desc">${escapeHtml(p.description)}</p>` : ""}
      ${details ? `<table class="pp-details"><tbody>${details}</tbody></table>` : ""}
      <div class="pp-source">
        ${source}
        <div class="muted small" style="margin-top:6px">Data last updated ${escapeHtml(formatDate(p.last_updated) || "-")}.
          Photos are shown live from the shop and are not stored.</div>
      </div>`;
    el.panelBody.querySelectorAll(".gallery-thumbs button").forEach((b) => b.addEventListener("click", () => {
      el.panelBody.querySelectorAll(".gallery-thumbs button").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      document.getElementById("pp-main-img").src = b.dataset.src;
    }));
    el.panelBody.scrollTop = 0;
  }

  // Clicks on product cards and budget-combination items open the panel.
  el.inner.addEventListener("click", (event) => {
    const target = event.target.closest(".product-card, .combo-item");
    if (!target) return;
    openProduct(target.dataset.category, target.dataset.id, target.classList.contains("product-card") ? target : null);
  });
  document.getElementById("pp-close").addEventListener("click", closeProduct);
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeProduct(); });

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
    const wanted = Number(new URLSearchParams(location.search).get("conversation"));
    if (wanted && state.conversations.some((c) => c.conversation_id === wanted)) {
      await openConversation(wanted);
    }
    el.input.focus();
  });
})();
