/**
 * Nera 2.0 Greenfield — Workforce View
 * The Unified Business Automation Pipeline: Sales + Support synchronized on a shared brain.
 */
export class WorkforceView {
  constructor({ router }) {
    this.router = router;
  }

  async render() {
    return `
      <div class="anim-fade-in-up">
        <!-- Header -->
        <section style="text-align: center; margin-bottom: 56px;">
          <div class="nera-badge nera-badge-emerald" style="margin-bottom: 12px;">Unified Dual-Engine Pipeline</div>
          <h1 style="font-size: 2.75rem; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 16px;">
            The Synchronized <span class="gradient-text">Nera Workforce Pipeline</span>
          </h1>
          <p style="color: var(--slate-light); font-size: 1.125rem; max-width: 680px; margin: 0 auto; line-height: 1.6;">
            Workforce is not a separate third agent—it is the unified end-to-end automation of both our <strong>Sales Engine</strong> and <strong>Support Engine</strong> running on synchronized business memory.
          </p>
        </section>

        <!-- Architecture & Handoff Showcase -->
        <section class="nera-card nera-card-highlight" style="padding: 40px; margin-bottom: 60px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 32px; flex-wrap: wrap; gap: 16px;">
            <div>
              <h2 style="font-size: 1.75rem; font-weight: 800;">End-to-End Operational Pipeline</h2>
              <p style="color: var(--slate-light); font-size: 0.9375rem;">
                Business Activity → Nera Orchestration → Automated Workflows → Completed Outcomes
              </p>
            </div>
            <span class="nera-badge nera-badge-blue">Synchronized Nera Brain</span>
          </div>

          <!-- Flow Chart Visual -->
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 20px;">
            <div style="background: var(--bg-surface-elevated); padding: 24px; border-radius: var(--radius-lg); border: 1px solid var(--border-subtle);">
              <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
                <span class="nera-badge nera-badge-blue">Stage 1: Acquisition</span>
                <span class="nera-mono" style="font-size: 0.8125rem; color: var(--electric-blue-light);">SALES ENGINE</span>
              </div>
              <h3 style="font-size: 1.125rem; font-weight: 700; margin-bottom: 8px;">Inbound Lead Intake &amp; Scoping</h3>
              <p style="color: var(--slate-light); font-size: 0.875rem; line-height: 1.5;">
                Captures prospect requirements on Web or Telegram, computes deterministic line-item pricing, and generates Paystack payment links.
              </p>
            </div>

            <div style="background: var(--bg-surface-elevated); padding: 24px; border-radius: var(--radius-lg); border: 1px solid var(--border-subtle);">
              <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
                <span class="nera-badge nera-badge-emerald">Stage 2: Settlement</span>
                <span class="nera-mono" style="font-size: 0.8125rem; color: var(--emerald-light);">PAYSTACK GATEWAY</span>
              </div>
              <h3 style="font-size: 1.125rem; font-weight: 700; margin-bottom: 8px;">Automated Settlement Verification</h3>
              <p style="color: var(--slate-light); font-size: 0.875rem; line-height: 1.5;">
                Customer completes payment. Paystack HMAC SHA512 webhook confirms transaction, idempotently updating the order and customer ledger.
              </p>
            </div>

            <div style="background: var(--bg-surface-elevated); padding: 24px; border-radius: var(--radius-lg); border: 1px solid var(--border-subtle);">
              <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
                <span class="nera-badge nera-badge-emerald">Stage 3: Handoff</span>
                <span class="nera-mono" style="font-size: 0.8125rem; color: var(--emerald-light);">SHARED MEMORY</span>
              </div>
              <h3 style="font-size: 1.125rem; font-weight: 700; margin-bottom: 8px;">Instant Context Dispatch</h3>
              <p style="color: var(--slate-light); font-size: 0.875rem; line-height: 1.5;">
                All transaction tokens, buyer metadata, and terms are instantly passed to the Support Engine. Zero repetitive questions for the buyer.
              </p>
            </div>

            <div style="background: var(--bg-surface-elevated); padding: 24px; border-radius: var(--radius-lg); border: 1px solid var(--border-subtle);">
              <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
                <span class="nera-badge nera-badge-blue">Stage 4: Fulfillment</span>
                <span class="nera-mono" style="font-size: 0.8125rem; color: var(--electric-blue-light);">SUPPORT ENGINE</span>
              </div>
              <h3 style="font-size: 1.125rem; font-weight: 700; margin-bottom: 8px;">Continuous Automated Care</h3>
              <p style="color: var(--slate-light); font-size: 0.875rem; line-height: 1.5;">
                Delivers 24/7 post-purchase order tracking, knowledge base inquiry resolution, and escalation to human staff when necessary.
              </p>
            </div>
          </div>
        </section>

        <!-- The Workforce Package Callout -->
        <section class="nera-card" style="padding: 48px; display: grid; grid-template-columns: 1.25fr 1fr; gap: 40px; align-items: center; margin-bottom: 64px;">
          <div>
            <div class="nera-badge nera-badge-emerald" style="margin-bottom: 12px;">Authoritative Bundle Pricing</div>
            <h2 style="font-size: 2.25rem; font-weight: 800; margin-bottom: 16px;">
              Deploy the Complete Operations Pipeline
            </h2>
            <p style="color: var(--slate-light); font-size: 1rem; margin-bottom: 24px; line-height: 1.6;">
              Synchronize commercial acquisition with post-purchase customer care. Your business operations run 24 hours a day on autopilot with zero human coordination fatigue.
            </p>

            <div style="display: flex; align-items: baseline; gap: 12px; margin-bottom: 24px;">
              <span class="nera-price-tag">₦348,000</span>
              <span class="nera-price-period">/ month base (+ ₦2,500 base volume charge for 500 conv, ₦5/additional)</span>
              <span style="font-size: 0.875rem; color: var(--emerald-light); font-weight: 600;">(₦199k Sales + ₦149k Support bundled)</span>
            </div>

            <div style="display: flex; gap: 12px; flex-wrap: wrap;">
              <a href="/build?product=workforce_agent" class="nera-btn nera-btn-primary nera-btn-lg" data-link="/build">
                Automate Workforce Pipeline
              </a>
              <a href="/demo?agent=workforce" class="nera-btn nera-btn-secondary nera-btn-lg" data-link="/demo">
                Simulate End-to-End Flow
              </a>
            </div>
          </div>

          <div style="background: var(--bg-surface-elevated); padding: 32px; border-radius: var(--radius-xl); border: 1px solid var(--border-card);">
            <h4 style="font-size: 1rem; font-weight: 700; margin-bottom: 16px; color: var(--ivory);">Inclusions in Workforce Deployment:</h4>
            <ul style="list-style: none; display: flex; flex-direction: column; gap: 12px; font-size: 0.875rem; color: var(--ivory-dim);">
              <li style="display: flex; gap: 10px;"><span>✓</span><span><strong>Sales Automation Engine:</strong> Dynamic intake, line-item pricing, Paystack links</span></li>
              <li style="display: flex; gap: 10px;"><span>✓</span><span><strong>Support Automation Engine:</strong> Grounded KB answers, live order lookups, triage</span></li>
              <li style="display: flex; gap: 10px;"><span>✓</span><span><strong>Shared Business Memory:</strong> Handoff without asking customers to repeat data</span></li>
              <li style="display: flex; gap: 10px;"><span>✓</span><span><strong>Cross-Channel Coordination:</strong> Web Widget + Telegram bot integration</span></li>
              <li style="display: flex; gap: 10px;"><span>✓</span><span><strong>Authoritative Savings:</strong> Saves ₦50,000/month vs two independent deployments</span></li>
            </ul>
          </div>
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
