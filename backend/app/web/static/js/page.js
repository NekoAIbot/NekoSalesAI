/* Page motion: the hero proof panel, and section reveals on scroll.
 *
 * Two rules shape this file.
 *
 * The first is that nothing here may invent content. The proof panel replays a
 * scripted exchange, and the script is read out of the markup rather than
 * written here — the same <ol> a screen reader and a no-JS visitor get is the
 * source the player types from. There is no second copy to drift, and the panel
 * cannot show a sentence the page does not already contain.
 *
 * The second is that no content depends on this file running. The reveal starts
 * from a stylesheet class that is *added* by JS, so a browser that never gets
 * here shows a complete page rather than a blank one. Reduced motion is checked
 * before anything moves, and it is checked live rather than at load, so a
 * visitor who turns it on mid-session is honoured.
 */

(function () {
  "use strict";

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  const wait = function (ms) {
    return new Promise(function (resolve) { window.setTimeout(resolve, ms); });
  };

  /* ---------- the proof panel ---------- */

  /* Replays the scripted exchange in the hero.
   *
   * Plays once, when the panel is first scrolled into view — not on load, so a
   * visitor who arrives and immediately scrolls past does not come back to a
   * panel that already finished, and not on a loop, because a hero that keeps
   * restarting is asking for attention it has already had.
   */
  function proofPlayer() {
    const panel = document.getElementById("proof");
    const log = document.getElementById("proof-log");
    const script = document.getElementById("proof-script");
    if (!panel || !log || !script) return;

    const turns = Array.from(script.children).map(function (node) {
      return {
        role: node.getAttribute("data-role") === "visitor" ? "visitor" : "agent",
        text: node.textContent.trim().replace(/\s+/g, " "),
        trace: node.getAttribute("data-trace") || "",
      };
    });

    if (!turns.length) return;

    // With reduced motion the flat list *is* the panel. Leave it visible and
    // never build the animated version.
    if (reduced.matches) return;

    let started = false;

    function addTurn(turn) {
      const wrap = el("div", "turn turn--" + turn.role);
      wrap.appendChild(el(
        "span", "turn-who", turn.role === "visitor" ? "Buyer" : "Rep"
      ));
      wrap.appendChild(el("div", "turn-body", turn.text));

      if (turn.trace) wrap.appendChild(el("div", "turn-trace", turn.trace));

      log.appendChild(wrap);
      return wrap;
    }

    function addDots() {
      const wrap = el("div", "turn turn--agent");
      const dots = el("div", "turn-dots");
      dots.appendChild(el("span"));
      dots.appendChild(el("span"));
      dots.appendChild(el("span"));
      wrap.appendChild(dots);
      log.appendChild(wrap);
      return wrap;
    }

    async function play() {
      // Hand the panel over: the animated log becomes the visible copy and the
      // flat script steps out of the layout. The log stays aria-hidden (set in
      // the markup), so a screen reader keeps reading the script it replaced
      // rather than a half-typed transcript.
      script.hidden = true;

      await wait(500);

      for (const turn of turns) {
        if (reduced.matches) break;

        if (turn.role === "agent") {
          // The rep pauses before answering, because answering is a real round
          // trip and a reply that lands instantly reads as a canned one.
          const dots = addDots();
          await wait(1150);
          dots.remove();
        }

        addTurn(turn);
        await wait(turn.role === "visitor" ? 680 : 1500);
      }

      // If the preference flipped mid-play, restore the flat list rather than
      // leaving a half-finished exchange on screen.
      if (reduced.matches) {
        log.replaceChildren();
        script.hidden = false;
      }
    }

    function start() {
      if (started) return;
      started = true;
      play();
    }

    if (!("IntersectionObserver" in window)) {
      start();
      return;
    }

    const seen = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        seen.disconnect();
        start();
      });
    }, { threshold: 0.35 });

    seen.observe(panel);
  }

  /* ---------- section reveals ---------- */

  /* Sections lift into place the first time they are reached, once each.
   *
   * The job is to mark where one part of a long page ends and the next begins.
   * Anything that re-animated on every pass would be decoration instead, so the
   * observer releases each element as it fires.
   */
  function reveals() {
    if (reduced.matches) return;
    if (!("IntersectionObserver" in window)) return;

    const targets = document.querySelectorAll(
      ".section-head, .flow, .grid, .plans, .trust, .builder, .faq-list"
    );

    if (!targets.length) return;

    const shown = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("reveal--in");
        shown.unobserve(entry.target);
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });

    targets.forEach(function (node) {
      node.classList.add("reveal");
      shown.observe(node);
    });

    /* The failure this guards against is the worst one available here: .reveal
     * sets opacity to 0, so anything the observer never reports on would be
     * permanently invisible rather than merely un-animated. Cheap insurance —
     * after a few seconds everything is shown regardless of what fired.
     */
    window.setTimeout(function () {
      targets.forEach(function (node) { node.classList.add("reveal--in"); });
      shown.disconnect();
    }, 3000);
  }

  /* ---------- product note on the builder ---------- */

  /* The plan buttons in the pricing grid deep-link to the chat. Focusing the
   * input on arrival means the visitor can type their question straight away
   * instead of hunting for the field they were just sent to.
   */
  function focusChatOnJump() {
    document.querySelectorAll('a[href="#chat"]').forEach(function (link) {
      link.addEventListener("click", function () {
        const input = document.getElementById("chat-input");
        if (!input) return;
        // After the browser's own scroll has been queued, so focusing does not
        // fight it.
        window.setTimeout(function () { input.focus({ preventScroll: true }); }, 420);
      });
    });
  }

  proofPlayer();
  reveals();
  focusChatOnJump();
})();
