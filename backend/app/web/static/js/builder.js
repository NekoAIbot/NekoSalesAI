/* The product builder — describe an AI, get a price, buy it.
 *
 * The one rule that matters in this file: **it never computes a price.** It
 * collects a requirement, posts it, and renders whatever the server returns.
 * There is no arithmetic here, no price table, and no total assembled from
 * parts. If this file could add up a quote it could also disagree with the
 * server about one, and the version the buyer saw is the version they would
 * reasonably expect to be charged.
 *
 * Buying works the same way. The quote reference from the server is the only
 * thing sent to the checkout — no amount travels with it, because the checkout
 * re-prices the stored requirement server-side anyway (see app.pricing.quotes).
 * So a tampered reference or an edited DOM cannot move the figure.
 *
 * The line items are shown because a buyer who asks "why is it this much"
 * deserves the same breakdown the total was summed from, not a single number.
 */

(function () {
  "use strict";

  const form = document.getElementById("builder-form");
  if (!form) return;

  const QUOTE_URL = "/api/v1/pricing/quote";
  const ORDER_URL = "/api/v1/checkout/orders";

  // The language every product ships with. The form collects languages *beyond*
  // this one, matching the field's own note.
  const BASE_LANGUAGE = "English";

  const els = {
    submit: document.getElementById("b-submit"),
    product: document.getElementById("b-product"),
    productNote: document.getElementById("b-product-note"),
    empty: document.getElementById("quote-empty"),
    body: document.getElementById("quote-body"),
    productLabel: document.getElementById("quote-product"),
    amount: document.getElementById("quote-amount"),
    period: document.getElementById("quote-period"),
    lines: document.getElementById("quote-lines"),
    error: document.getElementById("quote-error"),
    buyForm: document.getElementById("quote-buy"),
    buySubmit: document.getElementById("q-submit"),
    email: document.getElementById("q-email"),
    company: document.getElementById("q-company"),
  };

  // What the server said, verbatim. Only the reference is ever sent back.
  let quote = null;

  // Written by the server's own product list, so it cannot describe a product
  // that does not exist.
  const PRODUCT_NOTES = {
    sales_agent:
      "Answers buyers, quotes your published prices and takes payment.",
    support_agent:
      "Answers questions from your own knowledge. It will not quote prices " +
      "or take payment — those go to your team.",
  };

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function showError(message) {
    els.error.textContent = message;
    els.error.classList.remove("hidden");
  }

  /* What to show the buyer when the server refuses.
   *
   * A refusal we planned for is a 400 whose detail is a sentence written to be
   * read ("Above 50,000 conversations a month we price by hand"), and it is
   * shown exactly as written. A 422 is different: its detail is a *list* of
   * field errors from the schema layer, phrased for whoever is calling the API.
   * Assigning that list to textContent renders "[object Object]", so it is
   * deliberately not shown — a malformed request is our bug to fix, not
   * something the buyer can act on, and they get the generic line instead.
   */
  function errorText(body, fallback) {
    const detail = body && body.detail;
    if (typeof detail === "string" && detail) return detail;
    return fallback;
  }

  function clearError() {
    els.error.textContent = "";
    els.error.classList.add("hidden");
  }

  function describeProduct() {
    const note = PRODUCT_NOTES[els.product.value] || "";
    els.productNote.textContent = note;
  }

  /* Collect the form as a requirement.
   *
   * Counts become lists of placeholder names because the engine prices the
   * *number* of integrations and languages, not which ones. Naming them here
   * would imply we had scoped specific systems.
   */
  function readRequirement() {
    const channels = Array.from(
      form.querySelectorAll('input[name="channels"]:checked')
    ).map(function (input) { return input.value; });

    // A whole number from a field, or 0 if it cannot be read. The guard is not
    // decoration: parseInt("") is NaN, JSON.stringify(NaN) is null, and the API
    // rejects null as a type error the buyer can do nothing about.
    const wholeNumber = function (id) {
      const raw = parseInt(document.getElementById(id).value, 10);
      return Number.isFinite(raw) && raw > 0 ? raw : 0;
    };

    const repeat = function (n, prefix) {
      const out = [];
      for (let i = 1; i <= n; i += 1) out.push(prefix + " " + i);
      return out;
    };

    /* The field asks for languages *beyond* the first, but the engine prices the
     * whole list and treats one language as included in the base. So the
     * included language travels with the extras. Sending only the extras made
     * the engine read one of them as the included one, and every buyer was
     * quoted one language cheaper than they asked for.
     */
    const languages = [BASE_LANGUAGE].concat(
      repeat(wholeNumber("b-languages"), "Language")
    );

    return {
      product_type: els.product.value,
      channels: channels,
      integrations: repeat(wholeNumber("b-integrations"), "System"),
      languages: languages,
      monthly_conversations: wholeNumber("b-volume"),
      workflow_steps: wholeNumber("b-workflows"),
    };
  }

  function renderQuote(body) {
    els.productLabel.textContent = body.product_name;

    // Straight from the server. Deliberately not reformatted — reformatting is
    // arithmetic, and arithmetic here is a second opinion about the price.
    els.amount.textContent = body.display_total;
    els.period.textContent = "/ " + body.billing_period;

    els.lines.replaceChildren();

    body.line_items.forEach(function (item) {
      const row = el("li", "quote-line");
      row.appendChild(el("span", "quote-line-label", item.label));
      row.appendChild(el("span", "quote-line-amount", item.display_amount));
      els.lines.appendChild(row);
    });

    els.empty.classList.add("hidden");
    els.body.classList.remove("hidden");
  }

  async function price(event) {
    event.preventDefault();
    clearError();

    const requirement = readRequirement();

    if (requirement.channels.length === 0) {
      showError("Pick at least one place for it to answer.");
      return;
    }

    els.submit.disabled = true;
    els.submit.textContent = "Pricing…";

    try {
      const response = await fetch(QUOTE_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requirement),
      });

      const body = await response.json().catch(function () { return null; });

      if (!response.ok) {
        // A refusal carries its reason and is shown as written: the server
        // declines to quote some requirements on purpose (volumes it has not
        // costed, channels it cannot serve) and softening that into "try
        // again" would hide a real answer.
        showError(errorText(
          body, "We couldn't price that. Adjust something and try again."
        ));
        return;
      }

      quote = body;
      renderQuote(body);
    } catch (e) {
      showError("We couldn't reach our server. Try again in a moment.");
    } finally {
      els.submit.disabled = false;
      els.submit.textContent = "Price it";
    }
  }

  async function buy(event) {
    event.preventDefault();
    clearError();

    if (!quote || !quote.reference) {
      showError("Price it first, then continue.");
      return;
    }

    const email = els.email.value.trim();
    if (!email) {
      showError("We need an email to send the receipt and login to.");
      return;
    }

    els.buySubmit.disabled = true;
    els.buySubmit.textContent = "Starting…";

    try {
      const response = await fetch(ORDER_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // The reference and the buyer. No amount: the server re-prices the
        // stored requirement, so there is nothing useful to send and nothing
        // here that could change the charge.
        body: JSON.stringify({
          quote_reference: quote.reference,
          email: email,
          company: els.company.value.trim() || null,
        }),
      });

      const body = await response.json().catch(function () { return null; });

      if (!response.ok) {
        showError(errorText(
          body,
          "We couldn't start that checkout. Nothing has been charged."
        ));
        return;
      }

      if (!body.checkout_url) {
        showError(
          "That order was created but we didn't get a payment link. " +
            "Nothing has been charged — email us and we'll finish it."
        );
        return;
      }

      window.location.href = body.checkout_url;
    } catch (e) {
      showError(
        "We couldn't reach our server. Nothing has been charged."
      );
    } finally {
      els.buySubmit.disabled = false;
      els.buySubmit.textContent = "Continue to payment";
    }
  }

  /* Any edit to the requirement invalidates the quote on screen.
   *
   * Otherwise a buyer changes the volume, sees the old figure still sitting
   * there, and clicks continue believing that is the price. The server would
   * charge the older requirement's amount — correctly, since that is what the
   * reference names — but it is not what they thought they were buying.
   */
  function invalidate() {
    if (!quote) return;
    quote = null;
    els.body.classList.add("hidden");
    els.empty.classList.remove("hidden");
    clearError();
  }

  form.addEventListener("submit", price);
  els.buyForm.addEventListener("submit", buy);
  els.product.addEventListener("change", describeProduct);

  Array.from(form.elements).forEach(function (input) {
    if (input === els.submit) return;
    input.addEventListener("change", invalidate);
  });

  describeProduct();
})();
