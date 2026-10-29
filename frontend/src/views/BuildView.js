/**
 * Nera 2.0 Greenfield — Build View (Business Automation Configurator)
 * Authoritative line-item calculation and Paystack checkout dispatch.
 */
import { api } from '../core/api.js';
import { store } from '../core/store.js';

export class BuildView {
  constructor({ router, query }) {
    this.router = router;
    this.query = query;
    this.selectedProduct = 'sales_agent';
    this.selectedChannels = ['web', 'telegram'];
    this.selectedIntegrations = ['crm'];
    this.selectedLanguages = ['en'];
    this.currentQuote = null;
    this.isSubmitting = false;

    // Check if product was passed in query params (e.g. ?product=support_agent or ?product=workforce_agent or ?agent=...)
    const productParam = query.get('product') || query.get('agent');
    if (productParam === 'support_agent' || productParam === 'support') {
      this.selectedProduct = 'support_agent';
    } else if (productParam === 'workforce_agent' || productParam === 'workforce') {
      this.selectedProduct = 'workforce_agent';
    }
  }

  async render() {
    return `
      <div class="anim-fade-in-up" style="max-width: 1040px; margin: 0 auto;">
        <!-- Header -->
        <section style="text-align: center; margin-bottom: 40px;">
          <div class="nera-badge nera-badge-emerald" style="margin-bottom: 12px;">
            <span class="nera-badge-dot anim-pulse-dot"></span>
            Business Automation Configurator
          </div>
          <h1 style="font-size: 2.5rem; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 8px;">
            Configure Your <span class="gradient-text">Business Automation</span>
          </h1>
          <p style="color: var(--slate-light); font-size: 1rem; max-width: 600px; margin: 0 auto;">
            Configure automation engines, communication channels, and integrations. Quotes are calculated deterministically before triggering secure Paystack checkout.
          </p>
        </section>

        <div style="display: grid; grid-template-columns: 1.35fr 1fr; gap: 40px; align-items: start;">
          <!-- Configuration Form -->
          <div class="nera-card" style="padding: 32px;">
            <h2 style="font-size: 1.25rem; font-weight: 700; margin-bottom: 24px; padding-bottom: 12px; border-bottom: 1px solid var(--border-subtle);">
              1. Choose Automation Engine
            </h2>

            <div style="display: grid; grid-template-columns: 1fr; gap: 12px; margin-bottom: 32px;">
              <label class="agent-role-card nera-card ${this.selectedProduct === 'sales_agent' ? 'nera-card-highlight' : ''}" style="cursor: pointer; padding: 16px; border-radius: var(--radius-md);">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                  <div style="display: flex; align-items: center; gap: 12px;">
                    <input type="radio" name="product_code" value="sales_agent" ${this.selectedProduct === 'sales_agent' ? 'checked' : ''} />
                    <div>
                      <strong>Sales Automation Engine</strong>
                      <div style="font-size: 0.8125rem; color: var(--slate-light);">Inbound qualification, line-item pricing, Paystack invoices.</div>
                    </div>
                  </div>
                  <strong class="nera-mono" style="color: var(--emerald-light);">₦199,000/mo</strong>
                </div>
              </label>

              <label class="agent-role-card nera-card ${this.selectedProduct === 'support_agent' ? 'nera-card-highlight' : ''}" style="cursor: pointer; padding: 16px; border-radius: var(--radius-md);">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                  <div style="display: flex; align-items: center; gap: 12px;">
                    <input type="radio" name="product_code" value="support_agent" ${this.selectedProduct === 'support_agent' ? 'checked' : ''} />
                    <div>
                      <strong>Support Automation Engine</strong>
                      <div style="font-size: 0.8125rem; color: var(--slate-light);">Grounded knowledge base, order tracking, human escalation.</div>
                    </div>
                  </div>
                  <strong class="nera-mono" style="color: var(--emerald-light);">₦149,000/mo</strong>
                </div>
              </label>

              <label class="agent-role-card nera-card ${this.selectedProduct === 'workforce_agent' ? 'nera-card-highlight' : ''}" style="cursor: pointer; padding: 16px; border-radius: var(--radius-md);">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                  <div style="display: flex; align-items: center; gap: 12px;">
                    <input type="radio" name="product_code" value="workforce_agent" ${this.selectedProduct === 'workforce_agent' ? 'checked' : ''} />
                    <div>
                      <strong>Workforce Pipeline (Sales + Support)</strong>
                      <div style="font-size: 0.8125rem; color: var(--slate-light);">Dual-engine deployment with synchronized shared business context.</div>
                    </div>
                  </div>
                  <strong class="nera-mono" style="color: var(--emerald-light);">₦348,000/mo</strong>
                </div>
              </label>
            </div>

            <h2 style="font-size: 1.25rem; font-weight: 700; margin-bottom: 24px; padding-bottom: 12px; border-bottom: 1px solid var(--border-subtle);">
              2. Channels, Integrations &amp; Languages
            </h2>

            <div class="nera-form-group">
              <label class="nera-label">Active Communication Channels</label>
              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 6px;">
                <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem;">
                  <input type="checkbox" name="channels" value="web" checked disabled /> Web Chat Widget (Included)
                </label>
                <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                  <input type="checkbox" name="channels" value="telegram" checked /> Telegram Bot (+₦4,000/mo)
                </label>
                <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                  <input type="checkbox" name="channels" value="whatsapp" /> WhatsApp Bot (+₦8,000/mo)
                </label>
                <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                  <input type="checkbox" name="channels" value="email" /> Email Helpdesk (+₦3,000/mo)
                </label>
              </div>
            </div>

            <div class="nera-form-group">
              <label class="nera-label">Enterprise Integrations (+₦2,000/mo each)</label>
              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 6px;">
                <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                  <input type="checkbox" name="integrations" value="crm" checked /> CRM Webhook (+₦2k)
                </label>
                <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                  <input type="checkbox" name="integrations" value="accounting" /> Accounting System (+₦2k)
                </label>
                <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                  <input type="checkbox" name="integrations" value="calendar" /> Calendar &amp; Scheduling (+₦2k)
                </label>
                <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                  <input type="checkbox" name="integrations" value="payment" /> Payment Gateway (+₦2k)
                </label>
                <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                  <input type="checkbox" name="integrations" value="helpdesk" /> Helpdesk &amp; Support (+₦2k)
                </label>
                <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                  <input type="checkbox" name="integrations" value="ecommerce" /> E-Commerce Platform (+₦2k)
                </label>
              </div>
            </div>

            <div class="nera-form-group">
              <label class="nera-label">Regional &amp; Multi-Language Support (+₦3,500/mo per extra)</label>
              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 6px;">
                <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem;">
                  <input type="checkbox" name="languages" value="en" checked disabled /> English (Included)
                </label>
                <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                  <input type="checkbox" name="languages" value="pid" /> Nigerian Pidgin (+₦3.5k)
                </label>
                <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                  <input type="checkbox" name="languages" value="yo" /> Yoruba (+₦3.5k)
                </label>
                <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                  <input type="checkbox" name="languages" value="ig" /> Igbo (+₦3.5k)
                </label>
                <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                  <input type="checkbox" name="languages" value="ha" /> Hausa (+₦3.5k)
                </label>
              </div>
            </div>

            <div class="nera-form-group">
              <div style="display: flex; justify-content: space-between; align-items: baseline;">
                <label class="nera-label">Monthly Transaction / Conversation Volume</label>
                <span style="font-size: 0.75rem; color: var(--slate-light);">Base 500 conv included in ₦2,500 charge</span>
              </div>
              <input type="range" id="volume-slider" min="500" max="10000" step="500" value="1000" style="width: 100%; margin: 8px 0;" />
              <div style="display: flex; justify-content: space-between; font-family: var(--font-mono); font-size: 0.8125rem; color: var(--emerald-light);">
                <span>Volume: <strong id="volume-val">1,000</strong> conversations</span>
                <span>₦5/conversation total</span>
              </div>
            </div>

            <h2 style="font-size: 1.25rem; font-weight: 700; margin: 32px 0 20px; padding-bottom: 12px; border-bottom: 1px solid var(--border-subtle);">
              3. Organization &amp; Account Details
            </h2>

            <div id="auth-status-banner" style="margin-bottom: 16px;"></div>

            <div class="nera-form-group">
              <label class="nera-label">Business / Company Name</label>
              <input type="text" id="builder-org-name" class="nera-input" placeholder="e.g. SwiftPay Africa" required />
            </div>

            <div class="nera-form-group">
              <label class="nera-label">Admin Email Address</label>
              <input type="email" id="builder-email" class="nera-input" placeholder="admin@swiftpay.ng" required />
            </div>
          </div>

          <!-- Authoritative Quote Summary Card -->
          <div class="nera-card nera-card-highlight" style="position: sticky; top: 100px; padding: 28px;">
            <div style="font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--emerald-light); margin-bottom: 8px;">
              Authoritative Quotation
            </div>

            <div style="display: flex; align-items: baseline; gap: 8px; margin-bottom: 20px;">
              <span class="nera-price-tag" id="summary-total-price">₦239,000</span>
              <span class="nera-price-period">/ month</span>
            </div>

            <div style="border-top: 1px solid var(--border-subtle); padding: 16px 0; margin-bottom: 20px;">
              <div style="font-size: 0.8125rem; font-weight: 700; color: var(--slate-light); margin-bottom: 12px; text-transform: uppercase;">
                Line Items
              </div>
              <div id="summary-line-items" style="display: flex; flex-direction: column; gap: 8px; font-size: 0.8125rem; font-family: var(--font-mono); color: var(--ivory);">
                <div style="display: flex; justify-content: space-between;">
                  <span>Base Engine</span>
                  <span>₦199,000</span>
                </div>
              </div>
            </div>

            <div style="background: var(--bg-ground); padding: 12px; border-radius: var(--radius-md); font-size: 0.75rem; color: var(--slate-light); margin-bottom: 20px;">
              🔒 <strong>Paystack Protected:</strong> Transactions are cryptographically verified via HMAC SHA512 webhooks with zero auto-renew surcharges.
            </div>

            <button id="dispatch-checkout-btn" class="nera-btn nera-btn-primary nera-btn-lg" style="width: 100%; text-align: center;">
              Proceed to Paystack Checkout
            </button>
            <div id="checkout-error-msg" style="color: var(--signal-error); font-size: 0.8125rem; margin-top: 8px; display: none;"></div>
          </div>
        </div>
      </div>
    `;
  }

  async onMounted() {
    this.restorePendingBuild();
    await this.checkAuthStatus();
    this.setupListeners();
    this.refreshQuote();

    document.querySelectorAll('[data-link]').forEach(anchor => {
      anchor.addEventListener('click', (e) => {
        e.preventDefault();
        const targetPath = anchor.getAttribute('data-link');
        this.router.navigate(targetPath);
      });
    });
  }

  async checkAuthStatus() {
    const authBanner = document.getElementById('auth-status-banner');
    const emailInput = document.getElementById('builder-email');
    const orgInput = document.getElementById('builder-org-name');
    const token = localStorage.getItem('nera_auth_token');

    if (token) {
      try {
        const user = await api.getMe();
        if (user) {
          store.setUser(user);
          if (emailInput && !emailInput.value) emailInput.value = user.email || '';
          if (orgInput && !orgInput.value) orgInput.value = user.organization_name || user.company_name || '';
          if (authBanner) {
            authBanner.innerHTML = `
              <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid var(--emerald); padding: 10px 14px; border-radius: var(--radius-sm); font-size: 0.8125rem; color: var(--emerald-light); display: flex; align-items: center; justify-content: space-between;">
                <span>✓ Authenticated workspace: <strong>${user.email}</strong> (${user.organization_name || 'Standard'})</span>
                <span class="nera-badge nera-badge-emerald" style="font-size: 0.6875rem;">Active Session</span>
              </div>
            `;
          }
          return;
        }
      } catch (err) {
        console.warn('Failed to resolve authenticated user:', err);
      }
    }

    if (authBanner) {
      authBanner.innerHTML = `
        <div style="background: rgba(59, 130, 246, 0.08); border: 1px solid var(--border-subtle); padding: 10px 14px; border-radius: var(--radius-sm); font-size: 0.8125rem; color: var(--slate-light);">
          🔒 Public Storefront Configurator. <a href="/login?return_to=/build" data-link="/login?return_to=/build" style="color: var(--emerald-light); font-weight: 600;">Sign in</a> or <a href="/signup?return_to=/build" data-link="/signup?return_to=/build" style="color: var(--emerald-light); font-weight: 600;">create an account</a> to secure this configuration and complete your order.
        </div>
      `;
    }
  }

  restorePendingBuild() {
    try {
      const saved = sessionStorage.getItem('nera_pending_build');
      if (!saved) return;
      const data = JSON.parse(saved);

      if (data.product_code) {
        this.selectedProduct = data.product_code;
        document.querySelectorAll('input[name="product_code"]').forEach(r => {
          r.checked = (r.value === data.product_code);
          const card = r.closest('.agent-role-card');
          if (card) {
            if (r.checked) card.classList.add('nera-card-highlight');
            else card.classList.remove('nera-card-highlight');
          }
        });
      }

      if (Array.isArray(data.channels)) {
        document.querySelectorAll('input[name="channels"]').forEach(c => {
          if (c.value !== 'web') c.checked = data.channels.includes(c.value);
        });
      }

      if (Array.isArray(data.integrations)) {
        document.querySelectorAll('input[name="integrations"]').forEach(i => {
          i.checked = data.integrations.includes(i.value);
        });
      }

      if (Array.isArray(data.languages)) {
        document.querySelectorAll('input[name="languages"]').forEach(l => {
          if (l.value !== 'en') l.checked = data.languages.includes(l.value);
        });
      }

      if (data.monthly_conversations) {
        const slider = document.getElementById('volume-slider');
        const volDisplay = document.getElementById('volume-val');
        if (slider) slider.value = data.monthly_conversations;
        if (volDisplay) volDisplay.textContent = parseInt(data.monthly_conversations, 10).toLocaleString();
      }

      const emailInput = document.getElementById('builder-email');
      const orgInput = document.getElementById('builder-org-name');
      if (emailInput && data.email) emailInput.value = data.email;
      if (orgInput && data.orgName) orgInput.value = data.orgName;
    } catch (e) {
      console.warn('Failed restoring pending build:', e);
    }
  }

  setupListeners() {
    // Product radio buttons
    document.querySelectorAll('input[name="product_code"]').forEach(radio => {
      radio.addEventListener('change', (e) => {
        this.selectedProduct = e.target.value;
        document.querySelectorAll('.agent-role-card').forEach(c => c.classList.remove('nera-card-highlight'));
        e.target.closest('.agent-role-card').classList.add('nera-card-highlight');
        this.refreshQuote();
      });
    });

    // Channel, Integration & Language checkboxes
    document.querySelectorAll('input[name="channels"], input[name="integrations"], input[name="languages"]').forEach(box => {
      box.addEventListener('change', () => this.refreshQuote());
    });

    // Volume slider
    const slider = document.getElementById('volume-slider');
    const volDisplay = document.getElementById('volume-val');
    if (slider && volDisplay) {
      slider.addEventListener('input', (e) => {
        volDisplay.textContent = parseInt(e.target.value, 10).toLocaleString();
        this.refreshQuote();
      });
    }

    // Checkout button
    const checkoutBtn = document.getElementById('dispatch-checkout-btn');
    if (checkoutBtn) {
      checkoutBtn.addEventListener('click', () => this.handleCheckout());
    }
  }

  gatherFormData() {
    const channels = ['web'];
    document.querySelectorAll('input[name="channels"]:checked').forEach(c => {
      if (!channels.includes(c.value)) channels.push(c.value);
    });

    const integrations = [];
    document.querySelectorAll('input[name="integrations"]:checked').forEach(i => {
      integrations.push(i.value);
    });

    const languages = ['en'];
    document.querySelectorAll('input[name="languages"]:checked').forEach(l => {
      if (!languages.includes(l.value)) languages.push(l.value);
    });

    const slider = document.getElementById('volume-slider');
    const monthly_conversations = slider ? parseInt(slider.value, 10) : 1000;

    return {
      product_code: this.selectedProduct,
      channels,
      integrations,
      languages,
      monthly_conversations
    };
  }

  async refreshQuote() {
    const data = this.gatherFormData();
    try {
      const quote = await api.getQuote(data);
      this.currentQuote = quote;

      const totalEl = document.getElementById('summary-total-price');
      const itemsEl = document.getElementById('summary-line-items');
      const formattedTotal = quote.display_total || quote.display_amount;

      if (totalEl && formattedTotal) {
        totalEl.textContent = formattedTotal;
      }

      if (itemsEl && quote.line_items) {
        itemsEl.innerHTML = quote.line_items.map(item => `
          <div style="display: flex; justify-content: space-between;">
            <span>${item.label || item.description || item.name || 'Component'}</span>
            <span>${item.display_amount || '₦' + ((item.amount_minor || 0) / 100).toLocaleString()}</span>
          </div>
        `).join('');
      }
    } catch (err) {
      console.warn('Failed to calculate quote:', err);
    }
  }

  async handleCheckout() {
    if (this.isSubmitting) return;

    const emailInput = document.getElementById('builder-email');
    const orgInput = document.getElementById('builder-org-name');
    const errBox = document.getElementById('checkout-error-msg');
    const checkoutBtn = document.getElementById('dispatch-checkout-btn');

    if (errBox) errBox.style.display = 'none';

    const email = emailInput ? emailInput.value.trim() : '';
    const orgName = orgInput ? orgInput.value.trim() : '';

    if (!email || !email.includes('@')) {
      if (errBox) {
        errBox.textContent = 'Please enter a valid business email address.';
        errBox.style.display = 'block';
      }
      return;
    }

    if (!orgName) {
      if (errBox) {
        errBox.textContent = 'Please enter your organization or business name.';
        errBox.style.display = 'block';
      }
      return;
    }

    // Authenticated boundary enforcement
    const token = localStorage.getItem('nera_auth_token');
    const isAuthenticated = Boolean(token || store.getState().isAuthenticated);

    const formData = this.gatherFormData();
    sessionStorage.setItem('nera_pending_build', JSON.stringify({
      ...formData,
      email,
      orgName
    }));

    if (!isAuthenticated) {
      store.showToast('Please sign in or create an account to proceed with your order.', 'info');
      this.router.navigate('/login?return_to=/build');
      return;
    }

    this.isSubmitting = true;
    checkoutBtn.disabled = true;
    checkoutBtn.innerHTML = `
      <span class="anim-spin" style="display:inline-block; margin-right: 8px;">🔄</span>
      <span>Connecting to Paystack Secure Checkout...</span>
    `;

    try {
      // Dispatch direct authoritative order & checkout session creation
      const checkoutRes = await api.createCheckoutSession({
        customer_email: email,
        organization_name: orgName,
        product_type: formData.product_code,
        channels: formData.channels,
        integrations: formData.integrations,
        languages: formData.languages,
        monthly_conversations: formData.monthly_conversations,
        callback_url: `${window.location.origin}/v2/checkout/return`
      });

      // Clear pending build upon successful checkout dispatch
      sessionStorage.removeItem('nera_pending_build');

      if (checkoutRes && (checkoutRes.authorization_url || checkoutRes.checkout_url)) {
        const dest = checkoutRes.authorization_url || checkoutRes.checkout_url;
        window.location.href = dest;
      } else {
        throw new Error(checkoutRes.detail || 'Paystack checkout URL not returned');
      }
    } catch (err) {
      console.error('Checkout error:', err);
      if (errBox) {
        errBox.textContent = err.message || 'Payment link generation failed. Please try again.';
        errBox.style.display = 'block';
      }
      checkoutBtn.disabled = false;
      checkoutBtn.innerHTML = '<span>Proceed to Paystack Checkout</span>';
      this.isSubmitting = false;
    }
  }
}
