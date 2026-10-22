// Shared helpers: API calls with the login token, login guard, safe Markdown rendering.
const TOKEN_KEY = "mas_token";
const USER_KEY = "mas_user";

function getToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch (e) { return null; }
}

function saveLogin(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function clearLogin() {
  try { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); } catch (e) { /* ignore */ }
}

function goToLogin() {
  clearLogin();
  window.location.replace("/login.html");
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(path, { ...options, headers });
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    goToLogin();                       // missing, expired or invalid token (UM-9)
    throw new Error("Login required");
  }
  let data = null;
  if (res.status !== 204) {
    try { data = await res.json(); } catch (e) { data = null; }
  }
  if (!res.ok) {
    throw new Error(errorText(data) || `Request failed (${res.status})`);
  }
  return data;
}

function errorText(data) {
  if (!data) return "";
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail.map((d) => (d.msg || "").replace(/^Value error, /, "")).join(". ");
  }
  return "";
}

// The chat and admin pages stay hidden until the server confirms the login (UM-9).
async function requireLogin({ adminOnly = false } = {}) {
  if (!getToken()) { goToLogin(); return null; }
  try {
    const me = await api("/api/me");
    if (adminOnly && me.role !== "admin") { window.location.replace("/index.html"); return null; }
    localStorage.setItem(USER_KEY, JSON.stringify(me));
    document.body.classList.remove("guarded");
    return me;
  } catch (e) {
    goToLogin();
    return null;
  }
}

async function logout() {
  try { await api("/api/auth/logout", { method: "POST" }); } catch (e) { /* token may be expired */ }
  goToLogin();
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function inlineMarkdown(escaped) {
  return escaped
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      (m, label, url) => `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|\s)_([^_]+)_(?=$|[\s.,!?])/g, "$1<em>$2</em>");
}

// Renders the small Markdown subset used in replies: ### headings, lists, bold, italics, links.
function renderMarkdown(text) {
  const lines = escapeHtml(text).split(/\r?\n/);
  const out = [];
  let list = null;
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) { closeList(); continue; }
    let m;
    if ((m = line.match(/^#{1,4}\s+(.*)$/))) {
      closeList(); out.push(`<h4>${inlineMarkdown(m[1])}</h4>`);
    } else if ((m = line.match(/^\d+\.\s+(.*)$/))) {
      if (list !== "ol") { closeList(); out.push("<ol>"); list = "ol"; }
      out.push(`<li>${inlineMarkdown(m[1])}</li>`);
    } else if ((m = line.match(/^[-*]\s+(.*)$/))) {
      if (list !== "ul") { closeList(); out.push("<ul>"); list = "ul"; }
      out.push(`<li>${inlineMarkdown(m[1])}</li>`);
    } else {
      closeList(); out.push(`<p>${inlineMarkdown(line)}</p>`);
    }
  }
  closeList();
  return out.join("");
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

// ---------------------------------------------------------------- product cards
// Simple category pictures, shown until (or instead of) the real product photo.
const CATEGORY_ICONS = {
  food: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 7c-3-2.2-7.5-.3-7.5 4.6 0 4.2 3 8.4 5.2 8.4 1 0 1.4-.5 2.3-.5s1.3.5 2.3.5c2.2 0 5.2-4.2 5.2-8.4C19.5 6.7 15 4.8 12 7z"/><path d="M12 7c0-2 1-3.5 3-4"/></svg>',
  clothes: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M8.5 3.5 12 5.5l3.5-2 5 3-2 4.5-2.5-1V21h-8V10L5.5 11l-2-4.5z"/></svg>',
  electronics: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><rect x="4" y="5" width="16" height="11" rx="1.5"/><path d="M2 19h20"/></svg>',
};

function starsHtml(rating) {
  if (rating === null || rating === undefined) return "";
  const full = Math.round(Number(rating));
  return `<span class="stars" aria-label="Rated ${Number(rating).toFixed(1)} out of 5">${"★".repeat(full)}<span class="off">${"★".repeat(5 - full)}</span></span>`;
}

function thumbHtml(category) {
  const cat = escapeHtml(category);
  return `<span class="thumb" data-cat="${cat}">${CATEGORY_ICONS[category] || ""}</span>`;
}

function productCardHtml(p, { clickable = true } = {}) {
  const rating = p.rating ? `${starsHtml(p.rating)}<span>${Number(p.rating).toFixed(1)}</span>` : "";
  return `<button type="button" class="product-card${clickable ? "" : " static"}" data-category="${escapeHtml(p.category)}"
      data-id="${escapeHtml(p.product_id)}" title="${escapeHtml(p.name)}">
    ${thumbHtml(p.category)}
    <span class="pc-body">
      <span class="pc-name">${escapeHtml(p.name)}</span>
      <span class="pc-row"><span class="pc-price">${escapeHtml(p.price_text)}</span>${rating}</span>
      <span class="pc-site">${escapeHtml(p.source_site)}${p.sub_category ? " · " + escapeHtml(p.sub_category) : ""}</span>
    </span>
  </button>`;
}

// Renders an assistant reply: product cards when the reply has sections, Markdown otherwise.
function renderReplyHtml(msg, { clickable = true, traceLink = null } = {}) {
  let html = "";
  if (msg.categories && msg.categories.length) {
    html += `<div class="badges">${msg.categories.map((c) =>
      `<span class="badge ${escapeHtml(c)}">${escapeHtml(c)} agent</span>`).join("")}</div>`;
  }
  if (!msg.sections) {
    html += renderMarkdown(msg.content || "");
  } else {
    html += renderMarkdown(msg.intro || "");
    for (const s of msg.sections) {
      const limits = s.limits ? ` <span class="limits">· ${escapeHtml(s.limits)}</span>` : "";
      html += `<div class="section-title">${escapeHtml(s.label)} · ${escapeHtml(s.query)}${limits}</div>`;
      if (s.products && s.products.length) {
        html += `<div class="product-grid">${s.products.map((p) => productCardHtml(p, { clickable })).join("")}</div>`;
      } else {
        html += `<p class="section-note">${escapeHtml(s.note || "")}</p>`;
      }
    }
    if (msg.budget) {
      html += `<div class="section-title">Combinations within your total budget of ${escapeHtml(msg.budget.budget_text)}</div>`;
      if (msg.budget.combinations.length) {
        html += msg.budget.combinations.map((c, i) => `<div class="budget-combo">${i + 1}. ${c.items.map((p) =>
          `<button type="button" class="combo-item" data-category="${escapeHtml(p.category)}" data-id="${escapeHtml(p.product_id)}">${escapeHtml(p.name)}</button> (${escapeHtml(p.price_text)})`).join(" + ")}
          = <strong>${escapeHtml(c.total_text)}</strong></div>`).join("");
      } else if (msg.budget.possible === false) {
        html += `<p class="section-note">No combination of these products fits within your total budget.</p>`;
      }
    }
    if (msg.footer) html += `<div class="reply-footer">${escapeHtml(msg.footer.replace(/^_|_$/g, ""))}</div>`;
  }
  if (traceLink) {
    html += `<a class="trace-link" href="${escapeHtml(traceLink)}">See how the agents answered this &rarr;</a>`;
  }
  return html;
}

// Product photos are loaded live from the source site when a card scrolls into view.
const imageCache = new Map();

function productImage(category, id) {
  const key = `${category}/${id}`;
  if (!imageCache.has(key)) {
    imageCache.set(key, api(`/api/products/${encodeURIComponent(category)}/${encodeURIComponent(id)}/image`)
      .then((data) => data.image).catch(() => null));
  }
  return imageCache.get(key);
}

const cardObserver = ("IntersectionObserver" in window) ? new IntersectionObserver((entries) => {
  for (const entry of entries) {
    if (!entry.isIntersecting) continue;
    cardObserver.unobserve(entry.target);
    fillCardImage(entry.target);
  }
}, { rootMargin: "200px" }) : null;

async function fillCardImage(card) {
  const url = await productImage(card.dataset.category, card.dataset.id);
  if (!url) return;
  const img = new Image();
  img.alt = "";
  img.onload = () => card.querySelector(".thumb").appendChild(img);
  img.src = url;
}

function loadCardImages(container) {
  container.querySelectorAll(".product-card").forEach((card) => {
    if (cardObserver) cardObserver.observe(card); else fillCardImage(card);
  });
}
