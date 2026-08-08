/* Checkout return — the screen a buyer lands on with their money already gone.
 *
 * Two rules govern everything here.
 *
 * 1. The page reports server state and never anticipates it. There is a
 *    separate visible state for checking, not-seen-yet, provisioning, ready
 *    and failed, and the page shows whichever one the API says is true. A
 *    screen that shows "confirmed" before the server has confirmed is lying
 *    at the exact moment a buyer is least able to tolerate it.
 *
 * 2. Provisioning progress is per-step and driven by real timestamps from the
 *    server, so a step ticks over when it actually finished. That is what
 *    makes this different from a spinner: a spinner says "something is
 *    happening", this says which part is done.
 *
 * Credentials are rendered with textContent and are never written to storage
 * or the URL. They arrive once and live only in the DOM.
 */

(function () {
  "use strict";

  const API = "/api/v1/checkout";

  const params = new URLSearchParams(window.location.search);
  const reference = params.get("reference") || params.get("trxref");

  const states = {
    checking: document.getElementById("state-checking"),
    pending: document.getElementById("state-pending"),
    provisioning: document.getElementById("state-provisioning"),
    ready: document.getElementById("state-ready"),
    problem: document.getElementById("state-problem"),
  };

  const stepsList = document.getElementById("steps");

  // Poll steadily rather than backing off: provisioning is measured in
  // hundreds of milliseconds, and the wait that matters is the buyer's bank
  // confirming, which is not something a longer interval helps with.
  const POLL_MS = 1500;
  const MAX_POLLS = 80;   // two minutes, then stop and say so

  let polls = 0;
  let credentialsShown = false;

  function show(name) {
    Object.keys(states).forEach(function (key) {
      states[key].classList.toggle("hidden", key !== name);
    });
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function renderSummary(target, order) {
    const box = document.getElementById(target);
    if (!box) return;

    box.replaceChildren();

    const rows = [
      ["Plan", order.plan_name],
      ["Amount", order.display_amount + " per " + order.billing_period],
      ["Email", order.buyer_email],
      ["Reference", order.reference],
    ];

    rows.forEach(function (pair) {
      const row = el("div", "summary-row");
      row.appendChild(el("span", "summary-key", pair[0]));
      row.appendChild(el("span", "summary-val", pair[1]));
      box.appendChild(row);
    });
  }

  function renderSteps(steps) {
    stepsList.replaceChildren();

    steps.forEach(function (step) {
      const item = el("li", "step" + (step.done ? " step--done" : ""));
      item.appendChild(el("span", "step-mark", step.done ? "✓" : "•"));
      item.appendChild(el("span", "step-label", step.label));
      stepsList.appendChild(item);
    });
  }

  function renderCredentials(workspace) {
    // The API returns these exactly once — on the response that created them.
    // A later poll returns null, so anything already on screen must survive.
    if (credentialsShown) return;
    if (!workspace.api_key && !workspace.temporary_password) return;

    const box = document.getElementById("credentials");
    box.classList.remove("hidden");

    if (workspace.api_key) {
      const node = document.getElementById("cred-key");
      node.replaceChildren();
      node.appendChild(el("div", "cred-label", "API key"));
      node.appendChild(el("code", "cred-value", workspace.api_key));
    }

    if (workspace.temporary_password) {
      const node = document.getElementById("cred-password");
      node.replaceChildren();
      node.appendChild(el("div", "cred-label", "Temporary password"));
      node.appendChild(el("code", "cred-value", workspace.temporary_password));
    }

    credentialsShown = true;
  }

  function renderReady(order, workspace) {
    document.getElementById("ready-line").textContent =
      workspace.company_name +
      " is set up. Your rep is called " + workspace.agent_name + ".";

    renderSummary("ready-summary", order);
    renderCredentials(workspace);
    show("ready");
  }

  function renderProblem(title, line, order) {
    document.getElementById("problem-title").textContent = title;
    document.getElementById("problem-line").textContent = line;
    if (order) renderSummary("problem-summary", order);
    show("problem");
  }

  async function poll() {
    polls += 1;

    let body;
    try {
      const response = await fetch(API + "/orders/" + encodeURIComponent(reference));

      if (response.status === 404) {
        renderProblem(
          "We can't find that order",
          "The reference in this link doesn't match anything we have.",
          null
        );
        return;
      }

      if (!response.ok) throw new Error("status " + response.status);

      body = await response.json();
    } catch (e) {
      // A transient network failure mid-poll is not worth a scary screen
      // while retries remain.
      if (polls < MAX_POLLS) {
        setTimeout(poll, POLL_MS);
      } else {
        renderProblem(
          "We couldn't reach our server",
          "Your payment is unaffected. Refresh this page in a moment.",
          null
        );
      }
      return;
    }

    const order = body.order;
    const workspace = body.workspace;

    if (order.status !== "paid") {
      renderSummary("pending-summary", order);
      show("pending");

      if (polls < MAX_POLLS) {
        setTimeout(poll, POLL_MS);
      } else {
        renderProblem(
          "We still haven't seen this payment",
          "If you completed it, reply to your receipt and we'll sort it out.",
          order
        );
      }
      return;
    }

    if (!workspace) {
      renderSummary("paid-summary", order);
      renderSteps([]);
      show("provisioning");
      if (polls < MAX_POLLS) setTimeout(poll, POLL_MS);
      return;
    }

    if (workspace.status === "failed") {
      renderProblem(
        "Payment went through, setup didn't",
        workspace.failure_reason ||
          "Your workspace didn't finish building. We've been notified.",
        order
      );
      return;
    }

    if (workspace.status === "ready") {
      renderReady(order, workspace);
      return;
    }

    renderSummary("paid-summary", order);
    renderSteps(workspace.steps || []);
    show("provisioning");

    if (polls < MAX_POLLS) {
      setTimeout(poll, POLL_MS);
    } else {
      renderProblem(
        "Setup is taking longer than it should",
        "Your payment is recorded. We'll finish this and email you.",
        order
      );
    }
  }

  if (!reference) {
    renderProblem(
      "This link is missing its reference",
      "Open the link from your receipt email and it will pick up from here.",
      null
    );
    return;
  }

  show("checking");
  poll();
})();
