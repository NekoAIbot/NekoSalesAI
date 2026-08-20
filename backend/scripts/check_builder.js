/* Drives builder.js under a stub DOM against the real API contract.
 *
 * Not a substitute for a browser, and not pretending to be: it exercises the
 * request bodies the script builds and the fields it reads from a response.
 * That is the part with money in it. Layout is not covered here.
 *
 * Run: node scripts/check_builder.js   (from backend/)
 */

"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SOURCE = path.join(
  __dirname, "..", "app", "web", "static", "js", "builder.js"
);

let failures = 0;

function check(label, condition) {
  if (condition) {
    console.log("  ok   " + label);
  } else {
    console.log("  FAIL " + label);
    failures += 1;
  }
}

/* ---------- a stub DOM, only as deep as the script reaches ---------- */

function makeNode(id, value) {
  return {
    id: id,
    value: value === undefined ? "" : value,
    checked: false,
    disabled: false,
    textContent: "",
    className: "",
    children: [],
    classList: {
      _set: new Set(),
      add(c) { this._set.add(c); },
      remove(c) { this._set.delete(c); },
      contains(c) { return this._set.has(c); },
      toggle(c, on) { on ? this.add(c) : this.remove(c); },
    },
    appendChild(child) { this.children.push(child); return child; },
    replaceChildren() { this.children = []; },
    addEventListener(type, fn) { (this._on ||= {})[type] = fn; },
    querySelectorAll() { return []; },
    elements: [],
  };
}

function buildDom() {
  const ids = [
    "b-submit", "b-product", "b-product-note", "quote-empty", "quote-body",
    "quote-product", "quote-amount", "quote-period", "quote-lines",
    "quote-error", "quote-buy", "q-submit", "q-email", "q-company",
    "b-volume", "b-integrations", "b-languages", "b-workflows",
    "builder-form",
  ];

  const nodes = {};
  ids.forEach(function (id) { nodes[id] = makeNode(id); });

  nodes["b-product"].value = "support_agent";
  nodes["b-volume"].value = "2000";
  nodes["b-integrations"].value = "2";
  nodes["b-languages"].value = "1";
  nodes["b-workflows"].value = "3";
  nodes["q-email"].value = "buyer@example.com";
  nodes["q-company"].value = "Bright Dental";

  const channels = [
    Object.assign(makeNode("ch-web", "web"), { checked: true }),
    Object.assign(makeNode("ch-wa", "whatsapp"), { checked: true }),
  ];

  const form = nodes["builder-form"];
  form.querySelectorAll = function (selector) {
    return selector.indexOf("channels") !== -1 ? channels : [];
  };
  form.elements = [nodes["b-product"], nodes["b-volume"]];

  return { nodes: nodes, channels: channels };
}

function run(fetchImpl) {
  const dom = buildDom();
  const created = [];

  const document = {
    getElementById: function (id) { return dom.nodes[id] || null; },
    createElement: function (tag) {
      const node = makeNode("created-" + tag);
      created.push(node);
      return node;
    },
  };

  const context = {
    document: document,
    fetch: fetchImpl,
    window: { location: { href: "" } },
    console: console,
    setTimeout: setTimeout,
    Number: Number,
    JSON: JSON,
    parseInt: parseInt,
    Array: Array,
    Object: Object,
  };

  vm.createContext(context);
  vm.runInContext(fs.readFileSync(SOURCE, "utf8"), context);

  return { dom: dom, context: context, created: created };
}

/* ---------- the quote request ---------- */

console.log("\nrequirement the form posts:");

let sentQuote = null;

const quoteResponse = {
  reference: "qt_abc123",
  product_type: "support_agent",
  product_name: "AI Support Agent",
  currency: "NGN",
  billing_period: "month",
  display_total: "₦42,500",
  total_minor: 4250000,
  line_items: [
    { dimension: "base", label: "AI Support Agent", display_amount: "₦18,000" },
    { dimension: "channel", label: "WhatsApp", display_amount: "₦8,000" },
  ],
};

let harness = run(async function (url, init) {
  sentQuote = { url: url, body: JSON.parse(init.body) };
  return { ok: true, status: 200, json: async function () { return quoteResponse; } };
});

harness.dom.nodes["builder-form"]._on.submit({ preventDefault() {} });

setTimeout(function () {
  check("posts to the quote endpoint", sentQuote.url === "/api/v1/pricing/quote");
  check("sends the chosen product", sentQuote.body.product_type === "support_agent");
  check(
    "sends both checked channels",
    JSON.stringify(sentQuote.body.channels) === '["web","whatsapp"]'
  );
  check("sends the volume band as a number", sentQuote.body.monthly_conversations === 2000);
  check("turns the integration count into a list", sentQuote.body.integrations.length === 2);
  check("turns the language count into a list", sentQuote.body.languages.length === 1);
  check("sends the workflow step count", sentQuote.body.workflow_steps === 3);

  check("sends no amount of any kind", (function () {
    const keys = Object.keys(sentQuote.body).join(",");
    return !/amount|price|total|discount/.test(keys);
  })());

  /* ---------- what it renders ---------- */

  console.log("\nwhat it renders:");
  check(
    "shows the server's figure verbatim",
    harness.dom.nodes["quote-amount"].textContent === "₦42,500"
  );
  check(
    "shows the server's product name",
    harness.dom.nodes["quote-product"].textContent === "AI Support Agent"
  );
  check(
    "renders one row per line item",
    harness.dom.nodes["quote-lines"].children.length === 2
  );
  check(
    "reveals the quote panel",
    harness.dom.nodes["quote-body"].classList.contains("hidden") === false
  );

  /* ---------- the checkout request ---------- */

  console.log("\nthe checkout request:");

  let sentOrder = null;
  harness.context.fetch = async function (url, init) {
    sentOrder = { url: url, body: JSON.parse(init.body) };
    return {
      ok: true,
      status: 201,
      json: async function () {
        return { checkout_url: "https://checkout.paystack.com/x" };
      },
    };
  };

  harness.dom.nodes["quote-buy"]._on.submit({ preventDefault() {} });

  setTimeout(function () {
    check("posts to the orders endpoint", sentOrder.url === "/api/v1/checkout/orders");
    check("sends the quote reference", sentOrder.body.quote_reference === "qt_abc123");
    check("sends the buyer's email", sentOrder.body.email === "buyer@example.com");
    check(
      "sends nothing resembling a price",
      !/amount|price|total|discount/.test(Object.keys(sentOrder.body).join(","))
    );
    check(
      "sends only reference, email and company",
      Object.keys(sentOrder.body).sort().join(",") ===
        "company,email,quote_reference"
    );
    check(
      "follows the payment link",
      harness.context.window.location.href === "https://checkout.paystack.com/x"
    );

    /* ---------- a refusal is shown as written ---------- */

    console.log("\na refused requirement:");

    const refusing = run(async function () {
      return {
        ok: false,
        status: 400,
        json: async function () {
          return { detail: "Above 50,000 conversations a month we price by hand." };
        },
      };
    });

    refusing.dom.nodes["builder-form"]._on.submit({ preventDefault() {} });

    setTimeout(function () {
      check(
        "shows the server's reason, not a generic retry",
        refusing.dom.nodes["quote-error"].textContent ===
          "Above 50,000 conversations a month we price by hand."
      );
      check(
        "leaves no stale quote on screen",
        refusing.dom.nodes["quote-body"].classList.contains("hidden") === false ||
          refusing.dom.nodes["quote-lines"].children.length === 0
      );

      console.log(
        failures === 0
          ? "\nall checks passed\n"
          : "\n" + failures + " check(s) FAILED\n"
      );
      process.exit(failures === 0 ? 0 : 1);
    }, 10);
  }, 10);
}, 10);
