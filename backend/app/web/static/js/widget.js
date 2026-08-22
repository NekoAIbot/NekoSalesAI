/* The embeddable widget — a customer's agent, on the customer's own site.
 *
 * One <script> tag is the whole integration:
 *
 *   <script src="https://nekosales.ai/static/js/widget.js"
 *           data-token="WIDGET_TOKEN" async></script>
 *
 * Constraints that shaped this file:
 *
 * It runs on someone else's page. So it declares no globals beyond one guard
 * flag, styles itself inside a shadow root so the host page's CSS cannot bleed
 * in and its own cannot leak out, and never touches the host's DOM beyond
 * appending a single container. A widget that restyled a customer's site would
 * be a support ticket on their busiest day.
 *
 * It never computes or displays a price it was not given. Same rule as the
 * storefront builder: the agent composes replies server-side from the config,
 * and this file renders what it is handed. There is no catalog here to disagree
 * with the server about.
 *
 * The token in data-token is public — it ships in page source. It authorises
 * starting a conversation and reading branding, nothing else. The secret API key
 * is never sent to a browser.
 */

(function () {
  "use strict";

  if (window.__nekoWidgetLoaded) return;
  window.__nekoWidgetLoaded = true;

  const script = document.currentScript;
  const token = script && script.getAttribute("data-token");

  if (!token) {
    // Console rather than anything visible: a misconfigured tag is the site
    // owner's problem to fix and their visitors should not be shown it.
    console.error("[NekoSalesAI] widget.js needs a data-token attribute.");
    return;
  }

  // Derived from where this script was loaded, so a self-hosted or staging
  // deployment works without a second setting to keep in sync.
  const origin = new URL(script.src, window.location.href).origin;
  const api = origin + "/api/v1/widget/" + encodeURIComponent(token);

  let conversation = null;
  let sending = false;
  let open = false;

  /* ---------- shell ---------- */

  const host = document.createElement("div");
  host.setAttribute("data-neko-widget", "");
  const root = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function style(accent) {
    const css = `
      :host { all: initial; }
      * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont,
          "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
      .launcher {
        position: fixed; right: 20px; bottom: 20px; z-index: 2147483000;
        display: flex; align-items: center; gap: 9px;
        padding: 13px 18px; border: 0; border-radius: 100px;
        background: ${accent}; color: #fff; font-size: 15px; font-weight: 500;
        cursor: pointer; box-shadow: 0 6px 24px rgba(0,0,0,.18);
        transition: transform 140ms cubic-bezier(.2,.8,.2,1);
      }
      .launcher:hover { transform: translateY(-1px); }
      .launcher:focus-visible { outline: 3px solid ${accent}; outline-offset: 3px; }
      .panel {
        position: fixed; right: 20px; bottom: 20px; z-index: 2147483000;
        display: none; flex-direction: column;
        width: 380px; max-width: calc(100vw - 40px);
        height: 560px; max-height: calc(100vh - 40px);
        background: #fff; border-radius: 16px; overflow: hidden;
        box-shadow: 0 12px 48px rgba(0,0,0,.22);
      }
      .panel[data-open="1"] { display: flex; }
      .head {
        display: flex; align-items: center; gap: 11px;
        padding: 14px 16px; background: ${accent}; color: #fff;
      }
      .head-text { flex: 1; min-width: 0; }
      .name { font-size: 15px; font-weight: 600; }
      .sub { font-size: 12px; opacity: .85; }
      .close {
        border: 0; background: transparent; color: #fff;
        font-size: 22px; line-height: 1; cursor: pointer; padding: 4px 6px;
      }
      .close:focus-visible { outline: 2px solid #fff; outline-offset: 2px; }
      .log {
        flex: 1; overflow-y: auto; padding: 16px;
        display: flex; flex-direction: column; gap: 10px; background: #fbfaf9;
      }
      .msg { max-width: 86%; padding: 10px 13px; border-radius: 13px;
             font-size: 14px; line-height: 1.5; white-space: pre-wrap;
             word-wrap: break-word; }
      .msg--agent { align-self: flex-start; background: #f0eeea; color: #17150f;
                    border-bottom-left-radius: 4px; }
      .msg--visitor { align-self: flex-end; background: ${accent}; color: #fff;
                      border-bottom-right-radius: 4px; }
      .dots { align-self: flex-start; display: flex; gap: 4px; padding: 12px 13px; }
      .dots i { width: 5px; height: 5px; border-radius: 50%; background: #8a8377;
                animation: p 1.3s ease-in-out infinite; }
      .dots i:nth-child(2) { animation-delay: .18s; }
      .dots i:nth-child(3) { animation-delay: .36s; }
      @keyframes p { 0%,100% { opacity: .35; } 50% { opacity: 1; } }
      .err { margin: 0 16px 10px; padding: 9px 12px; border-radius: 8px;
             background: #fbeceb; color: #9b2c23; font-size: 13px; }
      .form { display: flex; gap: 8px; padding: 12px; border-top: 1px solid #e6e2dc; }
      .input {
        flex: 1; padding: 10px 12px; border: 1px solid #d3cec6; border-radius: 8px;
        font-size: 14px; font-family: inherit; resize: none; max-height: 96px;
      }
      .input:focus { outline: none; border-color: ${accent};
                     box-shadow: 0 0 0 3px ${accent}22; }
      .send {
        border: 0; border-radius: 8px; padding: 0 16px; background: ${accent};
        color: #fff; font-size: 14px; font-weight: 500; cursor: pointer;
      }
      .send:disabled { opacity: .5; cursor: not-allowed; }
      .send:focus-visible { outline: 2px solid ${accent}; outline-offset: 2px; }
      @media (prefers-reduced-motion: reduce) {
        * { animation-duration: .01ms !important; transition-duration: .01ms !important; }
        .dots i { opacity: .6; }
      }
      @media (max-width: 480px) {
        .panel { right: 10px; bottom: 10px; width: calc(100vw - 20px); }
      }
    `;
    const tag = document.createElement("style");
    tag.textContent = css;
    return tag;
  }

  /* ---------- render ---------- */

  const nodes = {};

  function build(config) {
    root.appendChild(style(config.accent_color || "#1c5d43"));

    const launcher = el("button", "launcher");
    launcher.type = "button";
    launcher.setAttribute("aria-label", "Chat with " + config.agent_name);
    launcher.appendChild(el("span", null, "💬"));
    launcher.appendChild(el("span", null, "Chat"));

    const panel = el("div", "panel");
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "Chat with " + config.agent_name);

    const head = el("div", "head");
    const headText = el("div", "head-text");
    headText.appendChild(el("div", "name", config.agent_name));
    headText.appendChild(el("div", "sub", config.company_name));
    const close = el("button", "close", "×");
    close.type = "button";
    close.setAttribute("aria-label", "Close chat");
    head.appendChild(headText);
    head.appendChild(close);

    const log = el("div", "log");
    log.setAttribute("aria-live", "polite");

    const form = el("form", "form");
    const input = el("textarea", "input");
    input.rows = 1;
    input.placeholder = "Type a message…";
    input.setAttribute("aria-label", "Your message");
    const send = el("button", "send", "Send");
    send.type = "submit";
    form.appendChild(input);
    form.appendChild(send);

    panel.appendChild(head);
    panel.appendChild(log);
    panel.appendChild(form);

    root.appendChild(launcher);
    root.appendChild(panel);

    Object.assign(nodes, { launcher, panel, log, form, input, send, close });

    launcher.addEventListener("click", toggle);
    close.addEventListener("click", toggle);
    form.addEventListener("submit", submit);

    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        submit(event);
      }
    });

    // Escape closes, which is what a dialog is expected to do.
    panel.addEventListener("keydown", function (event) {
      if (event.key === "Escape") toggle();
    });
  }

  function addMessage(role, body) {
    const node = el("div", "msg msg--" + role, body);
    nodes.log.appendChild(node);
    nodes.log.scrollTop = nodes.log.scrollHeight;
    return node;
  }

  function showThinking() {
    const wrap = el("div", "dots");
    wrap.appendChild(el("i"));
    wrap.appendChild(el("i"));
    wrap.appendChild(el("i"));
    nodes.log.appendChild(wrap);
    nodes.log.scrollTop = nodes.log.scrollHeight;
    return wrap;
  }

  function showError(message) {
    clearError();
    const node = el("div", "err", message);
    nodes.err = node;
    nodes.form.before(node);
  }

  function clearError() {
    if (nodes.err) {
      nodes.err.remove();
      nodes.err = null;
    }
  }

  /* ---------- behaviour ---------- */

  function toggle() {
    open = !open;
    nodes.panel.setAttribute("data-open", open ? "1" : "0");
    nodes.launcher.style.display = open ? "none" : "";

    if (open) {
      nodes.input.focus();
      if (!conversation) startConversation();
    }
  }

  async function startConversation() {
    try {
      const response = await fetch(api + "/conversations", { method: "POST" });
      if (!response.ok) throw new Error("start failed");

      const body = await response.json();
      conversation = body.token;

      (body.messages || []).forEach(function (message) {
        addMessage(message.role === "visitor" ? "visitor" : "agent", message.body);
      });
    } catch (e) {
      showError("We couldn't start the chat. Please try again.");
    }
  }

  async function submit(event) {
    if (event && event.preventDefault) event.preventDefault();
    if (sending) return;

    const text = nodes.input.value.trim();
    if (!text) return;

    if (!conversation) {
      await startConversation();
      if (!conversation) return;
    }

    clearError();
    addMessage("visitor", text);
    nodes.input.value = "";

    sending = true;
    nodes.send.disabled = true;
    const thinking = showThinking();

    try {
      const response = await fetch(api + "/conversations/" + conversation + "/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: text }),
      });

      const body = await response.json().catch(function () { return null; });
      thinking.remove();

      if (!response.ok) {
        // A refusal from the server is written to be read, so it is shown as
        // written rather than softened into a retry prompt.
        showError(
          (body && typeof body.detail === "string" && body.detail) ||
            "That didn't send. Please try again."
        );
        return;
      }

      addMessage("agent", body.body);
    } catch (e) {
      thinking.remove();
      showError("We couldn't reach the server. Please try again.");
    } finally {
      sending = false;
      nodes.send.disabled = false;
      nodes.input.focus();
    }
  }

  /* ---------- boot ---------- */

  fetch(api + "/config")
    .then(function (response) {
      if (!response.ok) throw new Error("config " + response.status);
      return response.json();
    })
    .then(function (config) {
      build(config);
      document.body.appendChild(host);
    })
    .catch(function () {
      // An unknown or not-yet-ready token renders nothing at all. The
      // alternative — a launcher that opens onto an error — is worse for the
      // customer's visitors than no widget.
      console.error("[NekoSalesAI] widget could not load its configuration.");
    });
})();
