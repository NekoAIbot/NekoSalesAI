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

  const buyPanel = document.getElementById("buy-panel");
  const buyForm = document.getElementById("buy-form");
  const buyError = document.getElementById("buy-error");
  const buyNote = document.getElementById("buy-note");
  const buyPrice = document.getElementById("buy-price");
  const buySend = document.getElementById("buy-send");

  // Stages at which a buy panel is honest to show. Before ready_to_buy the
  // visitor has not chosen anything, and after closed_won or a handoff the
  // decision is no longer theirs to make here.
  const BUY_STAGES = ["ready_to_buy"];

  let token = null;
  let busy = false;
  let catalog = null;
  let paymentsEnabled = null;

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

  /* ---------- the close ---------- */

  /* Show the buy panel only when the conversation has genuinely arrived at
   * a plan, and only when this deployment can actually take a payment. An
   * unconfigured deployment says so rather than offering a button that
   * fails at the last step. */
  async function updateBuyPanel(conversation) {
    if (!buyPanel) return;

    const planCode = conversation.interested_plan_code;
    const eligible = BUY_STAGES.indexOf(conversation.stage) !== -1 && !!planCode;

    if (!eligible) {
      buyPanel.classList.add("hidden");
      return;
    }

    if (paymentsEnabled === null) {
      try {
        const config = await (await fetch("/api/v1/checkout/config")).json();
        paymentsEnabled = !!config.enabled;
      } catch (e) {
        paymentsEnabled = false;
      }
    }

    const plan = findPlan(planCode);
    buyPrice.textContent = plan
      ? plan.display_price + " / " + plan.billing_period
      : "";

    if (!paymentsEnabled) {
      buyForm.classList.add("hidden");
      buyNote.textContent =
        "Card payment is not switched on for this instance yet. Ask the rep " +
        "for an invoice and a person will pick it up.";
      buyPanel.classList.remove("hidden");
      return;
    }

    buyForm.classList.remove("hidden");
    buyNote.textContent = plan
      ? "You'll pay " + plan.display_price + " for " + plan.name +
        ". Your workspace is set up the moment payment clears."
      : "";

    // Pre-fill from what the visitor already told the agent, so the form is
    // a confirmation rather than a second interrogation.
    prefill("buy-name", conversation.visitor_name);
    prefill("buy-email", conversation.visitor_email);
    prefill("buy-company", conversation.visitor_company);

    buyPanel.classList.remove("hidden");
  }

  function prefill(id, value) {
    const field = document.getElementById(id);
    if (field && value && !field.value) field.value = value;
  }

  function findPlan(code) {
    if (!catalog || !catalog.plans) return null;
    return catalog.plans.filter(function (p) { return p.code === code; })[0] || null;
  }

  if (buyForm) {
    buyForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      buyError.classList.add("hidden");
      buySend.disabled = true;

      try {
        const order = await api("/conversations/" + token + "/checkout", {
          method: "POST",
          body: JSON.stringify({
            name: document.getElementById("buy-name").value || null,
            email: document.getElementById("buy-email").value,
            company: document.getElementById("buy-company").value || null,
          }),
        });

        if (!order.checkout_url) {
          throw new Error("We couldn't open the payment page. Try again.");
        }

        window.location.href = order.checkout_url;
      } catch (e) {
        buyError.textContent = e.message;
        buyError.classList.remove("hidden");
        buySend.disabled = false;
      }
    });
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
    // The catalog is the same list the page and the agent both read from,
    // so the buy panel cannot disagree with either about the price.
    try {
      catalog = await api("/catalog", {method: "GET"});
    } catch (e) {
      catalog = null;
    }

    const saved = sessionStorage.getItem(STORAGE_KEY);

    if (saved) {
      try {
        const existing = await api("/conversations/" + saved, {method: "GET"});
        token = saved;
        existing.messages.forEach(renderMessage);
        setStage(existing.stage);
        updateBuyPanel(existing);
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
      updateBuyPanel(created);
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

      // Re-read the thread: an escalation moves its stage and a buy intent
      // sets its plan, and both change what the page should be showing.
      const current = await api("/conversations/" + token, {method: "GET"});
      setStage(current.stage);
      updateBuyPanel(current);
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
