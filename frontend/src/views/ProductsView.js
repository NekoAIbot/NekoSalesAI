/**
 * Nera 2.0 Greenfield — Products View
 * Specialized Business Automation Engines: Sales & Support.
 * Explains capabilities in terms of the business workflows they perform.
 */
export class ProductsView {
  constructor({ router }) {
    this.router = router;
  }

  async render() {
    return `
      <div class="anim-fade-in-up">
        <!-- Header -->
        <section style="text-align: center; margin-bottom: 56px;">
          <div class="nera-badge nera-badge-emerald" style="margin-bottom: 12px;">Specialized Workflow Engines</div>
          <h1 style="font-size: 2.75rem; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 16px;">
            AI-Powered <span class="gradient-text">Business Automation Engines</span>
          </h1>
          <p style="color: var(--slate-light); font-size: 1.125rem; max-width: 680px; margin: 0 auto; line-height: 1.6;">
            Deploy autonomous engines built to execute specific operational workflows: converting inbound buyer demand into revenue or automating tier-1 customer support.
          </p>
        </section>

        <!-- Product Cards Detail -->
        <div style="display: flex; flex-direction: column; gap: 48px; margin-bottom: 80px;">
          <!-- Product 1: Sales Automation Engine -->
          <div class="nera-card" style="display: grid; grid-template-columns: 1.25fr 1fr; gap: 40px; align-items: center;">
            <div>
              <div class="nera-badge nera-badge-blue" style="margin-bottom: 12px;">Commercial Conversion Engine</div>
              <h2 style="font-size: 2rem; font-weight: 800; margin-bottom: 12px;">Nera Sales Automation Engine</h2>
              <p style="color: var(--slate-light); font-size: 1rem; margin-bottom: 24px; line-height: 1.6;">
                Coordinates and executes the entire inbound sales workflow. Scopes buyer parameters, computes authoritative quotes from published rules, and collects payments via Paystack.
              </p>

              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 28px;">
                <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
                  <div style="font-weight: 700; font-size: 0.9375rem; margin-bottom: 4px;">Dynamic Scoping Workflow</div>
                  <div style="font-size: 0.8125rem; color: var(--slate-light);">Discovers volume, product lines, and service needs.</div>
                </div>
                <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
                  <div style="font-weight: 700; font-size: 0.9375rem; margin-bottom: 4px;">Paystack Paylink Generation</div>
                  <div style="font-size: 0.8125rem; color: var(--slate-light);">Generates instant authoritative checkout references.</div>
                </div>
                <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
                  <div style="font-weight: 700; font-size: 0.9375rem; margin-bottom: 4px;">Scheduled Follow-Up Loops</div>
                  <div style="font-size: 0.8125rem; color: var(--slate-light);">Automated re-engagement scheduler for stalled leads.</div>
                </div>
                <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
                  <div style="font-weight: 700; font-size: 0.9375rem; margin-bottom: 4px;">Zero LLM Price Errors</div>
                  <div style="font-size: 0.8125rem; color: var(--slate-light);">Deterministic calculations; no invented discounts.</div>
                </div>
              </div>

              <div style="display: flex; align-items: baseline; gap: 8px; margin-bottom: 20px;">
                <span class="nera-price-tag">₦199,000</span>
                <span class="nera-price-period">/ month base (+ ₦2,500 base volume charge for 500 conv, ₦5/additional)</span>
              </div>

              <div style="display: flex; gap: 12px;">
                <a href="/build?product=sales_agent" class="nera-btn nera-btn-primary nera-btn-lg" data-link="/build">
                  Configure Sales Engine
                </a>
                <a href="/demo?agent=sales" class="nera-btn nera-btn-secondary nera-btn-lg" data-link="/demo">
                  Simulate Sales Flow
                </a>
              </div>
            </div>

            <div style="background: var(--bg-surface-elevated); padding: 28px; border-radius: var(--radius-xl); border: 1px solid var(--border-card);">
              <div style="font-size: 0.8125rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--emerald-light); font-weight: 700; margin-bottom: 16px;">
                Sales Automation Capabilities &amp; Architecture
              </div>
              <ul style="list-style: none; display: flex; flex-direction: column; gap: 14px; font-size: 0.875rem; color: var(--ivory-dim);">
                <li style="display: flex; gap: 10px;"><span>✓</span><span><strong>Response Targets:</strong> Sub-second workflow execution cycle</span></li>
                <li style="display: flex; gap: 10px;"><span>✓</span><span><strong>Channels:</strong> Web Chat Widget, Telegram Bot, WhatsApp API</span></li>
                <li style="display: flex; gap: 10px;"><span>✓</span><span><strong>Concurrency:</strong> Scalable multi-tenant session processing</span></li>
                <li style="display: flex; gap: 10px;"><span>✓</span><span><strong>Security:</strong> NDPR-compliant customer data isolation</span></li>
                <li style="display: flex; gap: 10px;"><span>✓</span><span><strong>Analytics:</strong> Conversion progression and quotation tracking</span></li>
              </ul>
            </div>
          </div>

          <!-- Product 2: Support Automation Engine -->
          <div class="nera-card" style="display: grid; grid-template-columns: 1.25fr 1fr; gap: 40px; align-items: center;">
            <div>
              <div class="nera-badge nera-badge-emerald" style="margin-bottom: 12px;">Customer Care Engine</div>
              <h2 style="font-size: 2rem; font-weight: 800; margin-bottom: 12px;">Nera Support Automation Engine</h2>
              <p style="color: var(--slate-light); font-size: 1rem; margin-bottom: 24px; line-height: 1.6;">
                Eliminates repetitive post-purchase tasks. Answers inquiries from verified documents, looks up live order and shipping status, triages return requests, and escalates edge cases to your staff.
              </p>

              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 28px;">
                <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
                  <div style="font-weight: 700; font-size: 0.9375rem; margin-bottom: 4px;">Grounded Knowledge Answering</div>
                  <div style="font-size: 0.8125rem; color: var(--slate-light);">Only speaks from verified knowledge base documents.</div>
                </div>
                <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
                  <div style="font-weight: 700; font-size: 0.9375rem; margin-bottom: 4px;">Live Order Tracking</div>
                  <div style="font-size: 0.8125rem; color: var(--slate-light);">Reads order state via secure backend tokens.</div>
                </div>
                <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
                  <div style="font-weight: 700; font-size: 0.9375rem; margin-bottom: 4px;">Human Handoff Workflow</div>
                  <div style="font-size: 0.8125rem; color: var(--slate-light);">Seamlessly alerts human agents with full context.</div>
                </div>
                <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
                  <div style="font-weight: 700; font-size: 0.9375rem; margin-bottom: 4px;">Multilingual Routing</div>
                  <div style="font-size: 0.8125rem; color: var(--slate-light);">English, Pidgin, Yoruba, Hausa, and Igbo.</div>
                </div>
              </div>

              <div style="display: flex; align-items: baseline; gap: 8px; margin-bottom: 20px;">
                <span class="nera-price-tag">₦149,000</span>
                <span class="nera-price-period">/ month base (+ ₦2,500 base volume charge for 500 conv, ₦5/additional)</span>
              </div>

              <div style="display: flex; gap: 12px;">
                <a href="/build?product=support_agent" class="nera-btn nera-btn-primary nera-btn-lg" data-link="/build">
                  Configure Support Engine
                </a>
                <a href="/demo?agent=support" class="nera-btn nera-btn-secondary nera-btn-lg" data-link="/demo">
                  Simulate Support Flow
                </a>
              </div>
            </div>

            <div style="background: var(--bg-surface-elevated); padding: 28px; border-radius: var(--radius-xl); border: 1px solid var(--border-card);">
              <div style="font-size: 0.8125rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--electric-blue-light); font-weight: 700; margin-bottom: 16px;">
                Support Automation Capabilities &amp; Architecture
              </div>
              <ul style="list-style: none; display: flex; flex-direction: column; gap: 14px; font-size: 0.875rem; color: var(--ivory-dim);">
                <li style="display: flex; gap: 10px;"><span>✓</span><span><strong>Resolution Focus:</strong> Designed for autonomous tier-1 issue resolution</span></li>
                <li style="display: flex; gap: 10px;"><span>✓</span><span><strong>Knowledge Grounding:</strong> Strict RAG boundary filtering</span></li>
                <li style="display: flex; gap: 10px;"><span>✓</span><span><strong>Infrastructure:</strong> Scalable stateless service architecture</span></li>
                <li style="display: flex; gap: 10px;"><span>✓</span><span><strong>Escalation Triggers:</strong> Sentiment analysis and policy refund bounds</span></li>
                <li style="display: flex; gap: 10px;"><span>✓</span><span><strong>Workforce Bundle:</strong> Pair with Sales on <a href="/workforce" data-link="/workforce" style="color: var(--emerald-light); text-decoration: underline;">Workforce page</a></span></li>
              </ul>
            </div>
          </div>
        </div>

        <!-- Capability Distinction Matrix -->
        <section style="margin-bottom: 64px;">
          <h3 style="font-size: 1.5rem; font-weight: 800; margin-bottom: 16px; text-align: center;">
            Capability Classification &amp; Boundaries
          </h3>
          <p style="color: var(--slate-light); text-align: center; max-width: 680px; margin: 0 auto 32px;">
            Truthfulness is a core engineering requirement. Here is the verified operational status of every product capability:
          </p>

          <div style="overflow-x: auto;">
            <table class="capability-matrix-table">
              <thead>
                <tr>
                  <th>Capability</th>
                  <th>Operational Classification</th>
                  <th>Current State</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>Deterministic Math Pricing</strong></td>
                  <td>Available &amp; Verified</td>
                  <td><span class="badge-status-verified">Active in Code (scoping.py)</span></td>
                </tr>
                <tr>
                  <td><strong>Paystack Webhook Settlement</strong></td>
                  <td>Available &amp; Verified</td>
                  <td><span class="badge-status-verified">HMAC SHA512 Verified</span></td>
                </tr>
                <tr>
                  <td><strong>Shared Sales-to-Support State</strong></td>
                  <td>Available &amp; Verified</td>
                  <td><span class="badge-status-verified">Synchronized Memory</span></td>
                </tr>
                <tr>
                  <td><strong>Custom Knowledge Document Grounding</strong></td>
                  <td>Requires Configuration</td>
                  <td><span class="badge-status-config">Upload Knowledge Docs</span></td>
                </tr>
                <tr>
                  <td><strong>Telegram Bot API Webhooks</strong></td>
                  <td>Requires Configuration</td>
                  <td><span class="badge-status-config">Input Bot Token</span></td>
                </tr>
                <tr>
                  <td><strong>ERP Inventory Synchronization</strong></td>
                  <td>Planned Future Roadmap</td>
                  <td><span class="badge-status-planned">In Architecture Phase</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- Technical Guardrails -->
        <section style="background: var(--bg-surface-elevated); padding: 48px; border-radius: var(--radius-2xl); border: 1px solid var(--border-card); margin-bottom: 64px;">
          <h3 style="font-size: 1.5rem; font-weight: 800; margin-bottom: 16px;">
            🛡️ What Nera Explicitly Does NOT Do
          </h3>
          <p style="color: var(--slate-light); margin-bottom: 24px; max-width: 720px;">
            Enterprise reliability requires strict, provable boundaries. Our architecture enforces immutable safety guardrails directly in code:
          </p>

          <div class="nera-product-grid" style="margin-bottom: 0;">
            <div style="background: var(--bg-surface); padding: 20px; border-radius: var(--radius-lg); border: 1px solid var(--border-subtle);">
              <strong style="color: var(--signal-error); font-size: 0.9375rem;">NO Pricing Deviations</strong>
              <p style="font-size: 0.8125rem; color: var(--slate-light); margin-top: 8px;">
                Engines cannot negotiate custom pricing, promise unauthorized discounts, or deviate from the authoritative formula.
              </p>
            </div>

            <div style="background: var(--bg-surface); padding: 20px; border-radius: var(--radius-lg); border: 1px solid var(--border-subtle);">
              <strong style="color: var(--signal-error); font-size: 0.9375rem;">NO Prompt Injection Leaks</strong>
              <p style="font-size: 0.8125rem; color: var(--slate-light); margin-top: 8px;">
                User inputs are sanitized through boundary layers. System instructions and internal tokens are never revealed.
              </p>
            </div>
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
