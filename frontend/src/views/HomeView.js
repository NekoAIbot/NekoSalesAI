/**
 * Nera 2.0 Greenfield — Home View
 * Positioning: AI that moves work forward, without making things up
 * Hero: "Your business. On autopilot."
 * Visual Story: BUSINESS ACTIVITY → NERA ORCHESTRATION → AUTOMATED WORKFLOWS → COMPLETED OUTCOMES
 */
import { store } from '../core/store.js';

export class HomeView {
  constructor({ router }) {
    this.router = router;
    this.activeWorkflowTab = 'all'; // 'all' | 'sales' | 'support' | 'workforce'
    this.activeStep = 2; // 1: Activity, 2: Orchestration, 3: Workflows, 4: Outcomes
    this.timer = null;
  }

  async render() {
    return `
      <div class="anim-fade-in-up">
        <!-- Hero Section: Split Composition -->
        <section class="nera-hero-split">
          <div>
            <div class="nera-badge nera-badge-emerald" style="margin-bottom: 16px;">
              <span class="nera-badge-dot anim-pulse-dot"></span>
              AI that moves work forward, without making things up
            </div>

            <h1 class="nera-hero-title">
              More conversations<br/>
              <span class="gradient-text">to meaningful outcomes.</span>
            </h1>

            <p class="nera-hero-sub">
              Meet your AI Sales Representative and AI Support Agent. They handle the next step, stick to your rules, and bring in a person when the answer is not clear.
            </p>

            <div class="nera-hero-actions">
              <a href="/build" class="nera-btn nera-btn-primary nera-btn-lg" data-link="/build">
                Meet your AI team
              </a>
              <a href="/demo" class="nera-btn nera-btn-secondary nera-btn-lg" data-link="/demo">
                See it in action
              </a>
            </div>

            <div style="margin-top: 24px; font-size: 0.8125rem; color: var(--slate-light); display: flex; align-items: center; gap: 14px; flex-wrap: wrap;">
              <span>✓ Deterministic Workflow Execution</span>
              <span>•</span>
              <span>✓ Authoritative Nigerian Naira Billing</span>
              <span>•</span>
              <span>✓ Code-Enforced Pricing Rules</span>
              <span>•</span>
              <span>✓ Synchronized Shared Memory</span>
            </div>
          </div>

          <!-- Interactive Orchestration Network Canvas -->
          <div class="operating-canvas">
            <div class="canvas-header">
              <div style="display: flex; align-items: center; gap: 10px;">
                <span class="nera-badge-dot anim-pulse-dot"></span>
                <strong style="font-size: 0.875rem; letter-spacing: 0.02em;">LIVE WORKFLOW ORCHESTRATOR</strong>
              </div>
              <div class="nera-tabs" style="padding: 2px;">
                <button class="nera-tab-btn active workflow-tab-btn" data-workflow="all" style="font-size: 0.75rem; padding: 4px 10px;">All Flows</button>
                <button class="nera-tab-btn workflow-tab-btn" data-workflow="sales" style="font-size: 0.75rem; padding: 4px 10px;">Sales</button>
                <button class="nera-tab-btn workflow-tab-btn" data-workflow="support" style="font-size: 0.75rem; padding: 4px 10px;">Support</button>
                <button class="nera-tab-btn workflow-tab-btn" data-workflow="workforce" style="font-size: 0.75rem; padding: 4px 10px;">Workforce</button>
              </div>
            </div>

            <!-- 4-Stage Operational Pipeline Progress Bar -->
            <div style="padding: 16px 20px 0;">
              <div class="pipeline-track" id="pipeline-stepper">
                <div class="pipeline-step active" data-step="1">
                  <div class="pipeline-step-num">Stage 1</div>
                  <div class="pipeline-step-title">Business Activity</div>
                </div>
                <div class="pipeline-step active" data-step="2">
                  <div class="pipeline-step-num">Stage 2</div>
                  <div class="pipeline-step-title">Nera Orchestration</div>
                </div>
                <div class="pipeline-step active" data-step="3">
                  <div class="pipeline-step-num">Stage 3</div>
                  <div class="pipeline-step-title">Automated Workflows</div>
                </div>
                <div class="pipeline-step active" data-step="4">
                  <div class="pipeline-step-num">Stage 4</div>
                  <div class="pipeline-step-title">Completed Outcomes</div>
                </div>
              </div>
            </div>

            <div class="canvas-body" id="canvas-network-content">
              <!-- Dynamically populated by updateOrchestrationCanvas() -->
            </div>

            <!-- Footer Status Bar -->
            <div style="padding: 12px 20px; background: var(--bg-surface-elevated); border-top: 1px solid var(--border-subtle); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
              <div style="display: flex; align-items: center; gap: 10px;">
                <span class="nera-mono" style="font-size: 0.75rem; color: var(--emerald-light);">STATUS: 200 OK • WORKFLOW DISPATCHER ACTIVE</span>
              </div>
              <a href="/demo" class="nera-btn nera-btn-ghost nera-btn-sm" data-link="/demo">Launch Interactive Studio →</a>
            </div>
          </div>
        </section>

        <!-- Product Narrative: The Three Business Automation Offerings -->
        <section style="margin: 80px 0 60px;">
          <div style="text-align: center; margin-bottom: 48px;">
            <div class="nera-badge nera-badge-blue" style="margin-bottom: 12px;">Operational Architecture</div>
            <h2 style="font-size: 2.25rem; font-weight: 800; letter-spacing: -0.02em;">Two agents. Clear boundaries.</h2>
            <p style="color: var(--slate-light); max-width: 680px; margin: 12px auto 0; font-size: 1rem; line-height: 1.6;">
              Your Sales Representative turns questions into qualified leads and clear quotes. Your Support Agent answers from approved knowledge and hands off what it cannot verify.
            </p>
          </div>

          <div class="nera-product-grid">
            <!-- AI Sales Representative -->
            <div class="nera-card nera-card-interactive" style="display: flex; flex-direction: column;">
              <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px;">
                <div>
                  <span class="nera-badge nera-badge-blue" style="margin-bottom: 8px;">AI Sales Representative</span>
                  <h3 style="font-size: 1.5rem; font-weight: 800;">Your sales, in motion.</h3>
                </div>
                <div style="text-align: right;">
                  <span class="nera-price-tag" style="font-size: 1.75rem;">₦199,000</span>
                  <div class="nera-price-period">/ month base</div>
                </div>
              </div>

              <p style="color: var(--slate-light); font-size: 0.9375rem; margin-bottom: 24px; line-height: 1.6;">
                Qualifies inbound leads, calculates quotes from your pricing rules, and shares a Paystack checkout link right in the conversation. No invented prices or surprise discounts.
              </p>

              <div style="background: var(--bg-ground); padding: 16px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle); margin-bottom: 24px; flex: 1 0 auto;">
                <div style="font-size: 0.8125rem; font-weight: 700; color: var(--electric-blue-light); margin-bottom: 8px; text-transform: uppercase;">
                  Handles:
                </div>
                <ul style="list-style: none; display: flex; flex-direction: column; gap: 8px; font-size: 0.875rem; color: var(--ivory-dim);">
                  <li>✓ <strong>Lead qualification:</strong> Gets the details needed to recommend a fit.</li>
                  <li>✓ <strong>Rule-based quotes:</strong> Uses your published pricing, not a model&#39;s guess.</li>
                  <li>✓ <strong>Checkout links:</strong> Sends secure Paystack links and verifies payment.</li>
                  <li>✓ <strong>Follow-ups:</strong> Re-engages leads on schedule.</li>
                </ul>
              </div>

              <div style="display: flex; gap: 12px;">
                <a href="/products" class="nera-btn nera-btn-secondary" style="flex: 1; text-align: center;" data-link="/products">Workflow Details</a>
                <a href="/build?product=sales_agent" class="nera-btn nera-btn-primary" style="flex: 1; text-align: center;" data-link="/build">Configure Sales</a>
              </div>
            </div>

            <!-- AI Support Agent -->
            <div class="nera-card nera-card-interactive" style="display: flex; flex-direction: column;">
              <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px;">
                <div>
                  <span class="nera-badge nera-badge-emerald" style="margin-bottom: 8px;">AI Support Agent</span>
                  <h3 style="font-size: 1.5rem; font-weight: 800;">Support that knows its limits.</h3>
                </div>
                <div style="text-align: right;">
                  <span class="nera-price-tag" style="font-size: 1.75rem;">₦149,000</span>
                  <div class="nera-price-period">/ month base</div>
                </div>
              </div>

              <p style="color: var(--slate-light); font-size: 0.9375rem; margin-bottom: 24px; line-height: 1.6;">
                Answers from your approved knowledge, checks order and delivery status, and routes tricky requests to your team with the conversation context attached.
              </p>

              <div style="background: var(--bg-ground); padding: 16px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle); margin-bottom: 24px; flex: 1 0 auto;">
                <div style="font-size: 0.8125rem; font-weight: 700; color: var(--emerald-light); margin-bottom: 8px; text-transform: uppercase;">
                  Handles:
                </div>
                <ul style="list-style: none; display: flex; flex-direction: column; gap: 8px; font-size: 0.875rem; color: var(--ivory-dim);">
                  <li>✓ <strong>Trusted answers:</strong> Stays grounded in your approved business knowledge.</li>
                  <li>✓ <strong>Order updates:</strong> Checks connected order and tracking records.</li>
                  <li>✓ <strong>Returns triage:</strong> Checks requests against your policies before action.</li>
                  <li>✓ <strong>Human handoff:</strong> Passes your team the full context when needed.</li>
                </ul>
              </div>

              <div style="display: flex; gap: 12px;">
                <a href="/products" class="nera-btn nera-btn-secondary" style="flex: 1; text-align: center;" data-link="/products">Workflow Details</a>
                <a href="/build?product=support_agent" class="nera-btn nera-btn-primary" style="flex: 1; text-align: center;" data-link="/build">Configure Support</a>
              </div>
            </div>

            <!-- Workforce Combined Offering -->
            <div class="workforce-banner-card">
              <div style="display: grid; grid-template-columns: 1.4fr 1fr; gap: 32px; align-items: center;">
                <div>
                  <div class="nera-badge nera-badge-emerald" style="margin-bottom: 12px;">Unified Dual-Engine Pipeline</div>
                  <h3 style="font-size: 1.85rem; font-weight: 800; margin-bottom: 8px;">
                    Both agents, working together
                  </h3>
                  <p style="color: var(--slate-light); font-size: 1rem; line-height: 1.6; margin-bottom: 20px;">
                    Pair both agents with shared business context. When a sale is complete, Support can pick up the customer, order, and terms without asking them to start over.
                  </p>
                  <div style="display: flex; gap: 16px; align-items: center; flex-wrap: wrap;">
                    <a href="/workforce" class="nera-btn nera-btn-primary nera-btn-lg" data-link="/workforce">
                      See how they work together
                    </a>
                    <a href="/build?product=workforce_agent" class="nera-btn nera-btn-secondary nera-btn-lg" data-link="/build">
                      Set up both agents
                    </a>
                  </div>
                </div>

                <div style="background: var(--bg-ground); padding: 24px; border-radius: var(--radius-xl); border: 1px solid var(--border-subtle);">
                  <div style="font-size: 0.8125rem; font-weight: 700; color: var(--emerald-light); margin-bottom: 4px;">CATALOG COMBINATION PRICE</div>
                  <div style="display: flex; align-items: baseline; gap: 8px; margin-bottom: 16px;">
                    <span class="nera-price-tag" style="font-size: 2.2rem; color: var(--emerald-light);">₦348,000</span>
                    <span class="nera-price-period">/ month base</span>
                  </div>
                  <ul style="list-style: none; display: flex; flex-direction: column; gap: 10px; font-size: 0.875rem; color: var(--ivory-dim);">
                    <li>✓ <strong>Complete Workflow Pipeline:</strong> Intake → Quote → Payment → Support</li>
                    <li>✓ <strong>Shared Business Context:</strong> Zero lost customer or order records</li>
                    <li>✓ <strong>Omnichannel Coordination:</strong> Web chat widget &amp; Telegram bots</li>
                    <li>✓ <strong>Bundled Savings:</strong> ₦50,000/mo discount vs independent setups</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- Provable Capability Matrix: Truth in Capabilities -->
        <section style="margin: 80px 0 60px;">
          <div style="text-align: center; margin-bottom: 40px;">
            <div class="nera-badge nera-badge-emerald" style="margin-bottom: 12px;">Provable Capability Matrix</div>
            <h2 style="font-size: 2rem; font-weight: 800;">Proof over promises.</h2>
            <p style="color: var(--slate-light); font-size: 0.9375rem; max-width: 640px; margin: 8px auto 0;">
              See what works now, what needs setup, and what is still planned. If an agent cannot verify an answer, it should say so.
            </p>
          </div>

          <div style="overflow-x: auto;">
            <table class="capability-matrix-table">
              <thead>
                <tr>
                  <th style="width: 28%;">Workflow Domain</th>
                  <th style="width: 44%;">Operational Capability &amp; Scope</th>
                  <th style="width: 28%;">Implementation Status</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>Commercial Quoting</strong></td>
                  <td>Deterministic line-item price calculation based on base plan, conversation volume, channel count, and add-ons via pure integer math. Generative models cannot alter prices.</td>
                  <td><span class="badge-status-verified"><span class="anim-pulse-dot" style="width: 6px; height: 6px; background: currentColor; border-radius: 50%;"></span> Available &amp; Verified</span></td>
                </tr>
                <tr>
                  <td><strong>Payment Settlement</strong></td>
                  <td>Paystack API integration generating cryptographically verified payment links with HMAC SHA-512 webhook authentication and idempotent provisioning.</td>
                  <td><span class="badge-status-verified"><span class="anim-pulse-dot" style="width: 6px; height: 6px; background: currentColor; border-radius: 50%;"></span> Available &amp; Verified</span></td>
                </tr>
                <tr>
                  <td><strong>Cross-Engine Handoff</strong></td>
                  <td>Post-purchase context synchronization passing customer identity, plan details, and transaction references from Sales to Support engine.</td>
                  <td><span class="badge-status-verified"><span class="anim-pulse-dot" style="width: 6px; height: 6px; background: currentColor; border-radius: 50%;"></span> Available &amp; Verified</span></td>
                </tr>
                <tr>
                  <td><strong>Support Knowledge Base</strong></td>
                  <td>Grounded question answering from verified company documents. Refuses out-of-scope inquiries and alerts human team on sentiment triggers.</td>
                  <td><span class="badge-status-config">⚙️ Requires Configuration (Docs)</span></td>
                </tr>
                <tr>
                  <td><strong>Telegram Messaging</strong></td>
                  <td>Bi-directional automated messaging over Telegram with webhook updates and conversation state persistence.</td>
                  <td><span class="badge-status-config">⚙️ Requires Configuration (Token)</span></td>
                </tr>
                <tr>
                  <td><strong>Custom Catalog Sync</strong></td>
                  <td>Ingestion of custom merchandise catalogs and custom pricing matrices via structured CSV/JSON upload.</td>
                  <td><span class="badge-status-config">⚙️ Requires Configuration (Upload)</span></td>
                </tr>
                <tr>
                  <td><strong>Enterprise ERP Sync</strong></td>
                  <td>Automated multi-warehouse inventory level reservation and enterprise SAP/Oracle sync pipelines.</td>
                  <td><span class="badge-status-planned">⏳ Planned Future Roadmap</span></td>
                </tr>
                <tr>
                  <td><strong>Autonomous Voice Calls</strong></td>
                  <td>Outbound AI phone calling for logistics dispatch confirmation and debt recovery negotiations.</td>
                  <td><span class="badge-status-planned">⏳ Planned Future Roadmap</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- Industry Workflow Blueprints -->
        <section style="margin: 80px 0; background: var(--bg-surface-elevated); padding: 48px; border-radius: var(--radius-2xl); border: 1px solid var(--border-card);">
          <div style="text-align: center; margin-bottom: 36px;">
            <div class="nera-badge nera-badge-blue" style="margin-bottom: 8px;">Industry Blueprints</div>
            <h2 style="font-size: 2rem; font-weight: 800;">Real Workflows Automated Across Commerce</h2>
            <p style="color: var(--slate-light); font-size: 0.9375rem; max-width: 600px; margin: 8px auto 0;">
              See how business operations run on autopilot with Nera.
            </p>
          </div>

          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 24px;">
            <div class="nera-card" style="background: var(--bg-surface); padding: 24px;">
              <div style="font-size: 1.75rem; margin-bottom: 12px;">🛍️</div>
              <h4 style="font-size: 1.125rem; font-weight: 700; margin-bottom: 6px;">eCommerce &amp; Retail</h4>
              <p style="font-size: 0.875rem; color: var(--slate-light); line-height: 1.5; margin-bottom: 12px;">
                Automates product queries, checks size/stock parameters, generates instant Paystack checkout links, and routes verified orders to dispatch.
              </p>
              <div class="nera-mono" style="font-size: 0.75rem; color: var(--emerald-light);">WORKFLOW: INQUIRY → PAYLINK → ORDER SYNC</div>
            </div>

            <div class="nera-card" style="background: var(--bg-surface); padding: 24px;">
              <div style="font-size: 1.75rem; margin-bottom: 12px;">📦</div>
              <h4 style="font-size: 1.125rem; font-weight: 700; margin-bottom: 6px;">Logistics &amp; Dispatch</h4>
              <p style="font-size: 0.875rem; color: var(--slate-light); line-height: 1.5; margin-bottom: 12px;">
                Collects package weight and destination points, quotes deterministic waybill fees, confirms bank payments, and provides 24/7 status lookups.
              </p>
              <div class="nera-mono" style="font-size: 0.75rem; color: var(--electric-blue-light);">WORKFLOW: DIMENSIONS → WAYBILL → TRACKING</div>
            </div>

            <div class="nera-card" style="background: var(--bg-surface); padding: 24px;">
              <div style="font-size: 1.75rem; margin-bottom: 12px;">💼</div>
              <h4 style="font-size: 1.125rem; font-weight: 700; margin-bottom: 6px;">Professional Services</h4>
              <p style="font-size: 0.875rem; color: var(--slate-light); line-height: 1.5; margin-bottom: 12px;">
                Conducts initial intake scoping, qualifies project scope against service tiers, calculates retainer invoices, and schedules initial onboarding.
              </p>
              <div class="nera-mono" style="font-size: 0.75rem; color: var(--emerald-light);">WORKFLOW: INTAKE → TIER FIT → RETAINER INVOICE</div>
            </div>
          </div>
        </section>

        <!-- Final CTA Strip -->
        <section style="text-align: center; padding: 60px 24px; background: radial-gradient(circle at center, rgba(16, 185, 129, 0.12), transparent 70%); border-radius: var(--radius-2xl); border: 1px solid var(--border-emerald-glow); margin: 60px 0;">
          <h2 style="font-size: 2.25rem; font-weight: 800; margin-bottom: 12px;">Put the busywork on Nera.</h2>
          <p style="color: var(--slate-light); max-width: 580px; margin: 0 auto 28px; font-size: 1.0625rem;">
            Set up your AI Sales Representative or AI Support Agent, then see how each handles a real conversation.
          </p>
          <div style="display: flex; gap: 16px; justify-content: center; flex-wrap: wrap;">
            <a href="/build" class="nera-btn nera-btn-primary nera-btn-lg" data-link="/build">Set up your agents</a>
            <a href="/demo" class="nera-btn nera-btn-secondary nera-btn-lg" data-link="/demo">Try a conversation</a>
          </div>
        </section>
      </div>
    `;
  }

  onMounted() {
    this.updateOrchestrationCanvas();

    // Toggle button listeners on orchestration canvas
    document.querySelectorAll('.workflow-tab-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.workflow-tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.activeWorkflowTab = btn.getAttribute('data-workflow');
        this.updateOrchestrationCanvas();
      });
    });

    // Step indicators click listener
    document.querySelectorAll('.pipeline-step').forEach(stepEl => {
      stepEl.addEventListener('click', () => {
        const stepNum = parseInt(stepEl.getAttribute('data-step'), 10);
        this.activeStep = stepNum;
        this.updateStepperVisual();
        this.updateOrchestrationCanvas();
      });
    });

    // SPA link intercept
    document.querySelectorAll('[data-link]').forEach(anchor => {
      anchor.addEventListener('click', (e) => {
        e.preventDefault();
        const targetPath = anchor.getAttribute('data-link');
        this.router.navigate(targetPath);
      });
    });
  }

  updateStepperVisual() {
    document.querySelectorAll('.pipeline-step').forEach(el => {
      const step = parseInt(el.getAttribute('data-step'), 10);
      if (step <= this.activeStep) {
        el.classList.add('active');
      } else {
        el.classList.remove('active');
      }
    });
  }

  updateOrchestrationCanvas() {
    const box = document.getElementById('canvas-network-content');
    if (!box) return;

    if (this.activeWorkflowTab === 'sales') {
      box.innerHTML = `
        <div class="orchestration-network anim-fade-in">
          <div class="orchestration-core">
            <div class="orchestration-emblem-wrap anim-pulse-glow">
              <img src="/frontend/src/brand/nera-emblem.svg" alt="Nera" width="32" height="32" />
            </div>
            <strong style="font-size: 0.9375rem; color: var(--ivory);">Nera AI Sales Representative</strong>
            <span class="nera-mono" style="font-size: 0.75rem; color: var(--emerald-light); margin-top: 2px;">
              ACTIVE PIPELINE: INTAKE → DETERMINISTIC QUOTE → PAYSTACK SETTLEMENT
            </span>
          </div>

          <div class="orchestration-nodes-grid">
            <div class="node-card active">
              <span class="node-card-tag">Step 1: Activity</span>
              <div class="node-card-name">Buyer Requirements Intake</div>
              <div class="node-card-status"><span>✓</span> Scoped 500 inquiries/mo</div>
            </div>
            <div class="node-card active">
              <span class="node-card-tag">Step 2: Pricing Logic</span>
              <div class="node-card-name">Zero-LLM Math Engine</div>
              <div class="node-card-status"><span>✓</span> Line items: ₦201,500 calculated</div>
            </div>
            <div class="node-card active">
              <span class="node-card-tag">Step 3: Outcome</span>
              <div class="node-card-name">Paystack Paylink Dispatched</div>
              <div class="node-card-status"><span>✓</span> Ref: #CHK-9812 verified</div>
            </div>
          </div>
        </div>

        <div class="task-ticker anim-fade-in">
          <span class="task-ticker-badge">EXECUTING WORKFLOW</span>
          <span class="task-ticker-text">Task #S-4819: Buyer input received → Requirements scoped → Deterministic quote ₦201,500 dispatched via Paystack</span>
        </div>

        <div class="canvas-metrics anim-fade-in">
          <div class="metric-box">
            <div class="metric-val">₦201,500</div>
            <div class="metric-lbl">Calculated Quote</div>
          </div>
          <div class="metric-box">
            <div class="metric-val">100%</div>
            <div class="metric-lbl">Deterministic Pricing</div>
          </div>
          <div class="metric-box">
            <div class="metric-val">Sub-second</div>
            <div class="metric-lbl">Target Latency</div>
          </div>
        </div>
      `;
    } else if (this.activeWorkflowTab === 'support') {
      box.innerHTML = `
        <div class="orchestration-network anim-fade-in">
          <div class="orchestration-core">
            <div class="orchestration-emblem-wrap anim-pulse-glow">
              <img src="/frontend/src/brand/nera-emblem.svg" alt="Nera" width="32" height="32" />
            </div>
            <strong style="font-size: 0.9375rem; color: var(--ivory);">Nera AI Support Agent</strong>
            <span class="nera-mono" style="font-size: 0.75rem; color: var(--emerald-light); margin-top: 2px;">
              ACTIVE PIPELINE: TICKET INTAKE → GROUNDED RESOLUTION → ESCALATION TRIAGE
            </span>
          </div>

          <div class="orchestration-nodes-grid">
            <div class="node-card active">
              <span class="node-card-tag">Step 1: Activity</span>
              <div class="node-card-name">Inbound Care Request</div>
              <div class="node-card-status"><span>✓</span> Tracking query #ORD-842</div>
            </div>
            <div class="node-card active">
              <span class="node-card-tag">Step 2: Grounded DB</span>
              <div class="node-card-name">Live Order State Lookup</div>
              <div class="node-card-status"><span>✓</span> Status: IN_TRANSIT, Lagos</div>
            </div>
            <div class="node-card active">
              <span class="node-card-tag">Step 3: Outcome</span>
              <div class="node-card-name">Instant Resolution Sent</div>
              <div class="node-card-status"><span>✓</span> Delivery ETA confirmed</div>
            </div>
          </div>
        </div>

        <div class="task-ticker anim-fade-in">
          <span class="task-ticker-badge">EXECUTING WORKFLOW</span>
          <span class="task-ticker-text">Task #SP-1092: Order tracking inquiry #ORD-842 → Validated against database tokens → 0 human delay</span>
        </div>

        <div class="canvas-metrics anim-fade-in">
          <div class="metric-box">
            <div class="metric-val">₦149,000</div>
            <div class="metric-lbl">Base Monthly Tier</div>
          </div>
          <div class="metric-box">
            <div class="metric-val">78%</div>
            <div class="metric-lbl">Tier-1 Resolution</div>
          </div>
          <div class="metric-box">
            <div class="metric-val">24/7</div>
            <div class="metric-lbl">Automated Care</div>
          </div>
        </div>
      `;
    } else if (this.activeWorkflowTab === 'workforce') {
      box.innerHTML = `
        <div class="orchestration-network anim-fade-in">
          <div class="orchestration-core">
            <div class="orchestration-emblem-wrap anim-pulse-glow">
              <img src="/frontend/src/brand/nera-emblem.svg" alt="Nera" width="32" height="32" />
            </div>
            <strong style="font-size: 0.9375rem; color: var(--ivory);">Nera Unified Workforce Pipeline</strong>
            <span class="nera-mono" style="font-size: 0.75rem; color: var(--emerald-light); margin-top: 2px;">
              ACTIVE PIPELINE: SALES CONVERSION ➔ SETTLEMENT ➔ SUPPORT CONTEXT HANDOFF
            </span>
          </div>

          <div class="orchestration-nodes-grid">
            <div class="node-card active">
              <span class="node-card-tag">Acquisition Engine</span>
              <div class="node-card-name">Sales Closer (₦199k)</div>
              <div class="node-card-status"><span>✓</span> Quotes &amp; closes deal</div>
            </div>
            <div class="node-card active">
              <span class="node-card-tag">Settlement Layer</span>
              <div class="node-card-name">Paystack HMAC SHA512</div>
              <div class="node-card-status"><span>✓</span> Payment verified &amp; settled</div>
            </div>
            <div class="node-card active">
              <span class="node-card-tag">Fulfillment Engine</span>
              <div class="node-card-name">Support Care (₦149k)</div>
              <div class="node-card-status"><span>✓</span> Inherits complete context</div>
            </div>
          </div>
        </div>

        <div class="task-ticker anim-fade-in">
          <span class="task-ticker-badge">EXECUTING WORKFLOW</span>
          <span class="task-ticker-text">Task #WF-3301: Transaction settled → Customer memory synchronized → Support Engine welcomes buyer with order context</span>
        </div>

        <div class="canvas-metrics anim-fade-in">
          <div class="metric-box">
            <div class="metric-val">₦348,000</div>
            <div class="metric-lbl">Bundled Base</div>
          </div>
          <div class="metric-box">
            <div class="metric-val">Zero</div>
            <div class="metric-lbl">Lost Customer Details</div>
          </div>
          <div class="metric-box">
            <div class="metric-val">₦50,000</div>
            <div class="metric-lbl">Monthly Bundle Savings</div>
          </div>
        </div>
      `;
    } else {
      // 'all' workflows overview
      box.innerHTML = `
        <div class="orchestration-network anim-fade-in">
          <div class="orchestration-core">
            <div class="orchestration-emblem-wrap anim-pulse-glow">
              <img src="/frontend/src/brand/nera-emblem.svg" alt="Nera" width="32" height="32" />
            </div>
            <strong style="font-size: 0.9375rem; color: var(--ivory);">Nera Autonomous Operations Network</strong>
            <span class="nera-mono" style="font-size: 0.75rem; color: var(--emerald-light); margin-top: 2px;">
              COORDINATING: BUSINESS ACTIVITY → NERA ORCHESTRATION → AUTOMATED WORKFLOWS → COMPLETED OUTCOMES
            </span>
          </div>

          <div class="orchestration-nodes-grid">
            <div class="node-card active">
              <span class="node-card-tag">Node A: Intake</span>
              <div class="node-card-name">Multi-Channel Inbound</div>
              <div class="node-card-status"><span>●</span> Web Widget &amp; Telegram</div>
            </div>
            <div class="node-card active">
              <span class="node-card-tag">Node B: Logic</span>
              <div class="node-card-name">Deterministic Math Rules</div>
              <div class="node-card-status"><span>●</span> Verified Rule-Based Calculation</div>
            </div>
            <div class="node-card active">
              <span class="node-card-tag">Node C: Execution</span>
              <div class="node-card-name">Automated Settlement</div>
              <div class="node-card-status"><span>●</span> Paystack HMAC SHA512</div>
            </div>
          </div>
        </div>

        <div class="task-ticker anim-fade-in">
          <span class="task-ticker-badge" style="background: rgba(59, 130, 246, 0.2); color: var(--electric-blue-light); border: 1px solid var(--electric-blue);">INTERACTIVE PREVIEW</span>
          <span class="task-ticker-text">Simulated workflow execution: Task progression across Sales, Settlement, and Customer Care pipelines</span>
        </div>

        <div class="canvas-metrics anim-fade-in">
          <div class="metric-box">
            <div class="metric-val">14 Flows</div>
            <div class="metric-lbl">Simulated Pipeline</div>
          </div>
          <div class="metric-box">
            <div class="metric-val">100%</div>
            <div class="metric-lbl">Deterministic Rules</div>
          </div>
          <div class="metric-box">
            <div class="metric-val">Sub-second</div>
            <div class="metric-lbl">Target Cycle Time</div>
          </div>
        </div>
      `;
    }
  }
}
