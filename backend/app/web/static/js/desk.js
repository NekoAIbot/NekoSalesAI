/* Sales desk client.
 *
 * Talks to /api/v1/sales-desk with a bearer token held in sessionStorage —
 * cleared when the tab closes, and never written to localStorage where it
 * would outlive the session on a shared machine.
 *
 * As on the storefront, all buyer-supplied text goes in through textContent.
 * The desk renders strings a stranger typed, so treating any of it as markup
 * would turn the queue into an XSS vector aimed at the team.
 */

(function () {
  "use strict";

  const API = "/api/v1";
  const TOKEN_KEY = "nekosales.desk.token";

  const signinView = document.getElementById("signin-view");
  const deskView = document.getElementById("desk-view");
  const signinForm = document.getElementById("signin-form");
  const signinError = document.getElementById("signin-error");
  const signOutBtn = document.getElementById("sign-out");
  const deskUser = document.getElementById("desk-user");

  const statsBox = document.getElementById("desk-stats");
  const approvalsBox = document.getElementById("approvals");
  const conversationsBox = document.getElementById("conversations");
  const pendingLabel = document.getElementById("pending-label");
  const conversationLabel = document.getElementById("conversation-label");

  const transcriptPanel = document.getElementById("transcript-panel");
  const transcriptBox = document.getElementById("transcript");

  let token = sessionStorage.getItem(TOKEN_KEY);

  const STAGE_LABELS = {
    greeting: "New",
    discovery: "Discovery",
    qualified: "Qualified",
    negotiating: "Negotiating",
    awaiting_approval: "Waiting on you",
    ready_to_buy: "Ready to buy",
    closed_won: "Won",
    handed_off: "Handed off",
  };

  const HOT_STAGES = ["ready_to_buy", "closed_won"];
  const WAIT_STAGES = ["awaiting_approval", "negotiating"];

  async function api(path, options) {
    const config = Object.assign({headers: {}}, options || {});
    config.headers["Content-Type"] = "application/json";
    if (token) config.headers["Authorization"] = "Bearer " + token;

    const response = await fetch(API + path, config);

    if (response.status === 401 || response.status === 403) {
      signOut();
      throw new Error("Your session expired. Sign in again.");
    }

    if (!response.ok) {
      let detail = "Request failed.";
      try {
        const body = await response.json();
        if (body && typeof body.detail === "string") detail = body.detail;
      } catch (e) { /* keep the generic message */ }
      throw new Error(detail);
    }

    if (response.status === 204) return null;
    return response.json();
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function formatDate(value) {
    if (!value) return "";
    const date = new Date(value);
    if (isNaN(date)) return "";
    return date.toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  }

  /* ---------- sign in ---------- */

  signinForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    signinError.classList.add("hidden");

    try {
      const result = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: document.getElementById("signin-email").value,
          password: document.getElementById("signin-password").value,
        }),
      });

      token = result.access_token;
      sessionStorage.setItem(TOKEN_KEY, token);
      await enterDesk();
    } catch (e) {
      signinError.textContent = e.message;
      signinError.classList.remove("hidden");
    }
  });

  function signOut() {
    token = null;
    sessionStorage.removeItem(TOKEN_KEY);
    deskView.classList.add("hidden");
    signinView.classList.remove("hidden");
    signOutBtn.classList.add("hidden");
    deskUser.textContent = "";
  }

  signOutBtn.addEventListener("click", signOut);

  async function enterDesk() {
    const me = await api("/auth/me", {method: "GET"});

    deskUser.textContent = me.email;
    signinView.classList.add("hidden");
    deskView.classList.remove("hidden");
    signOutBtn.classList.remove("hidden");

    await refresh();
  }

  /* ---------- rendering ---------- */

  function renderStats(summary) {
    statsBox.replaceChildren();

    const cards = [
      {value: summary.pending_approvals, label: "Waiting on you",
       alert: summary.pending_approvals > 0},
      {value: summary.conversations, label: "Conversations"},
      {value: summary.resolved_approvals, label: "Decisions made"},
    ];

    cards.forEach(function (card) {
      const node = el("div", "stat" + (card.alert ? " stat--alert" : ""));
      node.appendChild(el("div", "stat-value", String(card.value)));
      node.appendChild(el("div", "stat-label", card.label));
      statsBox.appendChild(node);
    });
  }

  function renderApprovals(requests) {
    approvalsBox.replaceChildren();

    const pending = requests.filter(function (r) {
      return r.status === "pending";
    });

    pendingLabel.textContent = pending.length
      ? pending.length + " pending"
      : "All clear";

    if (!requests.length) {
      approvalsBox.appendChild(el(
        "div", "empty",
        "Nothing needs a decision. The rep has stayed inside the catalog."
      ));
      return;
    }

    // Pending first: this list is a work queue, not a history.
    const ordered = pending.concat(requests.filter(function (r) {
      return r.status !== "pending";
    }));

    ordered.forEach(function (request) {
      approvalsBox.appendChild(buildApproval(request));
    });
  }

  function buildApproval(request) {
    const card = el("div", "approval" +
      (request.status === "pending" ? "" : " approval--resolved"));

    const top = el("div", "approval-top");
    top.appendChild(el("div", "approval-subject", request.subject));
    top.appendChild(el("span", "badge badge--" + request.status,
      request.status));
    card.appendChild(top);

    card.appendChild(el("div", "quote", request.requested));

    if (request.status === "pending") {
      const field = el("label", "field");
      field.appendChild(el("span", null, "What should the buyer be told?"));

      const textarea = el("textarea");
      textarea.placeholder =
        "Write the exact words the buyer will see. They are sent verbatim.";
      field.appendChild(textarea);
      card.appendChild(field);

      const error = el("div", "chat-error hidden");
      error.style.borderRadius = "6px";
      error.style.marginBottom = "10px";
      card.appendChild(error);

      const actions = el("div", "approval-actions");
      const approve = el("button", "btn", "Approve & send");
      const decline = el("button", "btn btn--danger", "Decline & explain");

      actions.appendChild(approve);
      actions.appendChild(decline);
      card.appendChild(actions);

      function decide(shouldApprove) {
        const resolution = textarea.value.trim();

        if (!resolution) {
          // Enforced on the server too; caught here so the human is not
          // bounced by a 422 for something the form can tell them now.
          error.textContent =
            "Write what the buyer should be told — it is sent as-is.";
          error.classList.remove("hidden");
          textarea.focus();
          return;
        }

        approve.disabled = true;
        decline.disabled = true;

        api("/sales-desk/approvals/" + request.id + "/decide", {
          method: "POST",
          body: JSON.stringify({approve: shouldApprove, resolution: resolution}),
        }).then(refresh).catch(function (e) {
          error.textContent = e.message;
          error.classList.remove("hidden");
          approve.disabled = false;
          decline.disabled = false;
        });
      }

      approve.addEventListener("click", function () { decide(true); });
      decline.addEventListener("click", function () { decide(false); });
    } else if (request.resolution) {
      card.appendChild(el("div", "resolution-note", request.resolution));
      card.appendChild(el("div", "approval-meta",
        "Answered " + formatDate(request.resolved_at)));
    }

    return card;
  }

  function renderConversations(conversations) {
    conversationsBox.replaceChildren();

    conversationLabel.textContent = conversations.length
      ? conversations.length + " total"
      : "";

    if (!conversations.length) {
      conversationsBox.appendChild(el(
        "div", "empty", "No conversations yet. Open the landing page and " +
        "talk to the rep to see one here."
      ));
      return;
    }

    conversations.forEach(function (conversation) {
      const row = el("button", "conv");
      row.type = "button";

      const left = el("div");
      left.appendChild(el("div", "conv-who",
        conversation.visitor_name ||
        conversation.visitor_email ||
        "Anonymous visitor"));

      const parts = [];
      if (conversation.visitor_company) parts.push(conversation.visitor_company);
      if (conversation.interested_plan_code) {
        parts.push(conversation.interested_plan_code);
      }
      parts.push(formatDate(conversation.updated_at));

      left.appendChild(el("div", "conv-sub", parts.join(" · ")));
      row.appendChild(left);

      let pillClass = "stage-pill";
      if (HOT_STAGES.indexOf(conversation.stage) !== -1) {
        pillClass += " stage-pill--hot";
      } else if (WAIT_STAGES.indexOf(conversation.stage) !== -1) {
        pillClass += " stage-pill--wait";
      }

      row.appendChild(el("span", pillClass,
        STAGE_LABELS[conversation.stage] || conversation.stage));

      row.addEventListener("click", function () {
        openTranscript(conversation.id);
      });

      conversationsBox.appendChild(row);
    });
  }

  async function openTranscript(conversationId) {
    try {
      const data = await api("/sales-desk/conversations/" + conversationId, {
        method: "GET",
      });

      transcriptBox.replaceChildren();

      data.messages.forEach(function (message) {
        if (!message.body) return;

        const wrapper = el("div", "msg msg--" + message.role);

        if (message.role === "human") {
          wrapper.appendChild(el("div", "msg-tag", "Answered by a person"));
        }

        wrapper.appendChild(el("div", "msg-body", message.body));

        if (message.role === "agent" && message.reasoning) {
          wrapper.appendChild(buildReasoning(message.reasoning));
        }

        transcriptBox.appendChild(wrapper);
      });

      transcriptPanel.classList.remove("hidden");
      transcriptPanel.scrollIntoView({behavior: "smooth", block: "nearest"});
    } catch (e) {
      alert(e.message);
    }
  }

  function buildReasoning(reasoning) {
    const details = el("details", "why");
    details.appendChild(el("summary", null,
      reasoning.escalated ? "Why it escalated" : "Why it said this"));

    const body = el("div", "why-body");

    body.appendChild(reasoningRow("Rule", reasoning.rule));

    if (reasoning.signals && reasoning.signals.length) {
      body.appendChild(reasoningRow("Signals", reasoning.signals.join(" · ")));
    }

    body.appendChild(reasoningRow("Source",
      (reasoning.grounded_in && reasoning.grounded_in.length)
        ? reasoning.grounded_in.join(" · ")
        : "No product claim made"));

    details.appendChild(body);
    return details;
  }

  function reasoningRow(key, value) {
    const row = el("div", "why-row");
    row.appendChild(el("span", "why-key", key));

    const val = el("span", "why-val");
    val.appendChild(el("code", null, value));
    row.appendChild(val);

    return row;
  }

  document.getElementById("close-transcript")
    .addEventListener("click", function () {
      transcriptPanel.classList.add("hidden");
    });

  async function refresh() {
    try {
      const [summary, approvals, conversations] = await Promise.all([
        api("/sales-desk/summary", {method: "GET"}),
        api("/sales-desk/approvals", {method: "GET"}),
        api("/sales-desk/conversations", {method: "GET"}),
      ]);

      renderStats(summary);
      renderApprovals(approvals);
      renderConversations(conversations);
    } catch (e) {
      if (token) console.error(e);
    }
  }

  if (token) {
    enterDesk().catch(signOut);
  }
})();
