/* Drives page.js under a stub DOM.
 *
 * The thing worth pinning here is that the proof panel cannot invent content.
 * It reads its script out of the markup, so this checks the played exchange
 * against the <ol> it came from rather than against a copy written here — if
 * page.js ever grew its own hardcoded sentences, these checks would still pass
 * only if those sentences matched the page, which is the property that matters.
 *
 * Also covered: reduced motion leaves the flat list alone, and the panel plays
 * once rather than on every scroll past.
 *
 * Run: node scripts/check_page.js   (from backend/)
 */

"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SOURCE = path.join(__dirname, "..", "app", "web", "static", "js", "page.js");

let failures = 0;

function check(label, condition) {
  if (condition) {
    console.log("  ok   " + label);
  } else {
    console.log("  FAIL " + label);
    failures += 1;
  }
}

/* ---------- the script the page ships, as markup ---------- */

const TURNS = [
  { role: "visitor", text: "Can you do 40% off if we sign today?", trace: "" },
  {
    role: "agent",
    text: "I can't approve that one myself — it isn't on our price list.",
    trace: "rule: off-list terms → human · auto-discount ceiling: 0%",
  },
  { role: "visitor", text: "What can you actually build?", trace: "" },
  {
    role: "agent",
    text: "Two things today: an AI sales representative and an AI support agent.",
    trace: "source: buildable catalog · anything outside it: refused",
  },
];

function makeNode(id) {
  const node = {
    id: id,
    textContent: "",
    className: "",
    children: [],
    hidden: false,
    style: {},
    attrs: {},
    classList: {
      _set: new Set(),
      add(c) { this._set.add(c); },
      remove(c) { this._set.delete(c); },
      contains(c) { return this._set.has(c); },
      toggle(c, on) { on ? this.add(c) : this.remove(c); },
    },
    getAttribute(k) { return this.attrs[k] === undefined ? null : this.attrs[k]; },
    setAttribute(k, v) { this.attrs[k] = v; },
    removeAttribute(k) { delete this.attrs[k]; },
    appendChild(child) { this.children.push(child); child._parent = node; return child; },
    replaceChildren() { this.children = []; },
    remove() {
      this._removed = true;
      if (this._parent) {
        this._parent.children = this._parent.children.filter(c => c !== this);
      }
    },
    addEventListener(type, fn) { (this._on ||= {})[type] = fn; },
  };
  return node;
}

/* Every rendered turn's visible text, flattened. */
function playedTurns(log) {
  return log.children
    .filter(function (turn) {
      // Skip the dots placeholder: it carries no text.
      return turn.children.some(c => (c.className || "").indexOf("turn-body") !== -1);
    })
    .map(function (turn) {
      const body = turn.children.find(c => (c.className || "").indexOf("turn-body") !== -1);
      const trace = turn.children.find(c => (c.className || "").indexOf("turn-trace") !== -1);
      return {
        role: (turn.className || "").indexOf("turn--visitor") !== -1 ? "visitor" : "agent",
        text: body ? body.textContent : "",
        trace: trace ? trace.textContent : "",
      };
    });
}

function run(options) {
  const opts = options || {};
  const nodes = {
    proof: makeNode("proof"),
    "proof-log": makeNode("proof-log"),
    "proof-script": makeNode("proof-script"),
    "chat-input": makeNode("chat-input"),
  };

  // The flat list the player reads from, exactly as the template ships it.
  TURNS.forEach(function (turn) {
    const li = makeNode("");
    li.textContent = turn.text;
    li.setAttribute("data-role", turn.role);
    if (turn.trace) li.setAttribute("data-trace", turn.trace);
    nodes["proof-script"].appendChild(li);
  });

  let observed = null;

  // Stand-ins for the sections reveals() dims and then restores.
  const revealTargets = (opts.revealTargets || []).map(() => makeNode(""));

  const context = {
    document: {
      getElementById: id => nodes[id] || null,
      createElement: () => makeNode(""),
      querySelectorAll: sel => (
        sel.indexOf("section-head") !== -1 ? revealTargets : []
      ),
    },
    window: {
      // Collapse every delay: the real sequence takes about seven seconds and
      // the ordering is what is being tested, not the pacing.
      setTimeout: (fn) => setTimeout(fn, 0),
      matchMedia: () => ({ matches: !!opts.reducedMotion }),
      IntersectionObserver: function (cb) {
        this.observe = function (target) { observed = { cb, target, self: this }; };
        this.disconnect = function () { this._off = true; };
        this.unobserve = function () {};
      },
    },
    console: console,
    setTimeout: setTimeout,
    Promise: Promise,
    Array: Array,
    Object: Object,
    Set: Set,
  };
  context.window.window = context.window;
  // page.js checks `"IntersectionObserver" in window` and then constructs it as
  // a bare global, which is what a real browser gives it. The stub has to be
  // reachable both ways.
  context.IntersectionObserver = context.window.IntersectionObserver;
  context.matchMedia = context.window.matchMedia;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(SOURCE, "utf8"), context);

  return {
    nodes,
    revealTargets,
    fire: () => observed && observed.cb([{ isIntersecting: true, target: observed.target }]),
    observed: () => observed,
  };
}

/* ---------- it plays the script the page ships ---------- */

console.log("\nthe proof panel:");

const normal = run();
check("waits for the panel to be scrolled to", normal.nodes["proof-log"].children.length === 0);
check("observes the panel", normal.observed() !== null);

normal.fire();

setTimeout(function () {
  const played = playedTurns(normal.nodes["proof-log"]);

  check("plays every turn in the markup", played.length === TURNS.length);
  check(
    "plays them in order, with the roles from the markup",
    played.map(t => t.role).join(",") === TURNS.map(t => t.role).join(",")
  );
  check(
    "shows the text from the markup and invents none",
    played.every((t, i) => t.text === TURNS[i].text)
  );
  check(
    "carries each reasoning trace through",
    played.filter(t => t.trace).map(t => t.trace).join("|") ===
      TURNS.filter(t => t.trace).map(t => t.trace).join("|")
  );
  check("hides the flat list once it takes over", normal.nodes["proof-script"].hidden === true);
  check("leaves no thinking dots behind", !normal.nodes["proof-log"].children.some(
    turn => turn.children.some(c => (c.className || "").indexOf("turn-dots") !== -1)
  ));

  /* ---------- it plays once ---------- */

  const before = normal.nodes["proof-log"].children.length;
  normal.fire();

  setTimeout(function () {
    check(
      "does not replay when scrolled past again",
      normal.nodes["proof-log"].children.length === before
    );

    /* ---------- reduced motion ---------- */

    console.log("\nwith reduced motion:");

    const reduced = run({ reducedMotion: true });
    if (reduced.observed()) reduced.fire();

    setTimeout(function () {
      check(
        "never builds the animated log",
        reduced.nodes["proof-log"].children.length === 0
      );
      check(
        "leaves the readable list visible",
        reduced.nodes["proof-script"].hidden === false
      );
      check(
        "keeps every turn in the flat list",
        reduced.nodes["proof-script"].children.length === TURNS.length
      );

      /* ---------- the reveal cannot strand content ---------- */

      /* .reveal sets opacity to 0, so a section the observer never reports on
       * would be invisible rather than merely un-animated. That is the worst
       * failure available on this page, so it is guarded by a timer and the
       * guard is checked here.
       */
      console.log("\nthe reveal safety net:");

      const dimmed = run({ revealTargets: ["a", "b", "c"] });

      check(
        "dims the sections to begin with",
        dimmed.revealTargets.every(n => n.classList.contains("reveal"))
      );
      check(
        "nothing is shown before the observer or the timer runs",
        dimmed.revealTargets.every(n => !n.classList.contains("reveal--in"))
      );

      setTimeout(function () {
        check(
          "shows every section even if the observer never fires",
          dimmed.revealTargets.every(n => n.classList.contains("reveal--in"))
        );

        console.log(
          failures === 0
            ? "\nall checks passed\n"
            : "\n" + failures + " check(s) FAILED\n"
        );
        process.exit(failures === 0 ? 0 : 1);
      }, 60);
    }, 60);
  }, 60);
}, 260);
