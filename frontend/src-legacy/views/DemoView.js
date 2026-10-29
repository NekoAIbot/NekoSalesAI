/**
 * Nera 2.0 Greenfield — Demo Studio View
 * Public demos show the two products currently supported by Nera.
 */
import { api } from '../core/api.js';
import { store } from '../core/store.js';

export class DemoView {
  constructor({ router }) {
    this.router = router;
    this.activeTab = 'sales'; // 'sales' | 'support'
    this.salesToken = null;
    this.isSubmitting = false;

    // Support simulation state
    this.supportMessages = [
      {
        sender: 'support',
        meta: 'NERA SUPPORT ENGINE • RESOLUTION PIPELINE',
        text: "This tab is a visual simulation of the AI Support Agent. It does not connect to a live customer knowledge base or order system."
      }
    ];

    // Workforce simulation state
    this.workforceMessages = [
      {
        sender: 'system',
        meta: 'WORKFORCE ORCHESTRATOR • SYNCHRONIZED PIPELINE',
        text: 'Workforce Pipeline active. Observe how the Sales Engine scopes commercial requirements, confirms settlement, and smoothly hands off the account to the Support Engine with full context intact.'
      },
      {
        sender: 'sales',
        meta: 'NERA SALES ENGINE • INTAKE WORKFLOW',
        text: 'Welcome to SwiftPay Africa! I see you are inquiring about our Enterprise API integration. What monthly transaction volume are you looking to support?'
      }
    ];
  }

  async render() {
    return `
      <div class="anim-fade-in-up" style="max-width: 960px; margin: 0 auto;">
        <!-- Header -->
        <div style="text-align: center; margin-bottom: 32px;">
          <div class="nera-badge nera-badge-emerald" style="margin-bottom: 12px;">
            <span class="nera-badge-dot anim-pulse-dot"></span>
            Product demo
          </div>
          <h1 style="font-size: 2.25rem; font-weight: 800; letter-spacing: -0.02em;">
            See the two products <span class="gradient-text">Nera builds today</span>
          </h1>
          <p style="color: var(--slate-light); font-size: 0.9375rem; margin-top: 8px; max-width: 640px; margin-left: auto; margin-right: auto; line-height: 1.6;">
            The sales demo connects to the live sales conversation route. The support tab is a visual simulation, not a live support backend.
          </p>
        </div>

        <!-- Tab Selector -->
        <div style="display: flex; justify-content: center; gap: 8px; margin-bottom: 24px; flex-wrap: wrap;">
          <button id="tab-btn-sales" class="nera-btn ${this.activeTab === 'sales' ? 'nera-btn-primary' : 'nera-btn-secondary'}" style="padding: 10px 20px; font-size: 0.875rem;">
            AI Sales Representative (live)
          </button>
          <button id="tab-btn-support" class="nera-btn ${this.activeTab === 'support' ? 'nera-btn-primary' : 'nera-btn-secondary'}" style="padding: 10px 20px; font-size: 0.875rem;">
            AI Support Agent (simulation)
          </button>
        </div>

        <!-- Studio Playground Frame -->
        <div class="nera-chat-hud" style="box-shadow: var(--shadow-elevated);">
          
          <!-- TAB 1: SALES AGENT (LIVE) -->
          <div id="pane-sales" style="display: ${this.activeTab === 'sales' ? 'block' : 'none'};">
            <!-- HUD Header -->
            <div class="nera-chat-hud-header">
              <div style="display: flex; align-items: center; gap: 12px;">
                <span class="nera-badge-dot anim-pulse-dot"></span>
                <div>
                  <strong style="font-size: 0.9375rem;">AI Sales Representative</strong>
                  <div style="font-size: 0.75rem; color: var(--emerald-light);">Live Pipeline • /api/v1/sales/conversations</div>
                </div>
              </div>
              <button id="reset-sales-btn" class="nera-btn nera-btn-ghost nera-btn-sm" title="Start fresh conversation">
                🔄 Reset Session
              </button>
            </div>

            <!-- Chat Messages Body -->
            <div id="sales-chat-messages" class="nera-chat-hud-body" style="min-height: 380px; max-height: 480px;">
              <div class="bubble bubble-agent">
                <div class="bubble-agent-meta">
                  <span>NERA SALES ENGINE</span> • <span>ONLINE</span>
                </div>
                Hello! I am Nera's sales automation engine. I coordinate requirements intake, compute deterministic line-item pricing, and execute checkout workflows. How can I help automate your business today?
              </div>
            </div>

            <!-- Chat Input Footer -->
            <div class="nera-chat-hud-footer">
              <form id="sales-chat-form" style="display: flex; gap: 12px;">
                <input 
                  type="text" 
                  id="sales-input" 
                  class="nera-input" 
                  placeholder="Ask for pricing, describe your business requirements, or request a quote..." 
                  autocomplete="off" 
                  required 
                />
                <button type="submit" id="sales-submit-btn" class="nera-btn nera-btn-primary" style="padding: 0 24px;">
                  Send
                </button>
              </form>
            </div>
          </div>

          <!-- TAB 2: SUPPORT AGENT (SIMULATION) -->
          <div id="pane-support" style="display: ${this.activeTab === 'support' ? 'block' : 'none'};">
            <!-- HUD Header -->
            <div class="nera-chat-hud-header">
              <div style="display: flex; align-items: center; gap: 12px;">
                <span class="nera-badge-dot" style="background: var(--electric-blue);"></span>
                <div>
                  <strong style="font-size: 0.9375rem;">AI Support Agent</strong>
                  <div style="font-size: 0.75rem; color: var(--electric-blue-light);">Support demo • simulated responses</div>
                </div>
              </div>
              <div style="display: flex; gap: 8px;">
                <button class="nera-btn nera-btn-ghost nera-btn-sm support-preset-btn" data-query="Where is order #ORD-9842?">
                  📦 Check #ORD-9842
                </button>
                <button class="nera-btn nera-btn-ghost nera-btn-sm support-preset-btn" data-query="What is your return policy?">
                  📄 Return Policy
                </button>
                <button class="nera-btn nera-btn-ghost nera-btn-sm support-preset-btn" data-query="I need to speak to an operator">
                  👤 Operator Handoff
                </button>
              </div>
            </div>

            <!-- Chat Messages Body -->
            <div id="support-chat-messages" class="nera-chat-hud-body" style="min-height: 380px; max-height: 480px;">
              <!-- Rendered by updateSupportChat() -->
            </div>

            <!-- Chat Input Footer -->
            <div class="nera-chat-hud-footer">
              <form id="support-chat-form" style="display: flex; gap: 12px;">
                <input 
                  type="text" 
                  id="support-input" 
                  class="nera-input" 
                  placeholder="Ask a customer service or tracking inquiry..." 
                  autocomplete="off" 
                  required 
                />
                <button type="submit" class="nera-btn nera-btn-primary" style="padding: 0 24px;">
                  Send
                </button>
              </form>
            </div>
          </div>


        </div>
      </div>
    `;
  }

  onMounted() {
    this.setupTabSwitching();
    this.setupSalesChat();
    this.setupSupportChat();

    document.querySelectorAll('[data-link]').forEach(anchor => {
      anchor.addEventListener('click', (e) => {
        e.preventDefault();
        const targetPath = anchor.getAttribute('data-link');
        this.router.navigate(targetPath);
      });
    });
  }

  setupTabSwitching() {
    const tabs = ['sales', 'support'];
    tabs.forEach(tab => {
      const btn = document.getElementById(`tab-btn-${tab}`);
      if (btn) {
        btn.addEventListener('click', () => {
          this.activeTab = tab;
          tabs.forEach(t => {
            const b = document.getElementById(`tab-btn-${t}`);
            const p = document.getElementById(`pane-${t}`);
            if (b) {
              b.className = `nera-btn ${t === tab ? 'nera-btn-primary' : 'nera-btn-secondary'}`;
            }
            if (p) {
              p.style.display = (t === tab) ? 'block' : 'none';
            }
          });

          if (tab === 'support') this.updateSupportChat();
          if (tab === 'workforce') this.updateWorkforceChat();
        });
      }
    });
  }

  setupSalesChat() {
    const form = document.getElementById('sales-chat-form');
    const input = document.getElementById('sales-input');
    const resetBtn = document.getElementById('reset-sales-btn');
    const box = document.getElementById('sales-chat-messages');

    if (resetBtn) {
      resetBtn.addEventListener('click', () => {
        this.salesToken = null;
        if (box) {
          box.innerHTML = `
            <div class="bubble bubble-agent">
              <div class="bubble-agent-meta">
                <span>NERA SALES ENGINE</span> • <span>ONLINE</span>
              </div>
              Session reset. How can I help scope your business requirements today?
            </div>
          `;
        }
      });
    }

    if (form && input) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text || this.isSubmitting) return;

        input.value = '';
        this.appendSalesBubble('user', text);
        this.isSubmitting = true;

        const typingBubble = document.createElement('div');
        typingBubble.className = 'bubble bubble-agent';
        typingBubble.id = 'sales-typing';
        typingBubble.innerHTML = '<span class="anim-pulse-dot" style="display:inline-block;width:8px;height:8px;background:var(--emerald-light);border-radius:50%;"></span> Executing workflow...';
        box.appendChild(typingBubble);
        box.scrollTop = box.scrollHeight;

        try {
          let data;
          if (!this.salesToken) {
            data = await api.startSalesConversation(text);
            this.salesToken = data.conversation_token || data.token;
          } else {
            data = await api.sendSalesMessage(this.salesToken, text);
          }

          const existingTyping = document.getElementById('sales-typing');
          if (existingTyping) existingTyping.remove();

          const reply = data.reply || data.message || "I've processed your inquiry and updated your quotation.";
          this.appendSalesBubble('agent', reply);
        } catch (err) {
          console.error('Sales demo error:', err);
          const existingTyping = document.getElementById('sales-typing');
          if (existingTyping) existingTyping.remove();
          this.appendSalesBubble('agent', `I encountered an issue connecting to the sales pipeline: ${err.message || 'Please retry.'}`);
        } finally {
          this.isSubmitting = false;
        }
      });
    }
  }

  appendSalesBubble(type, text) {
    const box = document.getElementById('sales-chat-messages');
    if (!box) return;

    const div = document.createElement('div');
    div.className = `bubble bubble-${type} anim-fade-in`;
    if (type === 'agent') {
      div.innerHTML = `
        <div class="bubble-agent-meta">
          <span>NERA SALES ENGINE</span> • <span>SALES RESPONSE</span>
        </div>
        ${this.formatMarkdown(text)}
      `;
    } else {
      div.textContent = text;
    }
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }

  setupSupportChat() {
    this.updateSupportChat();

    const form = document.getElementById('support-chat-form');
    const input = document.getElementById('support-input');

    document.querySelectorAll('.support-preset-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const query = btn.getAttribute('data-query');
        this.handleSupportInquiry(query);
      });
    });

    if (form && input) {
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        input.value = '';
        this.handleSupportInquiry(text);
      });
    }
  }

  handleSupportInquiry(text) {
    this.supportMessages.push({ sender: 'user', text });
    this.updateSupportChat();

    setTimeout(() => {
      let reply = '';
      const lower = text.toLowerCase();

      if (lower.includes('9842') || lower.includes('order') || lower.includes('tracking')) {
        reply = 'Example only: an AI Support Agent can answer order-status questions when connected to a business's verified order system.';
      } else if (lower.includes('return') || lower.includes('policy') || lower.includes('refund')) {
        reply = 'Example only: an AI Support Agent can answer policy questions using material provided by the business.';
      } else if (lower.includes('operator') || lower.includes('human') || lower.includes('agent')) {
        reply = 'Example only: the AI Support Agent is designed to escalate commercial questions to a person.';
      } else {
        reply = `This support tab is a simulation, so it cannot verify an answer about: "${text}". A deployed Support Agent answers from the business's own provided material.`;
      }

      this.supportMessages.push({
        sender: 'support',
        meta: 'NERA SUPPORT ENGINE • GROUNDED ANSWER',
        text: reply
      });
      this.updateSupportChat();
    }, 600);
  }

  updateSupportChat() {
    const box = document.getElementById('support-chat-messages');
    if (!box) return;

    box.innerHTML = this.supportMessages.map(m => {
      if (m.sender === 'user') {
        return `<div class="bubble bubble-user anim-fade-in">${m.text}</div>`;
      } else {
        return `
          <div class="bubble bubble-agent anim-fade-in" style="background: rgba(15, 23, 42, 0.7); border-color: rgba(59, 130, 246, 0.3);">
            <div class="bubble-agent-meta" style="color: var(--electric-blue-light);">
              <span>${m.meta}</span>
            </div>
            ${this.formatMarkdown(m.text)}
          </div>
        `;
      }
    }).join('');
    box.scrollTop = box.scrollHeight;
  }

  setupWorkforceChat() {
    this.updateWorkforceChat();

    const nextBtn = document.getElementById('next-workforce-step-btn');
    if (nextBtn) {
      let stepIndex = 0;
      const steps = [
        {
          sender: 'user',
          text: 'We do around 2,500 conversations a month and need Telegram plus CRM integration.'
        },
        {
          sender: 'sales',
          meta: 'NERA SALES ENGINE • QUOTE GENERATED',
          text: 'Understood. For 2,500 monthly transactions with Telegram and CRM, your deterministic quote is **₦251,500/month**. I have prepared your checkout reference `CHK-9024`. Here is your Paystack settlement link:\n\n👉 [Complete Paystack Payment](https://paystack.com)'
        },
        {
          sender: 'system',
          meta: 'PAYSTACK GATEWAY • HMAC SHA512 WEBHOOK',
          text: '💳 **Payment Confirmed:** Transaction `trx_84920491` verified via HMAC SHA512. Customer account provisioned idempotently. Initiating context handoff to Support Engine...'
        },
        {
          sender: 'support',
          meta: 'NERA SUPPORT ENGINE • WORKFLOW INITIALIZED',
          text: 'Welcome to Nera, SwiftPay Africa! I am your Support Engine. I have inherited your plan details (₦251.5k tier, Telegram + CRM connected). Your workspace is active and your API token is ready.'
        }
      ];

      nextBtn.addEventListener('click', () => {
        if (stepIndex < steps.length) {
          this.workforceMessages.push(steps[stepIndex]);
          stepIndex++;
          this.updateWorkforceChat();
          if (stepIndex >= steps.length) {
            nextBtn.textContent = '✓ Workflow Completed';
            nextBtn.disabled = true;
          }
        }
      });
    }
  }

  updateWorkforceChat() {
    const box = document.getElementById('workforce-chat-messages');
    if (!box) return;

    box.innerHTML = this.workforceMessages.map(m => {
      if (m.sender === 'user') {
        return `<div class="bubble bubble-user anim-fade-in">${m.text}</div>`;
      } else if (m.sender === 'system') {
        return `
          <div style="background: rgba(16, 185, 129, 0.1); border: 1px dashed var(--emerald); border-radius: var(--radius-md); padding: 12px 16px; margin: 8px 0; font-size: 0.8125rem;" class="anim-fade-in">
            <div style="font-size: 0.6875rem; color: var(--emerald-light); font-weight: 700; margin-bottom: 4px;">${m.meta}</div>
            ${this.formatMarkdown(m.text)}
          </div>
        `;
      } else if (m.sender === 'sales') {
        return `
          <div class="bubble bubble-agent anim-fade-in">
            <div class="bubble-agent-meta">
              <span>${m.meta}</span>
            </div>
            ${this.formatMarkdown(m.text)}
          </div>
        `;
      } else {
        return `
          <div class="bubble bubble-agent anim-fade-in" style="background: rgba(15, 23, 42, 0.7); border-color: rgba(59, 130, 246, 0.3);">
            <div class="bubble-agent-meta" style="color: var(--electric-blue-light);">
              <span>${m.meta}</span>
            </div>
            ${this.formatMarkdown(m.text)}
          </div>
        `;
      }
    }).join('');
    box.scrollTop = box.scrollHeight;
  }

  formatMarkdown(text) {
    if (!text) return '';
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code class="nera-mono" style="background:rgba(0,0,0,0.3);padding:2px 4px;border-radius:4px;color:var(--emerald-light);">$1</code>')
      .replace(/\n/g, '<br/>');
  }
}
