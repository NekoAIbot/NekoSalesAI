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
            Automation Built on <span class="gradient-text">Verifiable Code</span>
          </h1>
          <p style="color: var(--slate-light); font-size: 1.125rem; max-width: 680px; margin: 0 auto; line-height: 1.6;">
            We don't ask you to trust black-box AI promises. Nera enforces deterministic execution guardrails, cryptographically validated webhooks, and strict customer data isolation directly in code.
          </p>
        </section>

        <!-- Code Citations Matrix -->
        <section style="margin-bottom: 64px;">
          <h2 style="font-size: 1.5rem; font-weight: 800; margin-bottom: 24px;">Code Module Safety Citations</h2>

          <div style="display: flex; flex-direction: column; gap: 20px;">
            <!-- Module 1 -->
            <div class="nera-card">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span class="nera-mono" style="color: var(--emerald-light); font-weight: 600; font-size: 0.9375rem;">
                  backend/app/sales/understanding.py
                </span>
                <span class="nera-badge nera-badge-blue">Input Sanitization &amp; Boundary Defense</span>
              </div>
              <p style="color: var(--slate-light); font-size: 0.875rem; line-height: 1.5;">
                All customer incoming messages are analyzed against strict prompt-injection guardrails. System prompts, internal keys, and raw prompts are never exposed or overridden by user prompts.
              </p>
            </div>

            <!-- Module 2 -->
            <div class="nera-card">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span class="nera-mono" style="color: var(--emerald-light); font-weight: 600; font-size: 0.9375rem;">
                  backend/app/sales/scoping.py
                </span>
                <span class="nera-badge nera-badge-emerald">Deterministic Pricing Scoping</span>
              </div>
              <p style="color: var(--slate-light); font-size: 0.875rem; line-height: 1.5;">
                Enforces the mathematical line-item engine. No generative AI model has permission to alter product pricing or promise unauthorized discounts.
              </p>
            </div>

            <!-- Module 3 -->
            <div class="nera-card">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span class="nera-mono" style="color: var(--emerald-light); font-weight: 600; font-size: 0.9375rem;">
                  backend/app/payments/paystack.py
                </span>
                <span class="nera-badge nera-badge-blue">HMAC SHA512 Webhook Verification</span>
              </div>
              <p style="color: var(--slate-light); font-size: 0.875rem; line-height: 1.5;">
                All incoming Paystack payment webhooks are cryptographically authenticated via HMAC SHA512 signatures before any transaction state is mutated.
              </p>
            </div>

            <!-- Module 4 -->
            <div class="nera-card">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span class="nera-mono" style="color: var(--emerald-light); font-weight: 600; font-size: 0.9375rem;">
                  backend/app/payments/provisioning.py
                </span>
                <span class="nera-badge nera-badge-emerald">Idempotent Fulfillment Engine</span>
              </div>
              <p style="color: var(--slate-light); font-size: 0.875rem; line-height: 1.5;">
                Prevents duplicate charging or provisioning. Transactions maintain idempotent database states ensuring exactly-once delivery across network retries.
              </p>
            </div>
          </div>
        </section>

        <!-- Operational Guardrails Grid -->
        <section style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 24px; margin-bottom: 64px;">
          <div class="nera-card" style="padding: 28px;">
            <div style="font-size: 1.75rem; margin-bottom: 12px;">🔒</div>
            <h3 style="font-size: 1.25rem; font-weight: 700; margin-bottom: 8px;">NDPR &amp; Data Isolation</h3>
            <p style="font-size: 0.875rem; color: var(--slate-light); line-height: 1.5;">
              Organization tenant memory is strictly scoped by tenant IDs. Customer conversations never cross organization boundaries or leak into training corpora.
            </p>
          </div>

          <div class="nera-card" style="padding: 28px;">
            <div style="font-size: 1.75rem; margin-bottom: 12px;">⚡</div>
            <h3 style="font-size: 1.25rem; font-weight: 700; margin-bottom: 8px;">Deterministic Restraints</h3>
            <p style="font-size: 0.875rem; color: var(--slate-light); line-height: 1.5;">
              Automation workflows operate under explicit bounded state machines. No unverified action can execute outside documented catalog constraints.
            </p>
          </div>

          <div class="nera-card" style="padding: 28px;">
            <div style="font-size: 1.75rem; margin-bottom: 12px;">🛡️</div>
            <h3 style="font-size: 1.25rem; font-weight: 700; margin-bottom: 8px;">Deterministic Integer Pricing</h3>
            <p style="font-size: 0.875rem; color: var(--slate-light); line-height: 1.5;">
              Pricing line items are calculated by pure Python integer math in kobo/minor units. Quotations match billing ledgers with 100% cryptographic precision.
            </p>
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
