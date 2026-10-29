/**
 * Nera 2.0 Greenfield — Trust & Safety View
 * Provable engineering standards, code module citations, and automation security boundaries.
 */
export class TrustView {
  constructor({ router }) {
    this.router = router;
  }

  async render() {
    return `
      <div class="anim-fade-in-up">
        <!-- Header -->
        <section style="text-align: center; margin-bottom: 56px;">
          <div class="nera-badge nera-badge-emerald" style="margin-bottom: 12px;">Provable Engineering</div>
          <h1 style="font-size: 2.75rem; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 16px;">
            Trust through <span class="gradient-text">provable restraint</span>
          </h1>
          <p style="color: var(--slate-light); font-size: 1.125rem; max-width: 680px; margin: 0 auto; line-height: 1.6;">
            Nera states only what its code and current product catalogue support. It does not invent prices or claim builds it cannot deliver.
          </p>
        </section>

        <section style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:20px;margin-bottom:64px;">
          <article class="nera-card"><h2>Prices are computed</h2><p style="color:var(--slate-light);margin-top:8px;">Quote line items come from bounded requirements and the pricing logic, not from free-form promises.</p></article>
          <article class="nera-card"><h2>Capabilities are bounded</h2><p style="color:var(--slate-light);margin-top:8px;">Nera currently builds an AI Sales Representative and an AI Support Agent. Requests outside those products are handed to a human.</p></article>
          <article class="nera-card"><h2>Quotes are itemised</h2><p style="color:var(--slate-light);margin-top:8px;">The quote shows its line items so buyers can see what contributes to the total.</p></article>
        </section>
      </div>
    `;
  }

  onMounted() {
    document.querySelectorAll('[data-link]').forEach(anchor => {
      anchor.addEventListener('click', (e) => {
        e.preventDefault();
        const targetPath = anchor.getAttribute('data-link');
        this.router.navigate(targetPath);
      });
    });
  }
}
