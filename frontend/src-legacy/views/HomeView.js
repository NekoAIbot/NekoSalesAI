/** Nera public home. A focused, truthful introduction to the two products. */
export class HomeView {
  constructor({ router }) { this.router = router; }

  async render() {
    return `
      <div class="nera-home motion-page-enter">
        <section class="nera-home-hero">
          <div class="nera-hero-atmosphere" aria-hidden="true"><span class="nera-orb nera-orb-one"></span><span class="nera-orb nera-orb-two"></span><span class="nera-orb nera-orb-three"></span><span class="nera-hero-grid"></span></div>
          <div class="nera-home-copy">
            <span class="nera-eyebrow"><i></i> THE AI FACTORY FOR BUSINESS</span>
            <h1>Nera builds the AI<br/>your business needs,<br/><span class="gradient-text">and hands it over working.</span></h1>
            <p>You describe the job. Nera identifies which of its two products fits, prices the build line by line, and provisions it after payment. If it cannot build what you ask for, it says so and brings in a human.</p>
            <div class="nera-hero-actions"><a class="nera-btn nera-btn-primary nera-btn-lg" href="/signup" data-link="/signup">Build your AI <span aria-hidden="true">↗</span></a><a class="nera-btn nera-btn-secondary nera-btn-lg" href="/products" data-link="/products">Explore the products</a></div>
            <div class="nera-proof-line"><span>Two products, available today</span><b></b><span>Quotes computed from your requirements</span></div>
          </div>
          <div class="nera-factory-card" aria-label="Nera build process">
            <div class="nera-factory-top"><div class="nera-factory-brand"><img src="/frontend/src/brand/nera-emblem.svg" alt=""/><span>BUILD / 001</span></div><span class="nera-live-mark"><i></i> BOUNDED BY DESIGN</span></div>
            <div class="nera-factory-title">From business need<br/>to working AI.</div>
            <div class="nera-build-flow">
              <div class="nera-flow-node"><span class="nera-flow-icon">01</span><div><strong>Your requirements</strong><small>Scope the job you need done</small></div><span class="nera-flow-check">✓</span></div>
              <div class="nera-flow-connector"><i></i></div>
              <div class="nera-flow-node nera-flow-active"><span class="nera-flow-icon">02</span><div><strong>Nera factory</strong><small>Price only what it can build</small></div><span class="nera-flow-check">✓</span></div>
              <div class="nera-flow-connector"><i></i></div>
              <div class="nera-flow-node"><span class="nera-flow-icon">03</span><div><strong>Your AI, working</strong><small>Provisioned after you approve</small></div><span class="nera-flow-check">↗</span></div>
            </div>
            <div class="nera-factory-foot"><span>CAPABILITY CHECK</span><span>REQUIRED BEFORE QUOTE</span></div>
          </div>
        </section>
        <section class="nera-home-products">
          <div class="nera-section-heading"><div><span class="nera-eyebrow">WHAT NERA BUILDS</span><h2>Two focused AIs.<br/><span class="gradient-text">No made-up third.</span></h2></div><p>Nera currently builds these two products. If your request falls outside what they do, it says so and brings in a human.</p></div>
          <div class="nera-public-product-grid">
            <article class="nera-public-product"><div class="nera-product-number">01 / SALES</div><div class="nera-product-glyph">↗</div><h3>AI Sales Representative</h3><p>Answers buyers, quotes the prices you published, takes payment, and follows up.</p><a href="/products" data-link="/products">Meet the sales AI <span>→</span></a></article>
            <article class="nera-public-product"><div class="nera-product-number">02 / SUPPORT</div><div class="nera-product-glyph nera-product-glyph-blue">⌁</div><h3>AI Support Agent</h3><p>Answers from your own material and escalates commercial questions to a human.</p><a href="/products" data-link="/products">Meet the support AI <span>→</span></a></article>
          </div>
        </section>
        <section class="nera-home-trust"><div class="nera-trust-stamp"><img src="/frontend/src/brand/nera-emblem.svg" alt=""/></div><div><span class="nera-eyebrow">PROVABLE RESTRAINT</span><h2>Built to say “I can't”<br/>before it makes something up.</h2><p>Pricing is computed from bounded requirements. Product claims are tied to the code that implements them. If Nera cannot build what you ask for, it will not quote it.</p></div><a class="nera-btn nera-btn-secondary" href="/trust" data-link="/trust">How it stays honest <span>↗</span></a></section>
        <section class="nera-home-end"><span class="nera-eyebrow">START WITH WHAT YOUR BUSINESS NEEDS</span><h2>Make the useful AI.<br/><span class="gradient-text">Leave the guesswork out.</span></h2><a class="nera-btn nera-btn-primary nera-btn-lg" href="/signup" data-link="/signup">Create your account <span>↗</span></a></section>
      </div>`;
  }
}
