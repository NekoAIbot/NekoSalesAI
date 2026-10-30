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
          <div class="nera-badge nera-badge-emerald" style="margin-bottom: 12px;">Meet the Nera agents</div>
          <h1 style="font-size: 2.75rem; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 16px;">
            Two agents. <span class="gradient-text">One clear standard.</span>
          </h1>
          <p style="color: var(--slate-light); font-size: 1.125rem; max-width: 680px; margin: 0 auto; line-height: 1.6;">
            An AI Sales Representative that moves leads toward a sale, and an AI Support Agent that helps customers with answers it can stand behind. Both know when to stop and hand off.
          </p>
        </section>

        <!-- Product Cards Detail -->
        <div style="display: flex; flex-direction: column; gap: 48px; margin-bottom: 80px;">
          <!-- Product 1: Sales Automation Engine -->
          <div class="nera-card" style="display: grid; grid-template-columns: 1.25fr 1fr; gap: 40px; align-items: center;">
            <div>
              <div class="nera-badge nera-badge-blue" style="margin-bottom: 12px;">AI Sales Representative</div>
              <h2 style="font-size: 2rem; font-weight: 800; margin-bottom: 12px;">Turn good questions into next steps.</h2>
              <p style="color: var(--slate-light); font-size: 1rem; margin-bottom: 24px; line-height: 1.6;">
                Qualifies inbound leads, builds accurate quotes from your published pricing rules, and shares Paystack checkout links, all in the conversation.
              </p>

              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 28px;">
                <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
                  <div style="font-weight: 700; font-size: 0.9375rem; margin-bottom: 4px;">Lead qualification</div>
                  <div style="font-size: 0.8125rem; color: var(--slate-light);">Learns what the buyer needs before making a recommendation.</div>
                </div>
                <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
                  <div style="font-weight: 700; font-size: 0.9375rem; margin-bottom: 4px;">Paystack checkout</div>
                  <div style="font-size: 0.8125rem; color: var(--slate-light);">Creates secure payment links when the buyer is ready.</div>
                </div>
                <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
                  <div style="font-weight: 700; font-size: 0.9375rem; margin-bottom: 4px;">Thoughtful follow-ups</div>
                  <div style="font-size: 0.8125rem; color: var(--slate-light);">Reaches out to leads on your schedule.</div>
                </div>
                <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
                  <div style="font-weight: 700; font-size: 0.9375rem; margin-bottom: 4px;">Quotes you can trust</div>
                  <div style="font-size: 0.8125rem; color: var(--slate-light);">Pricing follows your rules, with no made-up discounts.</div>
                </div>
              </div>

              <div style="display: flex; align-items: baseline; gap: 8px; margin-bottom: 20px;">
                <span class="nera-price-tag">₦199,000</span>
                <span class="nera-price-period">/ month base (+ ₦2,500 base volume charge for 500 conv, ₦5/additional)</span>
              </div>

              <div style="display: flex; gap: 12px;">
                <a href="/build?product=sales_agent" class="nera-btn nera-btn-primary nera-btn-lg" data-link="/build">
                  Set up your sales agent
                </a>
                <a href="/demo?agent=sales" class="nera-btn nera-btn-secondary nera-btn-lg" data-link="/demo">
                  Try a sales conversation
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
              <div class="nera-badge nera-badge-emerald" style="margin-bottom: 12px;">AI Support Agent</div>
              <h2 style="font-size: 2rem; font-weight: 800; margin-bottom: 12px;">Helpful answers, honest limits.</h2>
              <p style="color: var(--slate-light); font-size: 1rem; margin-bottom: 24px; line-height: 1.6;">
                Answers from your approved knowledge, looks up connected order and shipping records, and checks return requests against your policies. If it cannot verify an answer, it brings in your team.
              </p>

              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 28px;">
                <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
                  <div style="font-weight: 700; font-size: 0.9375rem; margin-bottom: 4px;">Answers with a source</div>
                  <div style="font-size: 0.8125rem; color: var(--slate-light);">Uses your approved knowledge, not a guess.</div>
                </div>
                <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
                  <div style="font-weight: 700; font-size: 0.9375rem; margin-bottom: 4px;">Order updates</div>
                  <div style="font-size: 0.8125rem; color: var(--slate-light);">Checks connected order and tracking records.</div>
                </div>
                <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
                  <div style="font-weight: 700; font-size: 0.9375rem; margin-bottom: 4px;">Human handoff</div>
                  <div style="font-size: 0.8125rem; color: var(--slate-light);">Gives your team the conversation context.</div>
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
                  Set up your support agent
                </a>
                <a href="/demo?agent=support" class="nera-btn nera-btn-secondary nera-btn-lg" data-link="/demo">
                  Try a support conversation
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
