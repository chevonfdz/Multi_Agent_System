// Live architecture page: replays the real trace of a request on the system diagram.
(function () {
  const state = { conversationId: null, lastTrace: null, lastReply: null, busy: false, stepNo: 0, runId: 0 };
  const CANCELLED = new Error("cancelled");
  const svg = document.getElementById("arch-svg");
  const packets = document.getElementById("packets");
  const timeline = document.getElementById("timeline");
  const AGENTS = ["food", "clothes", "electronics"];
  const EXAMPLES = ["A rain jacket and a power bank", "Show me cheaper ones", "Cheapest rice?",
    "Laptops under $500 with 8GB RAM", "Running shoes and earphones under $150 in total", "Apple",
    "What's the weather today?"];

  const speed = () => Number(document.getElementById("speed").value || 1);
  // A new question or Replay cancels the animation that is running (its promises reject).
  const wait = (ms) => {
    const run = state.runId;
    return new Promise((resolve, reject) => setTimeout(() => (run === state.runId ? resolve() : reject(CANCELLED)), ms * speed()));
  };
  const node = (id) => document.getElementById(`n_${id}`);
  const setSub = (id, text) => { const t = document.getElementById(`s_${id}`); if (t) t.textContent = text; };

  function setState(id, cls) {
    const n = node(id);
    if (!n) return;
    n.classList.remove("active", "done", "failed", "skipped");
    if (cls) n.classList.add(cls);
  }

  // Moves a dot along an edge of the diagram.
  function send(edgeId, { reverse = false, back = false } = {}) {
    const path = document.getElementById(edgeId);
    if (!path) return Promise.resolve();
    path.classList.add("lit");
    if (back) path.classList.add("back");
    const length = path.getTotalLength();
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("r", "7");
    dot.setAttribute("class", back ? "packet back" : "packet");
    packets.appendChild(dot);
    const duration = Math.max(350, Math.min(1100, length * 4)) * speed();
    const run = state.runId;
    return new Promise((resolve, reject) => {
      const start = performance.now();
      function frame(now) {
        if (run !== state.runId) { dot.remove(); reject(CANCELLED); return; }
        const k = Math.min(1, (now - start) / duration);
        const eased = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
        const point = path.getPointAtLength(length * (reverse ? 1 - eased : eased));
        dot.setAttribute("cx", point.x);
        dot.setAttribute("cy", point.y);
        if (k < 1) requestAnimationFrame(frame); else { dot.remove(); resolve(); }
      }
      requestAnimationFrame(frame);
    });
  }

  function addStep(title, detail = "", { ms = null, kind = "", pre = null } = {}) {
    if (state.stepNo === 0) timeline.innerHTML = "";
    state.stepNo += 1;
    const li = document.createElement("li");
    if (kind) li.className = kind;
    const time = ms !== null && ms !== undefined ? `<span class="t-time">${escapeHtml(String(ms))} ms</span>` : "";
    li.innerHTML = `<span class="num">${state.stepNo}</span><div><div class="t-title">${escapeHtml(title)}${time}</div>
      ${detail ? `<div class="t-detail">${detail}</div>` : ""}${pre ? `<pre>${escapeHtml(pre)}</pre>` : ""}</div>`;
    timeline.appendChild(li);
    timeline.scrollTop = timeline.scrollHeight;
  }

  function resetDiagram() {
    svg.querySelectorAll(".node").forEach((n) => n.classList.remove("active", "done", "failed", "skipped"));
    svg.querySelectorAll(".edge").forEach((e) => e.classList.remove("lit", "back"));
    packets.innerHTML = "";
    setSub("customer", "Browser · chat page");
    setSub("api", "FastAPI · POST /api/chat");
    setSub("auth", "Login token check (JWT)");
    setSub("planner", "Which agents? Which filters?");
    setSub("planner2", "");
    setSub("combiner", "One reply, a section per agent");
    setSub("combiner2", "");
    setSub("history", "Users · chat history");
    for (const a of AGENTS) setSub(a, "Own websites · own database");
    loadStatus();
    state.stepNo = 0;
    timeline.innerHTML = "";
  }

  function describeFilters(filters) {
    const parts = [];
    if (filters.min_price !== undefined && filters.max_price !== undefined) parts.push(`$${filters.min_price}–$${filters.max_price}`);
    else if (filters.max_price !== undefined) parts.push(`under $${filters.max_price}`);
    else if (filters.min_price !== undefined) parts.push(`over $${filters.min_price}`);
    if (filters.size) parts.push(`size ${filters.size}`);
    if (filters.sort) parts.push(`sort: ${filters.sort.replace("_", " ")}`);
    return parts.join(", ");
  }

  // ------------------------------------------------------------ the replay
  async function play(trace, reply) {
    state.runId += 1;
    resetDiagram();
    try {
      await animate(trace, reply);
    } catch (e) {
      if (e !== CANCELLED) throw e;
    }
  }

  async function animate(trace, reply) {
    document.getElementById("answer-box").classList.add("hidden");
    const planner = trace.planner || {};
    const agents = trace.agents || [];

    setState("customer", "active");
    addStep("The customer asks a question", `“${escapeHtml(trace.message || "")}”`);
    await send("e_req");
    setState("customer", "done");

    setState("api", "active");
    setSub("api", "POST /api/chat received");
    addStep("The website sends it to the API", "POST /api/chat with the conversation id and the login token.");
    await send("e_auth");
    setState("auth", "active");
    addStep("User management checks the login token", "Valid JWT, active account: the request may continue (UM-4).");
    await wait(350);
    await send("e_auth", { reverse: true, back: true });
    setState("auth", "done");
    setState("api", "done");

    setState("history", "active");
    const loaded = (trace.history || {}).loaded || 0;
    setSub("history", `${loaded} previous messages loaded`);
    addStep("The central agent loads the conversation history", `${loaded} recent messages from app.db, used for follow-ups like “cheaper ones”.`);
    await send("e_hist_load", { back: true });
    setState("history", "done");
    await send("e_api_planner");

    setState("planner", "active");
    const mode = planner.mode === "llm" ? "Claude" : "keyword rules";
    setSub("planner", `${planner.tasks ? planner.tasks.length : 0} task(s) · ${mode}`);
    setSub("planner2", `${planner.ms ?? "?"} ms`);
    if (planner.outcome === "tasks") {
      const lines = planner.tasks.map((t) => `${t.domain} agent ← “${t.query || "all products"}”` +
        (describeFilters(t.filters) ? `  [${describeFilters(t.filters)}]` : "") +
        (t.excluded ? `  (hides ${t.excluded} already shown)` : ""));
      let detail = `Planned with ${escapeHtml(mode)}: one task per category.`;
      if (planner.followup) detail += ` This is a follow-up${planner.modifier ? ` (“${escapeHtml(planner.modifier)}”)` : ""}, based on the previous answer.`;
      if (planner.total_budget) detail += ` Shared budget: $${planner.total_budget}.`;
      addStep("The task planner splits the question into tasks", detail, { ms: planner.ms, pre: lines.join("\n") });
    } else {
      const what = { clarify: "a clarifying question is needed", greeting: "this is a greeting",
        out_of_scope: "the question is not about food, clothes or electronics" }[planner.outcome] || planner.outcome;
      addStep("The task planner decides no agent is needed", `Because ${escapeHtml(what)}.` +
        (planner.clarify ? ` It asks: “${escapeHtml(planner.clarify)}”` : ""), { ms: planner.ms, kind: "info" });
    }
    await wait(500);
    setState("planner", "done");

    const used = new Set(agents.map((a) => a.agent));
    for (const a of AGENTS) if (!used.has(a)) { setState(a, "skipped"); setState(`${a}_db`, "skipped"); }

    if (planner.outcome === "tasks" && agents.length) {
      await Promise.all(agents.map((a) => send(`e_plan_${a.agent}`)));
      for (const a of agents) {
        setState(a.agent, "active");
        setSub(a.agent, `“${a.query || "all products"}”`);
      }
      addStep(`${agents.length} agent(s) start at the same time`, agents.map((a) =>
        `<strong>${escapeHtml(a.agent)}</strong>: “${escapeHtml(a.query || "all products")}”`).join(" · "));

      await Promise.all(agents.map(async (a) => {
        if (a.status === "failed") return;
        await send(`e_${a.agent}_db`);
        setState(`${a.agent}_db`, "active");
        setSub(`${a.agent}_db`, `${a.scanned} checked · ${a.matched} matched`);
        await wait(450);
        await send(`e_${a.agent}_db`, { reverse: true, back: true });
        setState(`${a.agent}_db`, "done");
      }));
      for (const a of agents) {
        if (a.status === "failed") {
          setState(a.agent, "failed");
          setSub(a.agent, `failed: ${a.error || "error"}`);
          addStep(`The ${a.agent} agent failed`, `${escapeHtml(a.error || "error")}. The other agents still answer (FR-12).`,
            { ms: a.latency_ms, kind: "failed" });
        } else {
          setState(a.agent, "done");
          setSub(a.agent, `${a.returned} result(s) · ${a.latency_ms} ms`);
          const top = a.top && a.top.length ? `<br>Top: ${a.top.map(escapeHtml).join(", ")}` : "";
          addStep(`The ${a.agent} agent searches ${a.db}`,
            `${a.scanned} products checked, ${a.matched} matched, best ${a.returned} returned` +
            (a.status === "empty" ? " (nothing matched)" : "") + `.${top}`, { ms: a.latency_ms });
        }
      }
      await Promise.all(agents.map((a) => send(`e_${a.agent}_comb`, { back: true })));

      setState("combiner", "active");
      const combiner = trace.combiner || {};
      setSub("combiner", `${combiner.sections || 0} section(s) merged`);
      setSub("combiner2", combiner.mode === "llm" ? "intro written by Claude" : "template reply");
      let detail = `One section per category${combiner.mode === "llm" ? "; Claude wrote the opening sentence" : ""}. Products and links come only from the agents' results (FR-13).`;
      if (trace.budget) detail += ` The budget solver found ${trace.budget.combinations} combination(s) within $${trace.budget.budget}.`;
      addStep("The answer combiner builds one reply", detail, { ms: combiner.ms });
      await wait(400);
      setState("combiner", "done");
      setState("history", "active");
      await send("e_comb_hist");
      setSub("history", `reply + ${(trace.saved || {}).agent_call_rows || 0} agent-call rows saved`);
      addStep("The reply is saved to app.db", `The message and ${(trace.saved || {}).agent_call_rows || 0} agent-call log rows (FR-1, FR-10).`);
      setState("history", "done");
      await send("e_comb_api", { back: true });
    } else {
      setState("combiner", "skipped");
      addStep("The reply is saved to app.db", "Saved with the conversation, so the answer to this question can be understood next time.");
      await send("e_planner_api", { back: true });
    }

    setState("api", "active");
    await send("e_resp", { back: true });
    setState("api", "done");
    setState("customer", "active");
    setSub("customer", `answer received · ${trace.total_ms} ms in total`);
    addStep("The customer sees the answer", `Total server time: ${trace.total_ms} ms.`, { ms: trace.total_ms });
    showAnswer(reply);
    setState("customer", "done");
  }

  function showAnswer(reply) {
    if (!reply) return;
    const box = document.getElementById("answer");
    box.innerHTML = renderReplyHtml(reply, { clickable: false });
    loadCardImages(box);
    document.getElementById("answer-box").classList.remove("hidden");
  }

  function setButtons() {
    document.getElementById("ask-btn").disabled = state.busy;
    document.getElementById("replay-btn").disabled = state.busy || !state.lastTrace;
  }

  // ------------------------------------------------------------ asking and replaying
  async function ask(question) {
    question = (question || "").trim();
    if (!question || state.busy) return;
    state.busy = true;
    state.runId += 1;                 // stop any replay that is still running
    setButtons();
    resetDiagram();
    document.getElementById("answer-box").classList.add("hidden");
    addStep("Sending the question...", "", { kind: "info" });
    try {
      const data = await api("/api/chat", { method: "POST",
        body: JSON.stringify({ conversation_id: state.conversationId, message: question }) });
      state.conversationId = data.conversation_id;
      updateBackLink();
      state.lastTrace = data.trace;
      state.lastReply = { ...data, content: data.reply };
      document.getElementById("question").value = "";
      state.busy = false;
      setButtons();
      await play(state.lastTrace, state.lastReply);
    } catch (e) {
      state.busy = false;
      setButtons();
      addStep("The request failed", escapeHtml(e.message), { kind: "failed" });
    }
  }

  async function replayFromUrl() {
    const params = new URLSearchParams(location.search);
    const conversation = Number(params.get("conversation"));
    if (!conversation) return;
    try {
      const data = await api(`/api/conversations/${conversation}`);
      const messageId = Number(params.get("message"));
      const replies = data.messages.filter((m) => m.sender === "assistant" && m.trace);
      const reply = replies.find((m) => m.message_id === messageId) || replies[replies.length - 1];
      state.conversationId = conversation;
      updateBackLink();
      if (!reply) {
        addStep("No trace for this conversation yet",
          "Its answers were created before tracing was added. Ask a question above to see a live trace.", { kind: "info" });
        return;
      }
      state.lastTrace = reply.trace;
      state.lastReply = reply;
      setButtons();
      await play(state.lastTrace, state.lastReply);
    } catch (e) {
      addStep("Could not load that conversation", escapeHtml(e.message), { kind: "failed" });
    }
  }

  function updateBackLink() {
    if (state.conversationId) document.getElementById("back-link").href = `/index.html?conversation=${state.conversationId}`;
  }

  async function loadStatus() {
    try {
      const status = await api("/api/system/status");
      for (const a of status.agents) setSub(`${a.agent}_db`, `${a.products} products`);
      document.getElementById("planner-mode").textContent = `Planner: ${status.planner}`;
      document.getElementById("refresh-text").textContent =
        `Daily refresh at ${status.daily_refresh}: each agent scrapes its own websites (robots.txt checked) and updates its database. No images are stored.`;
    } catch (e) { /* the diagram still works without the status */ }
  }

  document.getElementById("ask-form").addEventListener("submit", (event) => {
    event.preventDefault();
    ask(document.getElementById("question").value);
  });
  document.getElementById("replay-btn").addEventListener("click", () => {
    if (state.lastTrace && !state.busy) play(state.lastTrace, state.lastReply);
  });
  document.getElementById("logout").addEventListener("click", logout);

  document.addEventListener("DOMContentLoaded", async () => {
    const me = await requireLogin();
    if (!me) return;
    document.getElementById("who").textContent = `${me.name} (${me.role})`;
    const examples = document.getElementById("examples");
    examples.innerHTML = EXAMPLES.map((e) => `<button class="chip" type="button">${escapeHtml(e)}</button>`).join("");
    examples.querySelectorAll(".chip").forEach((chip) => chip.addEventListener("click", () => ask(chip.textContent)));
    timeline.innerHTML = '<li class="empty">Ask a question above to see each step with its real data and timing.</li>';
    await loadStatus();
    await replayFromUrl();
  });
})();
