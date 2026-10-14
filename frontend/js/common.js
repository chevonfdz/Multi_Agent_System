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
