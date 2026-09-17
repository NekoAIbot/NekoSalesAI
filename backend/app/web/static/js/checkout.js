/* Checkout return — the screen a buyer lands on with their money already gone.
 *
 * Two rules govern everything here.
 *
 * 1. The page reports server state and never anticipates it. There are
 *    separate visible states for checking, pending, processing, success,
 *    failed, cancelled, and error — and the page shows whichever one the API
 *    says is true. A screen that shows "confirmed" before the server has
 *    confirmed is lying at the exact moment a buyer is least able to tolerate
 *    it.
 *
 * 2. A payment is only "success" when Paystack has verified it. The browser
 *    returning from Paystack is NOT proof of payment — it just means the buyer
 *    left the payment page. Only the webhook/server-to-server confirmation counts.
 *
 * Credentials are rendered with textContent and are never written to storage
 * or the URL. They arrive once and live only in the DOM.
 */

(function () {
  "use strict";

  const API = "/api/v1/checkout";

  const params = new URLSearchParams(window.location.search);
  const reference = params.get("reference") || params.get("trxref");
  const status = params.get("status"); // Paystack may pass this back

  const states = {
    checking: document.getElementById("state-checking"),
    success: document.getElementById("state-success"),
    pending: document.getElementById("state-pending"),
    processing: document.getElementById("state-processing"),
    failed: document.getElementById("state-failed"),
    cancelled: document.getElementById("state-cancelled"),
    verificationError: document.getElementById("state-verification-error"),
    error: document.getElementById("state-error"),
  };

  const successSteps = document.getElementById("success-steps");
  const successCredentials = document.getElementById("success-credentials");
  const processingSteps = document.getElementById("processing-steps");

  // Poll steadily rather than backing off: provisioning is measured in
  // hundreds of milliseconds, and the wait that matters is the buyer's bank
  // confirming, which is not something a longer interval helps with.
  const POLL_MS = 1500;
  const MAX_POLLS = 80;   // two minutes, then stop and say so

  let polls = 0;
  let credentialsShown = false;

  function show(name) {
    Object.keys(states).forEach(function (key) {
      if (states[key]) {
        states[key].classList.toggle("hidden", key !== name);
      }
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

  function renderSteps(target, steps) {
    target.replaceChildren();

    steps.forEach(function (step) {
      const item = el("li", "step" + (step.done ? " step--done" : ""));
      item.appendChild(el("span", "step-mark", step.done ? "✓" : "•"));
      item.appendChild(el("span", "step-label", step.label));
      target.appendChild(item);
    });
  }

  function renderCredentials(workspace) {
    // The API returns these exactly once — on the response that created them.
    // A later poll returns null, so anything already on screen must survive.
    if (credentialsShown) return;
    if (!workspace.api_key && !workspace.temporary_password) return;

    successCredentials.classList.remove("hidden");

    if (workspace.api_key) {
      const keyBox = el("div");
      keyBox.appendChild(el("div", "cred-label", "API key"));
      keyBox.appendChild(el("code", "cred-value", workspace.api_key));
      successCredentials.appendChild(keyBox);
    }

    if (workspace.temporary_password) {
      const passBox = el("div");
      passBox.appendChild(el("div", "cred-label", "Temporary password"));
      passBox.appendChild(el("code", "cred-value", workspace.temporary_password));
      successCredentials.appendChild(passBox);
    }

    credentialsShown = true;
  }

  function renderSuccess(order, workspace) {
    renderSummary("success-summary", order);
    renderCredentials(workspace);
    show("success");
  }

  function renderProcessing(order, workspace) {
    renderSummary("processing-summary", order);
    renderSteps(processingSteps, workspace.steps || []);
    show("processing");
  }

  function renderPending(order) {
    renderSummary("pending-summary", order);
    show("pending");
  }

  function renderFailed(order) {
    if (order) renderSummary("cancelled-summary", order);
    show("failed");
  }

  function renderCancelled(order) {
    if (order) renderSummary("cancelled-summary", order);
    show("cancelled");
  }

  function renderVerificationError(order) {
    if (order) renderSummary("error-summary", order);
    show("verificationError");
  }

  function renderError(title, line, order) {
    document.getElementById("error-title").textContent = title;
    document.getElementById("error-line").textContent = line;
    if (order) renderSummary("error-summary-generic", order);
    show("error");
  }

  async function poll() {
    polls += 1;

    let body;
    try {
      const response = await fetch(API + "/orders/" + encodeURIComponent(reference));

      if (response.status === 404) {
        renderError(
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
        renderVerificationError(null);
      }
      return;
    }

    const order = body.order;
    const workspace = body.workspace;

    // Payment not yet confirmed
    if (order.status !== "paid") {
      renderPending(order);

      if (polls < MAX_POLLS) {
        setTimeout(poll, POLL_MS);
      } else {
        renderVerificationError(order);
      }
      return;
    }

    // Payment confirmed — now check provisioning status
    if (!workspace) {
      renderProcessing(order, { steps: [] });
      if (polls < MAX_POLLS) setTimeout(poll, POLL_MS);
      return;
    }

    if (workspace.status === "failed") {
      renderError(
        "Payment went through, setup didn't",
        workspace.failure_reason || "Your workspace didn't finish building. We've been notified.",
        order
      );
      return;
    }

    if (workspace.status === "ready") {
      renderSuccess(order, workspace);
      return;
    }

    // Still provisioning
    renderProcessing(order, workspace);

    if (polls < MAX_POLLS) {
      setTimeout(poll, POLL_MS);
    } else {
      renderVerificationError(order);
    }
  }

  // Handle Paystack return status if present
  if (status === "cancelled") {
    show("cancelled");
    return;
  }

  if (!reference) {
    renderError(
      "This link is missing its reference",
      "Open the link from your receipt email and it will pick up from here.",
      null
    );
    return;
  }

  show("checking");
  poll();
})();
