/* ================================================================
   builder.js — Floating Nera configurator with live authoritative pricing
   Prices come from /api/v1/pricing/quote, the same engine as checkout.
   ================================================================ */

(function () {
  "use strict";

  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var form = document.getElementById("builder-form");
  if (!form) return;

  // ---- DOM refs ----
  var productRadios = form.querySelectorAll("[data-builder-product]");
  var channelChecks = form.querySelectorAll("[data-builder-channel]");
  var volumePresets = document.querySelectorAll(".builder-volume-preset");
  var volumeInput = form.querySelector("#f-volume");
  var volumeQty = document.getElementById("vol-qty");
  var volumeTotal = document.getElementById("vol-total");
  var integCount = document.getElementById("integ-count");
  var integrationChecks = form.querySelectorAll("[data-builder-integration]");
  var languageChecks = form.querySelectorAll("[data-builder-language]");
  var quoteLines = document.querySelector("[data-quote-lines]");
  var quoteTotal = document.querySelector("[data-quote-total]");
  var quoteStatus = document.querySelector("[data-quote-status]");
  var submitBtn = document.getElementById("b-submit");
  var emailInput = document.querySelector("#f-email");

  var previewTimer = null;
  var lastReference = null;
  var lastPayload = null;
  var requestId = 0;

  function formatPrice(amountMinor) {
    if (amountMinor === null || amountMinor === undefined) return "\u2014";
    var n = amountMinor / 100;
    return "\u20A6" + n.toLocaleString("en-NG", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  }

  // ---- Volume control ----
  function updateVolumeTotal() {
    if (!volumeInput || !volumeQty) return;
    var vol = parseInt(volumeInput.value, 10) || 0;
    volumeQty.textContent = vol.toLocaleString("en-NG");
    // Update preset highlight
    volumePresets.forEach(function (b) {
      var bvol = parseInt(b.getAttribute("data-vol"), 10);
      if (bvol === vol) {
        b.classList.add("is-selected");
      } else {
        b.classList.remove("is-selected");
      }
    });
  }

  volumePresets.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var vol = parseInt(btn.getAttribute("data-vol"), 10);
      if (isNaN(vol)) return;
      volumeInput.value = vol;
      updateVolumeTotal();
      schedulePreview();
    });
  });

  if (volumeInput) {
    volumeInput.addEventListener("input", function () {
      updateVolumeTotal();
      schedulePreview();
    });
  }

  // ---- Integration counter ----
  function updateIntegCount() {
    if (!integCount) return;
    var checked = form.querySelectorAll("[data-builder-integration]:checked");
    integCount.textContent = checked.length;
  }

  // ---- Build payload from form ----
  function buildPayload() {
    var product = form.querySelector("input[name=\"product\"]:checked");
    var channels = Array.prototype.slice.call(
      form.querySelectorAll("input[name=\"channels\"]:checked")
    ).map(function (c) { return c.value; });
    var volume = volumeInput ? parseInt(volumeInput.value, 10) || 500 : 500;
    var languages = Array.prototype.slice.call(
      form.querySelectorAll("input[name=\"languages\"]:checked")
    ).map(function (l) { return l.value; });
    var integrations = Array.prototype.slice.call(
      integrationChecks
    ).filter(function (c) { return c.checked; }).map(function (c) { return c.value; });

    return {
      product_type: product ? product.value : "sales_agent",
      channels: channels.length ? channels : ["web"],
      monthly_conversations: volume,
      integrations: integrations,
      languages: languages
    };
  }

  // ---- Render quote from response ----
  function renderQuote(data) {
    if (!quoteLines || !quoteTotal) return;
    quoteLines.innerHTML = "";
    if (data && data.line_items && data.line_items.length) {
      data.line_items.forEach(function (item) {
        var row = document.createElement("div");
        row.className = "builder-quote-line";
        var label = document.createElement("span");
        label.textContent = item.label;
        var amt = document.createElement("span");
        amt.textContent = item.display_amount;
        row.appendChild(label);
        row.appendChild(amt);
        quoteLines.appendChild(row);
      });
    }
    quoteTotal.textContent = data && data.display_total ? data.display_total : "\u2014";
    if (quoteStatus) quoteStatus.textContent = "live pricing";
    if (data && data.reference) lastReference = data.reference;
  }

  function showError(msg) {
    if (!quoteLines) return;
    quoteLines.innerHTML = "";
    var err = document.createElement("div");
    err.style.cssText = "font-size:0.78rem;color:var(--signal-warn);padding:4px 0;";
    err.textContent = msg;
    quoteLines.appendChild(err);
    quoteTotal.textContent = "\u2014";
    if (quoteStatus) quoteStatus.textContent = "could not price";
  }

  // ---- Fetch authoritative price ----
  function fetchPreview() {
    var currentId = ++requestId;
    var payload = buildPayload();

    if (lastPayload && JSON.stringify(payload) === JSON.stringify(lastPayload)) {
      return;
    }
    lastPayload = payload;

    if (quoteStatus) quoteStatus.textContent = "computing\u2026";

    fetch("/api/v1/pricing/quote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      // Ignore if a newer request has started
      if (currentId !== requestId) return;

      if (data.detail) {
        showError(data.detail);
      } else {
        renderQuote(data);
      }
    })
    .catch(function () {
      if (currentId !== requestId) return;
      showError("We couldn't price that right now. Try again.");
    });
  }

  function schedulePreview() {
    if (previewTimer) clearTimeout(previewTimer);
    previewTimer = setTimeout(fetchPreview, 250);
  }

  // ---- Wire events ----
  productRadios.forEach(function (r) {
    r.addEventListener("change", function () {
      // Update selected visual state
      productRadios.forEach(function (other) {
        other.closest(".builder-product").classList.remove("is-selected");
      });
      r.closest(".builder-product").classList.add("is-selected");
      schedulePreview();
    });
  });

  channelChecks.forEach(function (c) {
    c.addEventListener("change", function () {
      var lbl = c.closest(".builder-channel");
      if (lbl) {
        if (c.checked) lbl.classList.add("is-selected");
        else lbl.classList.remove("is-selected");
      }
      schedulePreview();
    });
  });

  integrationChecks.forEach(function (c) {
    c.addEventListener("change", function () {
      updateIntegCount();
      schedulePreview();
    });
  });

  languageChecks.forEach(function (c) {
    c.addEventListener("change", function () {
      var box = c.closest(".builder-language");
      if (box) {
        var innerBox = box.querySelector(".builder-language-box");
        if (innerBox) {
          if (c.checked) innerBox.classList.add("is-selected");
          else innerBox.classList.remove("is-selected");
        }
      }
      schedulePreview();
    });
  });

  // ---- Submit ----
  if (submitBtn) {
    submitBtn.addEventListener("click", function (e) {
      e.preventDefault();
      var email = emailInput ? emailInput.value.trim() : "";
      if (!email) {
        alert("Please enter your email address so we can send your payment link and receipt.");
        if (emailInput) emailInput.focus();
        return;
      }
      var payload = buildPayload();
      submitBtn.disabled = true;
      submitBtn.textContent = "Getting quote\u2026";

      fetch("/api/v1/pricing/quote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.reference) {
          lastReference = data.reference;
          return fetch("/api/v1/checkout/orders", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              quote_reference: data.reference,
              email: email,
              product_type: payload.product_type,
              channels: payload.channels,
              monthly_conversations: payload.monthly_conversations,
              integrations: payload.integrations,
              languages: payload.languages
            })
          });
        } else if (data.detail) {
          showError(data.detail);
          submitBtn.disabled = false;
          submitBtn.textContent = "Get a quote";
          return null;
        }
      })
      .then(function (checkoutRes) {
        if (!checkoutRes) return;
        return checkoutRes.json();
      })
      .then(function (order) {
        if (!order) return;
        if (order.checkout_url) {
          window.location.href = order.checkout_url;
        } else if (order.detail) {
          alert("Could not start checkout: " + order.detail);
          submitBtn.disabled = false;
          submitBtn.textContent = "Get a quote";
        } else {
          alert("Order created: " + order.reference + "\nProceed to payment.");
          submitBtn.disabled = false;
          submitBtn.textContent = "Get a quote";
        }
      })
      .catch(function () {
        showError("We couldn't reach pricing. Try again.");
        submitBtn.disabled = false;
        submitBtn.textContent = "Get a quote";
      });
    });
  }

  // ---- Initial load: compute default preview immediately ----
  function loadInitial() {
    fetchPreview();
    updateVolumeTotal();
    updateIntegCount();
  }

  loadInitial();
})();
