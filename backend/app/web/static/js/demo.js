/* ================================================================
   demo.js — Scripted demonstration interactions
   ---------------------------------------------------------------
   Turn-by-turn replay with typing indicators, smooth window
   transitions, and full reduced-motion support.
   ================================================================ */

(function () {
  "use strict";

  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------------------------------------------------------------
     Demo transcript data
     --------------------------------------------------------------- */

  var transcript = document.getElementById("demo-transcript");
  var replayBtn = document.getElementById("demo-replay-btn");
  var resetBtn = document.getElementById("demo-reset-btn");

  var steps = [
    {
      from: "customer",
      text: "Hi — I run a clothing store and I need something that answers customer questions on WhatsApp and takes payment. What would that cost?"
    },
    {
      from: "nera",
      text: "I can help with that. A sales representative that answers on WhatsApp and takes payment — that's one of the things I build. Let me check what's in your configured products and prices.",
      typing: 1400
    },
    {
      from: "nera",
      text: "I've checked your configured knowledge — you're in fashion retail. I'd build you an AI Sales Representative that answers product questions and quotes your prices, available on WhatsApp. That starts at ₦199,000/month, depending on volume and channels.",
      typing: 1600
    },
    {
      from: "customer",
      text: "We also get a lot of support questions. Can we do both?"
    },
    {
      from: "nera",
      text: "Yes — that's the Nera Workforce. A sales representative plus a support agent working together. That bundle is <strong>₦299,000/month</strong>.",
      typing: 1200
    },
    {
      from: "customer",
      text: "Can you give us 20% off for an annual commitment?"
    },
    {
      from: "nera",
      text: "I'm not authorised to change the published price. I've flagged this for the team — someone will review it and reply to you directly. In the meantime, here's what I can do...",
      typing: 1000,
      escalate: true
    },
    {
      from: "nera",
      text: "",
      flow: true
    }
  ];

  /* ---------------------------------------------------------------
     State
     --------------------------------------------------------------- */

  var replayTimers = [];
  var isPlaying = false;

  /* ---------------------------------------------------------------
     Utility: clear all pending replay timers
     --------------------------------------------------------------- */

  function clearTimers() {
    for (var i = 0; i < replayTimers.length; i++) {
      clearTimeout(replayTimers[i]);
    }
    replayTimers = [];
  }

  /* ---------------------------------------------------------------
     Utility: schedule a callback, track the timer
     --------------------------------------------------------------- */

  function schedule(fn, delay) {
    var id = setTimeout(fn, delay);
    replayTimers.push(id);
    return id;
  }

  /* ---------------------------------------------------------------
     Utility: create an element with attributes/children
     --------------------------------------------------------------- */

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      for (var key in attrs) {
        if (attrs.hasOwnProperty(key)) {
          if (key === "class") node.className = attrs[key];
          else if (key === "html") node.innerHTML = attrs[key];
          else node.setAttribute(key, attrs[key]);
        }
      }
    }
    if (children) {
      for (var i = 0; i < children.length; i++) {
        node.appendChild(children[i]);
      }
    }
    return node;
  }

  /* ---------------------------------------------------------------
     Build a typing indicator (three pulsing dots)
     --------------------------------------------------------------- */

  function buildTyping() {
    var dot1 = el("span");
    var dot2 = el("span");
    var dot3 = el("span");
    return el("div", { class: "demo-bubble-typing" }, [dot1, dot2, dot3]);
  }

  /* ---------------------------------------------------------------
     Build a message turn (avatar + bubble) — NOT yet attached
     --------------------------------------------------------------- */

  function buildTurn(step) {
    var turn = el("div", {
      class: "demo-turn" + (step.from === "customer" ? " visitor" : " agent")
    });

    var av = el("div", {
      class: "demo-av " + (step.from === "customer" ? "cust" : "nera")
    });
    av.textContent = step.from === "customer" ? "C" : "N";

    var bubbleClass = "demo-bubble" + (step.from === "customer" ? " cust" : "");
    var bubble = el("div", { class: bubbleClass });

    if (step.flow) {
      bubble.innerHTML =
        '<div class="demo-bubble-flow">' +
          '<span class="flow-step">Quote</span><span class="flow-arrow">→</span>' +
          '<span class="flow-step">Checkout</span><span class="flow-arrow">→</span>' +
          '<span class="flow-step">Payment</span><span class="flow-arrow">→</span>' +
          '<span class="flow-step">Provisioning</span>' +
        '</div>';
      bubble.classList.add("demo-bubble-flow-card");
    } else if (step.escalate) {
      bubble.innerHTML = step.text;
      bubble.classList.add("demo-bubble-escalate");
    } else {
      bubble.innerHTML = step.text;
    }

    turn.appendChild(av);
    turn.appendChild(bubble);
    return turn;
  }

  /* ---------------------------------------------------------------
     Render the "typing then reveal" for a Nera step
     Returns the delay before the next step can start.
     --------------------------------------------------------------- */

  function renderNeraStep(step, container, onComplete) {
    if (reduce) {
      // No typing animation — just show the text
      var turn = buildTurn(step);
      container.appendChild(turn);
      scrollToBottom(container);
      if (onComplete) onComplete();
      return;
    }

    // Show typing indicator
    var typingTurn = el("div", { class: "demo-turn agent" });
    var typingAv = el("div", { class: "demo-av nera" });
    typingAv.textContent = "N";
    var typingBubble = el("div", { class: "demo-bubble" });
    typingBubble.appendChild(buildTyping());
    typingTurn.appendChild(typingAv);
    typingTurn.appendChild(typingBubble);

    // Fade in the typing indicator
    typingTurn.style.opacity = "0";
    typingTurn.style.transform = "translateY(6px)";
    typingTurn.style.transition = "opacity 0.2s ease, transform 0.2s ease";
    container.appendChild(typingTurn);

    // Trigger the rise
    schedule(function () {
      typingTurn.style.opacity = "1";
      typingTurn.style.transform = "none";
    }, 16);

    scrollToBottom(container);

    var typingDuration = step.typing || 1000;

    // After typing duration, swap to actual message
    schedule(function () {
      // Fade out typing
      typingTurn.style.transition = "opacity 0.15s ease";
      typingTurn.style.opacity = "0";

      schedule(function () {
        if (typingTurn.parentNode) {
          typingTurn.parentNode.removeChild(typingTurn);
        }
        var realTurn = buildTurn(step);
        realTurn.style.opacity = "0";
        realTurn.style.transform = "translateY(6px)";
        realTurn.style.transition = "opacity 0.25s ease, transform 0.25s ease";
        container.appendChild(realTurn);

        schedule(function () {
          realTurn.style.opacity = "1";
          realTurn.style.transform = "none";
        }, 16);

        scrollToBottom(container);
        if (onComplete) onComplete();
      }, 160);
    }, typingDuration);
  }

  /* ---------------------------------------------------------------
     Render a customer step (immediate, no typing)
     --------------------------------------------------------------- */

  function renderCustomerStep(step, container, onComplete) {
    var turn = buildTurn(step);
    turn.style.opacity = "0";
    turn.style.transform = "translateY(6px)";
    turn.style.transition = "opacity 0.25s ease, transform 0.25s ease";
    container.appendChild(turn);

    schedule(function () {
      turn.style.opacity = "1";
      turn.style.transform = "none";
    }, 16);

    scrollToBottom(container);
    if (onComplete) onComplete();
  }

  /* ---------------------------------------------------------------
     Scroll the transcript to the bottom (smooth when supported)
     --------------------------------------------------------------- */

  function scrollToBottom(container) {
    if (!container) return;
    if (reduce) {
      container.scrollTop = container.scrollHeight;
    } else {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: "smooth"
      });
    }
  }

  /* ---------------------------------------------------------------
     Clear the transcript container
     --------------------------------------------------------------- */

  function clearTranscript() {
    if (!transcript) return;
    transcript.innerHTML = "";
  }

  /* ---------------------------------------------------------------
     Play the demo turn by turn
     --------------------------------------------------------------- */

  function playDemo() {
    if (!transcript) return;

    // Cancel any in-progress replay
    clearTimers();
    isPlaying = true;

    clearTranscript();

    if (replayBtn) {
      replayBtn.classList.add("is-playing");
      replayBtn.setAttribute("aria-busy", "true");
    }

    if (reduce) {
      // Show all steps immediately
      for (var i = 0; i < steps.length; i++) {
        var turn = buildTurn(steps[i]);
        transcript.appendChild(turn);
      }
      scrollToBottom(transcript);
      isPlaying = false;
      if (replayBtn) {
        replayBtn.classList.remove("is-playing");
        replayBtn.removeAttribute("aria-busy");
      }
      return;
    }

    // Animate steps sequentially
    var idx = 0;

    function next() {
      if (idx >= steps.length) {
        isPlaying = false;
        if (replayBtn) {
          replayBtn.classList.remove("is-playing");
          replayBtn.removeAttribute("aria-busy");
        }
        return;
      }

      var step = steps[idx];
      idx++;

      if (step.from === "nera") {
        renderNeraStep(step, transcript, function () {
          schedule(next, 400);
        });
      } else {
        renderCustomerStep(step, transcript, function () {
          schedule(next, 300);
        });
      }
    }

    // Small initial delay
    schedule(next, 300);
  }

  /* ---------------------------------------------------------------
     Reset: clear everything and return to initial state
     --------------------------------------------------------------- */

  function resetDemo() {
    clearTimers();
    isPlaying = false;

    if (replayBtn) {
      replayBtn.classList.remove("is-playing");
      replayBtn.removeAttribute("aria-busy");
    }

    if (!transcript) return;

    // Fade out the transcript
    transcript.style.transition = "opacity 0.2s ease";
    transcript.style.opacity = "0";

    schedule(function () {
      clearTranscript();
      transcript.style.opacity = "1";
      showInitialState();
    }, 220);
  }

  /* ---------------------------------------------------------------
     Show the initial state (first customer message)
     --------------------------------------------------------------- */

  function showInitialState() {
    if (!transcript) return;

    var firstStep = steps[0];
    if (!firstStep) return;

    var turn = buildTurn(firstStep);

    if (!reduce) {
      turn.style.opacity = "0";
      turn.style.transform = "translateY(6px)";
      turn.style.transition = "opacity 0.3s ease, transform 0.3s ease";
    }

    transcript.appendChild(turn);

    if (!reduce) {
      schedule(function () {
        turn.style.opacity = "1";
        turn.style.transform = "none";
    }, 16);
    }
  }

  /* ---------------------------------------------------------------
     Button event listeners
     --------------------------------------------------------------- */

  if (replayBtn) {
    replayBtn.addEventListener("click", function () {
      if (isPlaying) {
        // Cancel current replay and restart
        clearTimers();
        isPlaying = false;
      }
      playDemo();
    });

    // Hover micro-interaction via JS for low-end phones
    replayBtn.addEventListener("mouseenter", function () {
      if (!reduce) replayBtn.style.transform = "translateY(-1px)";
    });
    replayBtn.addEventListener("mouseleave", function () {
      replayBtn.style.transform = "none";
    });
    replayBtn.addEventListener("mousedown", function () {
      if (!reduce) replayBtn.style.transform = "translateY(0) scale(0.97)";
    });
    replayBtn.addEventListener("mouseup", function () {
      if (!reduce) replayBtn.style.transform = "translateY(-1px)";
    });
  }

  if (resetBtn) {
    resetBtn.addEventListener("click", resetDemo);

    // Hover micro-interaction
    resetBtn.addEventListener("mouseenter", function () {
      if (!reduce) resetBtn.style.transform = "translateY(-1px)";
    });
    resetBtn.addEventListener("mouseleave", function () {
      resetBtn.style.transform = "none";
    });
    resetBtn.addEventListener("mousedown", function () {
      if (!reduce) resetBtn.style.transform = "translateY(0) scale(0.97)";
    });
    resetBtn.addEventListener("mouseup", function () {
      if (!reduce) resetBtn.style.transform = "translateY(-1px)";
    });
  }

  /* ---------------------------------------------------------------
     Initial state on page load
     --------------------------------------------------------------- */

  if (transcript) {
    showInitialState();
  }

  /* ---------------------------------------------------------------
     Demo dock — interactive window selector
     --------------------------------------------------------------- */

  var dock = document.querySelector(".demo-dock");
  if (dock) {
    var indicators = Array.prototype.slice.call(dock.querySelectorAll(".demo-indicator"));
    var windows = Array.prototype.slice.call(dock.querySelectorAll("[data-demo-window]"));

    function selectWindow(i) {
      if (i < 0 || i >= windows.length) return;

      windows.forEach(function (w, n) {
        if (n === i) {
          w.style.display = "";
          if (!reduce) {
            w.style.opacity = "0";
            w.style.transform = "translateY(8px)";
            w.style.transition = "opacity 0.3s ease, transform 0.3s ease";
            setTimeout(function () {
              w.style.opacity = "1";
              w.style.transform = "none";
            }, 16);
          }
        } else {
          w.style.display = "none";
          w.style.opacity = "";
          w.style.transform = "";
        }
      });

      indicators.forEach(function (ind, n) {
        var isActive = (n === i);
        if (isActive) {
          ind.style.opacity = "1";
          ind.style.transform = "scale(1.15)";
          ind.style.background = "var(--copper, #c4732a)";
        } else {
          ind.style.opacity = "0.3";
          ind.style.transform = "scale(1)";
          ind.style.background = "var(--void-border, #3a3a4a)";
        }
      });
    }

    indicators.forEach(function (ind, i) {
      // Click to select
      ind.addEventListener("click", function () { selectWindow(i); });

      // Hover to preview (desktop only)
      ind.addEventListener("mouseenter", function () {
        if (!reduce) {
          ind.style.opacity = "0.7";
        }
      });
      ind.addEventListener("mouseleave", function () {
        var isActive = ind.style.transform === "scale(1.15)";
        ind.style.opacity = isActive ? "1" : "0.3";
      });

      // Touch feedback for mobile
      ind.addEventListener("touchstart", function () {
        if (!reduce) ind.style.transform = "scale(0.9)";
      }, { passive: true });
      ind.addEventListener("touchend", function () {
        var isActive = ind.style.opacity === "1" && ind.style.transform !== "scale(0.9)";
        if (!reduce) ind.style.transform = isActive ? "scale(1.15)" : "scale(1)";
      }, { passive: true });
    });

    if (windows.length > 0) selectWindow(0);
  }

})();
