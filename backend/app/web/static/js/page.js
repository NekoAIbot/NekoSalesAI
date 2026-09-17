/* ================================================================
   page.js — Scroll reveal, count-up, interactive helpers
   Adapted from React Bits patterns: Spotlight, magnetic, animated list
   ================================================================ */

(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------------------------------------------------------------
     Scroll Reveal — IntersectionObserver
     --------------------------------------------------------------- */
  function initScrollReveal() {
    if (reduceMotion) {
      document.querySelectorAll(".reveal").forEach(function (el) {
        el.classList.add("is-visible");
      });
      return;
    }

    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) {
            e.target.classList.add("is-visible");
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.08, rootMargin: "0px 0px -20px 0px" }
    );

    document.querySelectorAll(".reveal").forEach(function (el) {
      io.observe(el);
    });
  }

  /* ---------------------------------------------------------------
     Count-up — smooth number drift
     --------------------------------------------------------------- */
  function formatCount(n) {
    var s = Math.round(n).toString();
    var parts = [];
    var i = s.length;
    while (i > 0) {
      parts.unshift(s.slice(i - 3, i));
      i -= 3;
    }
    return parts.join(",");
  }

  function animateCountUp(el, target) {
    if (reduceMotion) {
      el.textContent = formatCount(target);
      return;
    }

    var start = performance.now();
    var dur = 1400;
    var ease = function (t) { return 1 - Math.pow(1 - t, 3); };
    var current = 0;

    function loop() {
      var t = Math.min((performance.now() - start) / dur, 1);
      current = target * ease(t);
      el.textContent = formatCount(current);
      if (t < 1) requestAnimationFrame(loop);
      else el.textContent = formatCount(target);
    }
    requestAnimationFrame(loop);
  }

  function initCountUps() {
    document.querySelectorAll("[data-count]").forEach(function (el) {
      var target = parseInt(el.getAttribute("data-count"), 10);
      if (!isNaN(target)) animateCountUp(el, target);
    });
  }

  /* ---------------------------------------------------------------
     Spotlight Card — radial highlight follows mouse
     Usage: add class "spotlight-card" to any element
     --------------------------------------------------------------- */
  function initSpotlightCards() {
    if (reduceMotion) return;

    var cards = document.querySelectorAll(".spotlight-card");
    cards.forEach(function (card) {
      card.addEventListener("mousemove", function (e) {
        var r = card.getBoundingClientRect();
        var x = ((e.clientX - r.left) / r.width) * 100;
        var y = ((e.clientY - r.top) / r.height) * 100;
        card.style.setProperty("--mx", x + "%");
        card.style.setProperty("--my", y + "%");
      });
      card.addEventListener("mouseleave", function () {
        card.style.setProperty("--mx", "50%");
        card.style.setProperty("--my", "50%");
      });
    });
  }

  /* ---------------------------------------------------------------
     Magnetic Button — button pulls toward cursor
     Usage: add class "magnetic-btn" to buttons
     --------------------------------------------------------------- */
  function initMagneticButtons() {
    if (reduceMotion) return;

    var affinity = 0.28;
    var buttons = document.querySelectorAll(".magnetic-btn");
    buttons.forEach(function (btn) {
      btn.addEventListener("mousemove", function (e) {
        var r = btn.getBoundingClientRect();
        var cx = r.left + r.width / 2;
        var cy = r.top + r.height / 2;
        var dx = (e.clientX - cx) * affinity;
        var dy = (e.clientY - cy) * affinity;
        btn.style.transform = "translate(" + dx + "px, " + dy + "px)";
      });
      btn.addEventListener("mouseleave", function () {
        btn.style.transform = "";
        btn.style.transition = "transform 0.35s cubic-bezier(.34,1.56,.64,1)";
        window.setTimeout(function () { btn.style.transition = ""; }, 350);
      });
    });
  }

  /* ---------------------------------------------------------------
     Dock — macOS-style app dock with active scaling
     Usage: element with class "app-dock", items with class "dock-item"
     --------------------------------------------------------------- */
  function initDock() {
    var dock = document.querySelector(".app-dock");
    if (!dock) return;

    var items = Array.prototype.slice.call(dock.querySelectorAll(".dock-item"));
    var idx = 0;
    var hovered = false;

    function apply(i) {
      items.forEach(function (it, n) {
        var dist = Math.abs(n - i);
        var scale = Math.max(0.65, 1 - dist * 0.18);
        var y = (n - i) * 5;
        it.style.setProperty("--d-scale", scale.toFixed(2));
        it.style.setProperty("--d-y", y + "px");
      });
    }

    function onMove(e) {
      var r = dock.getBoundingClientRect();
      var rel = e.clientX - r.left;
      var i = Math.round((rel / r.width) * (items.length - 1));
      i = Math.max(0, Math.min(items.length - 1, i));
      if (i !== idx) { idx = i; apply(i); }
      if (!hovered) { hovered = true; dock.classList.add("dock-open"); }
    }

    dock.addEventListener("mousemove", onMove);
    dock.addEventListener("mouseenter", function () {
      if (!hovered) { hovered = true; dock.classList.add("dock-open"); }
    });
    dock.addEventListener("mouseleave", function () {
      hovered = false;
      dock.classList.remove("dock-open");
      idx = 0;
      apply(0);
    });

    items.forEach(function (it) {
      it.addEventListener("mouseenter", function () {
        idx = items.indexOf(it);
        apply(idx);
      });
    });

    apply(0);
  }

  /* ---------------------------------------------------------------
     Demo Dock, Demo Replay, Demo Typing
     All demo interaction logic lives in demo.js.
     page.js intentionally does not initialize demo controls
     to avoid double-binding event listeners on the demo page.
     --------------------------------------------------------------- */

  /* ---------------------------------------------------------------
     Hero typing simulation — auto-advance activity stream
     --------------------------------------------------------------- */
  function initHeroTypingSim() {
    var simBtn = document.getElementById("hero-sim-btn");
    if (!simBtn) return;

    var entries = document.querySelectorAll(".activity-entry");
    if (entries.length === 0) return;

    var current = 0;
    var hidden = true;

    simBtn.addEventListener("click", function () {
      hidden = !hidden;

      if (hidden) {
        entries.forEach(function (e) { e.style.display = "none"; });
        simBtn.textContent = "Show activity";
        return;
      }

      entries.forEach(function (e) { e.style.display = ""; });

      entries.forEach(function (e, i) {
        e.style.opacity = "0";
        e.style.transform = "translateY(4px)";
        setTimeout(function () {
          e.style.opacity = "1";
          e.style.transform = "";
        }, i * 130 + 60);
      });

      simBtn.textContent = "Hide activity";
    });
  }

  /* ---------------------------------------------------------------
     Builder builder — interactive worker preview
     --------------------------------------------------------------- */

  function initBuilder() {
    var selects = document.querySelectorAll("[data-builder-field]");
    if (selects.length === 0) return;

    var workerEl = document.querySelector("[data-builder-worker]");
    if (!workerEl) return;

    var capabilities = {
      "sales": ["Quotes your published prices", "Engages website visitors", "Follows configured workflows", "Operates on web by default"],
      "support": ["Answers from your knowledge base", "Resolves what it can", "Escalates what it cannot", "Never invents a price"],
      "workforce": ["Sales + Support operating together", "Shared context across channels", "Coordinate qualification and resolution", "Priority provisioning"]
    };

    var roleNames = {
      "sales": "Nera AI Sales Representative",
      "support": "Nera AI Support Agent",
      "workforce": "Nera AI Workforce"
    };

    var roleTags = {
      "sales": "Configured to your business",
      "support": "Configured to your business",
      "workforce": "Sales + Support · One system"
    };

    var priceMap = {};
    // Price map is filled from the API, not hardcoded.
    // The builder.js loadPrices() function populates this before checkout.

    function updatePreview() {
      var selected = "sales";
      selects.forEach(function (sel) {
        if (sel.classList.contains("selected")) {
          selected = sel.getAttribute("data-builder-field");
        }
      });

      var caps = capabilities[selected] || capabilities.sales;
      var name = roleNames[selected] || roleNames.sales;
      var tag = roleTags[selected] || roleTags.sales;
      var price = priceMap[selected] || priceMap.sales;

      var nameEl = workerEl.querySelector(".preview-name");
      var tagEl = workerEl.querySelector(".preview-tag");
      var priceEl = workerEl.querySelector(".preview-price");
      var capsList = workerEl.querySelector(".preview-caps");

      if (nameEl) nameEl.textContent = name;
      if (tagEl) tagEl.textContent = tag;
      if (priceEl) priceEl.textContent = price;

      if (capsList) {
        capsList.innerHTML = "";
        caps.forEach(function (c) {
          var item = document.createElement("div");
          item.className = "preview-cap";
          item.innerHTML = '<span class="preview-cap-mark"></span>' + c;
          capsList.appendChild(item);
        });
      }
    }

    selects.forEach(function (sel) {
      sel.addEventListener("click", function () {
        selects.forEach(function (s) { s.classList.remove("selected"); });
        sel.classList.add("selected");
        updatePreview();
      });
    });

    updatePreview();
  }

  /* ---------------------------------------------------------------
     Mobile nav toggle
     --------------------------------------------------------------- */
  function initMobileNav() {
    var toggle = document.querySelector(".nav-mobile-toggle");
    var menu = document.querySelector(".nav-mobile-menu");
    if (!toggle || !menu) return;

    toggle.addEventListener("click", function () {
      menu.classList.toggle("open");
      toggle.setAttribute("aria-expanded", menu.classList.contains("open"));
    });

    menu.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () {
        menu.classList.remove("open");
        toggle.setAttribute("aria-expanded", "false");
      });
    });

    window.addEventListener("resize", function () {
      if (window.innerWidth > 640) menu.classList.remove("open");
    });
  }

  /* ---------------------------------------------------------------
     Field focus ring — consistent interaction
     --------------------------------------------------------------- */
  function initFieldFocus() {
    var inputs = document.querySelectorAll(".field-input");
    inputs.forEach(function (input) {
      input.addEventListener("focus", function () {
        this.closest(".field")?.classList.add("field-focused");
      });
      input.addEventListener("blur", function () {
        this.closest(".field")?.classList.remove("field-focused");
      });
    });
  }

  /* ---------------------------------------------------------------
     Keyboard accessibility for clickable options
     --------------------------------------------------------------- */
  function initOptionKeys() {
    document.querySelectorAll(".field-option").forEach(function (opt) {
      opt.setAttribute("tabindex", "0");
      opt.setAttribute("role", "button");

      opt.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          opt.click();
        }
      });
    });
  }

  /* ---------------------------------------------------------------
     Smooth anchor scroll (for in-page navigation)
     --------------------------------------------------------------- */
  function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(function (link) {
      link.addEventListener("click", function (e) {
        var target = document.querySelector(link.getAttribute("href"));
        if (!target) return;

        e.preventDefault();
        var y = target.getBoundingClientRect().top + window.pageYOffset - 20;

        window.scrollTo({
          top: y,
          behavior: reduceMotion ? "auto" : "smooth"
        });
      });
    });
  }

  /* ---------------------------------------------------------------
     Checkout CTA — proceed to Paystack checkout
     --------------------------------------------------------------- */
  function initCheckoutCtas() {
    var ctas = document.querySelectorAll("[data-checkout-cta]");
    if (ctas.length === 0) return;

    ctas.forEach(function (cta) {
      cta.addEventListener("click", function (e) {
        e.preventDefault();

        // Read selected product from builder
        var productRadios = document.querySelectorAll("[data-builder-product]:checked");
        var selectedProduct = "sales";
        productRadios.forEach(function (r) {
          if (r.checked) selectedProduct = r.getAttribute("data-builder-product");
        });

        // Read selected channels
        var channels = [];
        var channelChecks = document.querySelectorAll("[data-builder-channel]:checked");
        channelChecks.forEach(function (c) {
          channels.push(c.value);
        });

        // Read form fields if present
        var formEmail = document.getElementById("checkout-email");
        var formName = document.getElementById("checkout-name");
        var formCompany = document.getElementById("checkout-company");
        var email = formEmail ? formEmail.value.trim() : "";
        var name = formName ? formName.value.trim() : "";
        var company = formCompany ? formCompany.value.trim() : "";

        // Default web if nothing selected
        if (channels.length === 0) channels.push("web");

        // If the form has an email, use it; otherwise we need one before
        // we can raise a payment link. Show the buyer what we have.
        if (!email) {
          alert("Please enter an email address so we can send your payment link.");
          if (formEmail) formEmail.focus();
          return;
        }

        var payload = {
          product_type: selectedProduct,
          channels: channels,
          monthly_conversations: 500,
          email: email,
          name: name || undefined,
          company: company || undefined,
        };

        // First get a quote, then create checkout from the quote
        fetch("/api/v1/pricing/quote", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        })
        .then(function (quoteRes) {
          if (!quoteRes.ok) throw new Error("Quote failed");
          return quoteRes.json();
        })
        .then(function (quote) {
          // Now create the checkout order using the quote reference.
          // Re-send the requirement too — the checkout service will re-price
          // it server-side and persist the agreed configuration.
          return fetch("/api/v1/checkout/orders", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              quote_reference: quote.reference,
              email: email,
              name: name || undefined,
              company: company || undefined,
              product_type: selectedProduct,
              channels: channels,
              monthly_conversations: 500,
            }),
          });
        })
        .then(function (checkoutRes) {
          if (!checkoutRes.ok) throw new Error("Checkout failed");
          return checkoutRes.json();
        })
        .then(function (order) {
          // Redirect to Paystack or show checkout URL
          if (order.checkout_url) {
            window.location.href = order.checkout_url;
          } else {
            // Fallback: show the order reference
            alert("Order created: " + order.reference + "\nProceed to payment.");
          }
        })
        .catch(function (err) {
          console.error("Checkout error:", err);
          alert("Could not start checkout: " + err.message);
        });
      });
    });
  }

  /* ---------------------------------------------------------------
     Init on DOM ready
     --------------------------------------------------------------- */
  function init() {
    initScrollReveal();
    initCountUps();
    initSpotlightCards();
    initMagneticButtons();
    initHeroTypingSim();
    initBuilder();
    initMobileNav();
    initFieldFocus();
    initOptionKeys();
    initSmoothScroll();
    initCheckoutCtas();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  /* Re-check scroll reveals on resize */
  var resizeTimer;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(initScrollReveal, 150);
  }, { passive: true });

})();
