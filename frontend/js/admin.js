// Admin dashboard: users, read-only chat histories, data sources and the audit log.
(function () {
  let me = null;
  let refreshTimer = null;

  function showTab(name) {
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
    for (const id of ["users", "sources", "audit"]) {
      document.getElementById(`tab-${id}`).classList.toggle("hidden", id !== name);
    }
    if (name === "sources") loadSources();
    if (name === "audit") loadAudit();
  }

  async function loadUsers() {
    const errorBox = document.getElementById("users-error");
    errorBox.classList.add("hidden");
    const search = document.getElementById("search").value.trim();
    try {
      const users = await api(`/api/admin/users?search=${encodeURIComponent(search)}`);
      const body = document.getElementById("users");
      body.innerHTML = "";
      if (!users.length) {
        body.innerHTML = '<tr><td colspan="7" class="muted">No users found.</td></tr>';
        return;
      }
      for (const u of users) {
        const tr = document.createElement("tr");
        const status = u.is_active ? '<span class="status-active">Active</span>' : '<span class="status-disabled">Disabled</span>';
        const toggle = u.user_id === me.user_id ? "" :
          `<button class="btn small ${u.is_active ? "danger" : "secondary"}" data-action="toggle">${u.is_active ? "Deactivate" : "Reactivate"}</button>`;
        tr.innerHTML = `<td>${escapeHtml(u.name)}</td><td>${escapeHtml(u.email)}</td><td>${escapeHtml(u.role)}</td>
          <td>${status}</td><td>${escapeHtml(formatDate(u.last_login_at) || "never")}</td><td>${u.conversations}</td>
          <td style="white-space:nowrap"><button class="btn small secondary" data-action="history">View history</button> ${toggle}</td>`;
        tr.querySelector('[data-action="history"]').addEventListener("click", () => loadHistory(u));
        const toggleBtn = tr.querySelector('[data-action="toggle"]');
        if (toggleBtn) toggleBtn.addEventListener("click", () => toggleUser(u));
        body.appendChild(tr);
      }
    } catch (e) {
      errorBox.textContent = e.message;
      errorBox.classList.remove("hidden");
    }
  }

  async function toggleUser(u) {
    const action = u.is_active ? "deactivate" : "reactivate";
    if (!confirm(`Do you want to ${action} ${u.name}?`)) return;
    await api(`/api/admin/users/${u.user_id}`, { method: "PATCH", body: JSON.stringify({ is_active: !u.is_active }) });
    await loadUsers();
  }

  async function loadHistory(u) {
    const data = await api(`/api/admin/users/${u.user_id}/conversations`);
    document.getElementById("history-panel").classList.remove("hidden");
    document.getElementById("history-title").textContent = `${data.user.name}'s conversations`;
    document.getElementById("conv-title").textContent = "Select a conversation";
    document.getElementById("conv-messages").innerHTML = "";
    const list = document.getElementById("conv-list");
    list.innerHTML = data.conversations.length ? "" : '<p class="muted">No conversations yet.</p>';
    for (const c of data.conversations) {
      const row = document.createElement("div");
      row.className = "conv-row";
      row.innerHTML = `<div>${escapeHtml(c.title)}</div><div class="muted small">${escapeHtml(formatDate(c.updated_at))}
        ${c.is_deleted ? ' <span class="badge failed">deleted by user</span>' : ""}</div>`;
      row.addEventListener("click", () => {
        list.querySelectorAll(".conv-row").forEach((r) => r.classList.remove("active"));
        row.classList.add("active");
        loadConversation(c.conversation_id);
      });
      list.appendChild(row);
    }
    document.getElementById("history-panel").scrollIntoView({ behavior: "smooth" });
  }

  async function loadConversation(id) {
    const data = await api(`/api/admin/conversations/${id}`);
    document.getElementById("conv-title").textContent = data.title;
    const box = document.getElementById("conv-messages");
    box.innerHTML = "";
    for (const m of data.messages) {
      const wrap = document.createElement("div");
      wrap.className = `msg ${m.sender}`;
      const bubble = document.createElement("div");
      bubble.className = "bubble";
      if (m.sender === "customer") {
        bubble.textContent = m.content;
      } else {
        const calls = (m.agent_calls || []).map((c) =>
          `<span class="badge ${c.status === "failed" ? "failed" : escapeHtml(c.agent)}" title="${escapeHtml(c.error || "")}">
            ${escapeHtml(c.agent)}: ${escapeHtml(c.status)}, ${c.products_found} products, ${c.latency_ms} ms</span>`).join("");
        bubble.innerHTML = renderMarkdown(m.content) +
          `<div class="calls">${calls || '<span class="badge gray">no agents called</span>'}</div>
           <div class="muted small">${escapeHtml(formatDate(m.created_at))}</div>`;
      }
      wrap.appendChild(bubble);
      box.appendChild(wrap);
    }
  }

  function runStatus(r) {
    if (r.status === "ok") return '<span class="status-active">ok</span>';
    if (r.status === "running") return '<span class="badge gray">running</span>';
    return `<span class="status-disabled" title="${escapeHtml(r.error || "")}">${escapeHtml(r.status)}</span>`;
  }

  async function loadSources() {
    const sources = await api("/api/admin/sources");
    const box = document.getElementById("sources");
    box.innerHTML = "";
    let anyRunning = false;
    for (const s of sources) {
      anyRunning = anyRunning || s.refreshing;
      const runs = s.recent_runs.map((r) => `<tr><td>${escapeHtml(r.source_site)}
          <div class="muted small">${escapeHtml(formatDate(r.finished_at || r.started_at))}</div></td>
        <td>${runStatus(r)}</td>
        <td>${r.products_found}</td></tr>`).join("");
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `<h3>${escapeHtml(s.agent)} agent ${s.refreshing ? '<span class="badge">refreshing...</span>' : ""}</h3>
        <div class="stat">${s.products}</div><div class="muted small">available products</div>
        <p class="small">Last updated: ${escapeHtml(formatDate(s.last_updated) || "never")}<br>
        Sites: ${s.sites.map(escapeHtml).join(", ")}</p>
        <div class="table-wrap"><table class="runs"><thead><tr><th>Site and time</th><th>Status</th><th>Products</th></tr></thead>
        <tbody>${runs || '<tr><td colspan="3" class="muted">No scrape runs yet.</td></tr>'}</tbody></table></div>`;
      box.appendChild(card);
    }
    clearTimeout(refreshTimer);
    if (anyRunning && !document.getElementById("tab-sources").classList.contains("hidden")) {
      refreshTimer = setTimeout(loadSources, 3000);
    }
  }

  async function refreshAll() {
    const button = document.getElementById("refresh-all");
    button.disabled = true;
    try {
      await api("/api/admin/refresh?agent=all", { method: "POST" });
      document.getElementById("refresh-note").textContent = "Refresh started. This takes about a minute.";
      setTimeout(loadSources, 1000);
    } finally {
      setTimeout(() => { button.disabled = false; }, 3000);
    }
  }

  async function loadAudit() {
    const rows = await api("/api/admin/audit");
    const body = document.getElementById("audit");
    body.innerHTML = rows.length ? "" : '<tr><td colspan="4" class="muted">No admin views recorded yet.</td></tr>';
    for (const r of rows) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${escapeHtml(formatDate(r.viewed_at))}</td><td>${escapeHtml(r.admin_name)} (${escapeHtml(r.admin_email)})</td>
        <td>${escapeHtml(r.viewed_user_name)} (${escapeHtml(r.viewed_user_email)})</td>
        <td>${r.conversation_id ? `#${r.conversation_id}` : "conversation list"}</td>`;
      body.appendChild(tr);
    }
  }

  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => showTab(t.dataset.tab)));
  document.getElementById("search-btn").addEventListener("click", loadUsers);
  document.getElementById("search").addEventListener("keydown", (e) => { if (e.key === "Enter") loadUsers(); });
  document.getElementById("refresh-all").addEventListener("click", refreshAll);
  document.getElementById("logout").addEventListener("click", logout);

  document.addEventListener("DOMContentLoaded", async () => {
    me = await requireLogin({ adminOnly: true });
    if (!me) return;
    document.getElementById("who").textContent = `${me.name} (admin)`;
    await loadUsers();
  });
})();
