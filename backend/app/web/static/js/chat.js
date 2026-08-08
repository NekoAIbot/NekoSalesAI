/* The live conversation on the landing page.
 *
 * Vanilla, no build step. The only rules worth stating up front:
 *
 * 1. Message bodies are inserted with textContent, never innerHTML. The
 *    transcript contains attacker-controlled text — a visitor can type
 *    anything into the box — so treating it as markup would be a stored XSS
 *    hole on the company's own front page.
 * 2. The thinking indicator is bound to the actual in-flight request. It
 *    appears when the fetch starts and leaves when it settles, so it always
 *    reports real state rather than padding a delay to look busy.
 */

(function () {
  "use strict";

  const panel = document.getElementById("chat-panel");
  if (!panel) return;

  const log = document.getElementById("chat-log");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const send = document.getElementById("chat-send");
  const stage = document.getElementById("chat-stage");
  const errorBox = document.getElementById("chat-error");
  const suggestions = document.getElementById("chat-suggestions");

  const API = "/api/v1/sales";
  const STORAGE_KEY = "nekosales.chat.token";

  let token = null;
  let busy = false;

  const STAGE_LABELS = {
    greeting: "Ready",
    discovery: "Getting to know you",
    qualified: "Talking through plans",
    negotiating: "Checking with the team",
    awaiting_approval: "Waiting on a human",
    ready_to_buy: "Ready to buy",
    closed_won: "Closed",
    handed_off: "A human has this",
  };

  function showError(message) {
    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
  }

  function clearError() {
    errorBox.classList.add("hidden");
    errorBox.textContent = "";
  }

  function setStage(value) {
    stage.textContent = STAGE_LABELS[value] || value;
  }

  function scrollToEnd() {
    log.scrollTop = log.scrollHeight;
  }

  /* Build the "why did it say that" disclosure.
   *
   * Every agent turn gets one. It is the visible half of the promise that
   * the rep's answers are traceable to published facts rather than
   * generated on the spot. */
  function buildReasoning(reasoning) {
    if (!reasoning) return null;

    const details = document.createElement("details");
    details.className = "why";

    const summary = document.createElement("summary");
    summary.textContent = reasoning.escalated
      ? "Why I passed this to a human"
      : "Why I said this";
    details.appendChild(summary);

    const body = document.createElement("div");
    body.className = "why-body";

    body.appendChild(row("Rule", codeText(reasoning.rule)));

    if (reasoning.signals && reasoning.signals.length) {
      body.appendChild(row("Signals", document.createTextNode(
        reasoning.signals.join(" · ")
      )));
    }

    if (reasoning.grounded_in && reasoning.grounded_in.length) {
      const wrap = document.createElement("span");
      reasoning.grounded_in.forEach(function (ref, index) {
        if (index) wrap.appendChild(document.createTextNode(" · "));
        wrap.appendChild(codeText(ref));
      });
      body.appendChild(row("Source", wrap));
    } else {
      body.appendChild(row("Source", document.createTextNode(
        "No product claim made"
      )));
    }

    details.appendChild(body);
    return details;
  }

  function row(key, valueNode) {
    const line = document.createElement("div");
    line.className = "why-row";

    const k = document.createElement("span");
    k.className = "why-key";
    k.textContent = key;

    const v = document.createElement("span");
    v.className = "why-val";
    v.appendChild(valueNode);

    line.appendChild(k);
    line.appendChild(v);
    return line;
  }

  function codeText(value) {
    const code = document.createElement("code");
    code.textContent = value;
    return code;
  }

  function renderMessage(message) {
    if (!message.body) return;

    const wrapper = document.createElement("div");
    wrapper.className = "msg msg--" + message.role;

    if (message.role === "human") {
      const tag = document.createElement("div");
      tag.className = "msg-tag";
      tag.textContent = "Answered by a person";
      wrapper.appendChild(tag);
    }

    const body = document.createElement("div");
    body.className = "msg-body";
    body.textContent = message.body;   // never innerHTML
    wrapper.appendChild(body);

    if (message.role === "agent") {
      const why = buildReasoning(message.reasoning);
      if (why) wrapper.appendChild(why);
    }

    log.appendChild(wrapper);
    scrollToEnd();
  }

  function showThinking() {
    const node = document.createElement("div");
    node.className = "thinking";
    node.id = "thinking";
    node.setAttribute("aria-label", "The rep is working out a reply");

    for (let i = 0; i < 3; i++) node.appendChild(document.createElement("span"));

    log.appendChild(node);
    scrollToEnd();
  }

  function hideThinking() {
    const node = document.getElementById("thinking");
    if (node) node.remove();
  }

  function setBusy(value) {
    busy = value;
    send.disabled = value;
    input.disabled = value;
  }

  async function api(path, options) {
    const response = await fetch(API + path, Object.assign(
      { headers: { "Content-Type": "application/json" } },
      options || {}
    ));

    if (!response.ok) {
      let detail = "Something went wrong. Try again.";
      try {
        const body = await response.json();
        if (body && typeof body.detail === "string") detail = body.detail;
      } catch (e) { /* keep the generic message */ }

      throw new Error(detail);
    }

    return response.json();
  }

  async function start() {
    const saved = sessionStorage.getItem(STORAGE_KEY);

    if (saved) {
      try {
        const existing = await api("/conversations/" + saved, {method: "GET"});
        token = saved;
        existing.messages.forEach(renderMessage);
        setStage(existing.stage);
        return;
      } catch (e) {
        // The stored thread is gone (restarted database, expired demo).
        // Fall through and open a fresh one rather than showing an error
        // the visitor can do nothing about.
        sessionStorage.removeItem(STORAGE_KEY);
      }
    }

    try {
      const created = await api("/conversations", {method: "POST"});
      token = created.token;
      sessionStorage.setItem(STORAGE_KEY, token);
      created.messages.forEach(renderMessage);
      setStage(created.stage);
    } catch (e) {
      showError(e.message);
    }
  }

  async function submit(text) {
    if (busy || !token) return;

    const trimmed = text.trim();
    if (!trimmed) return;

    clearError();
    renderMessage({role: "visitor", body: trimmed});

    input.value = "";
    input.style.height = "auto";
    setBusy(true);
    showThinking();

    try {
      const reply = await api("/conversations/" + token + "/messages", {
        method: "POST",
        body: JSON.stringify({body: trimmed}),
      });

      hideThinking();
      renderMessage(reply);

      // Re-read the thread's stage: an escalation moves it, and the header
      // should say so rather than silently staying on the old label.
      const current = await api("/conversations/" + token, {method: "GET"});
      setStage(current.stage);
    } catch (e) {
      hideThinking();
      showError(e.message);
    } finally {
      setBusy(false);
      input.focus();
    }
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    submit(input.value);
  });

  // Enter sends, Shift+Enter breaks the line — what a chat surface should do.
  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit(input.value);
    }
  });

  input.addEventListener("input", function () {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
  });

  if (suggestions) {
    suggestions.addEventListener("click", function (event) {
      const chip = event.target.closest(".chip");
      if (!chip) return;
      submit(chip.textContent);
    });
  }

  // Pricing-card buttons drop a question into the thread rather than
  // scrolling to a dead anchor.
  document.querySelectorAll("[data-plan]").forEach(function (link) {
    link.addEventListener("click", function () {
      const plan = link.getAttribute("data-plan");
      setTimeout(function () {
        submit("Tell me about the " + plan + " plan");
      }, 400);
    });
  });

  start();
})();
