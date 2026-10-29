/**
 * Nera 2.0 Greenfield — Pricing View
 * Deterministic, transparent automation pricing connected directly to /api/v1/pricing/quote.
 */
import { api } from '../core/api.js';
import { store } from '../core/store.js';

export class PricingView {
  constructor({ router }) {
    this.router = router;
    this.selectedProduct = 'sales_agent';
    this.selectedChannels = ['web', 'telegram'];
    this.selectedIntegrations = ['crm'];
    this.selectedLanguages = ['en'];
    this.activeQuote = null;
    this.options = null;
  }

  async render() {
    return `
      <div class="anim-fade-in-up">
        <!-- Header -->
        <section style="text-align: center; margin-bottom: 56px;">
          <div class="nera-badge nera-badge-blue" style="margin-bottom: 12px;">Quotes grounded in requirements</div>
          <h1 style="font-size: 2.75rem; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 16px;">
            A clear, <span class="gradient-text">itemised quote</span>
          </h1>
          <p style="color: var(--slate-light); font-size: 1.125rem; max-width: 680px; margin: 0 auto; line-height: 1.6;">
            Select one of the two products and its requirements to see a quote from Nera's pricing engine. No static package prices on this page.
          </p>
        </section>

        <section class="nera-card" style="margin-bottom: 48px; text-align:center;">
          <h2 style="font-size:1.5rem; margin-bottom:10px;">Pricing follows the build</h2>
          <p style="color:var(--slate-light); max-width:650px; margin:0 auto;">Nera currently quotes two products: an AI Sales Representative and an AI Support Agent. Choose a product and set its requirements below to see an itemised quote calculated by the pricing engine.</p>
        </section>

        <!-- Interactive Line-Item Pricing Simulator -->
        <section class="nera-card" style="padding: 40px; margin-bottom: 64px;">
          <div style="text-align: center; margin-bottom: 32px;">
            <div class="nera-badge nera-badge-blue" style="margin-bottom: 8px;">Live quote calculator</div>
            <h2 style="font-size: 1.75rem; font-weight: 800;">Itemised quote</h2>
            <p style="color: var(--slate-light); font-size: 0.9375rem;">
              Calculated from the product and requirements selected above.
            </p>
          </div>

          <div style="display: grid; grid-template-columns: 1.2fr 1fr; gap: 36px; align-items: start;">
            <!-- Form Controls -->
            <div>
              <div class="nera-form-group">
                <label class="nera-label">Automation Engine</label>
                <select id="calc-product" class="nera-input">
                  <option value="sales_agent">AI Sales Representative</option>
                  <option value="support_agent">AI Support Agent</option>

                </select>
              </div>

              <div class="nera-form-group">
                <label class="nera-label">Active Communication Channels</label>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 8px;">
                  <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem;">
                    <input type="checkbox" id="calc-chan-web" checked disabled /> Web Chat (Included)
                  </label>
                  <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                    <input type="checkbox" id="calc-chan-tg" checked /> Telegram Bot (+₦4,000/mo)
                  </label>
                  <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                    <input type="checkbox" id="calc-chan-wa" /> WhatsApp Bot (+₦8,000/mo)
                  </label>
                  <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                    <input type="checkbox" id="calc-chan-email" /> Email (+₦3,000/mo)
                  </label>
                </div>
              </div>

              <div class="nera-form-group">
                <label class="nera-label">Integrations (+₦2,000/mo each)</label>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 8px;">
                  <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                    <input type="checkbox" id="calc-int-crm" checked /> CRM Webhook (+₦2k)
                  </label>
                  <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                    <input type="checkbox" id="calc-int-accounting" /> Accounting (+₦2k)
                  </label>
                  <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                    <input type="checkbox" id="calc-int-calendar" /> Calendar (+₦2k)
                  </label>
                  <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                    <input type="checkbox" id="calc-int-payment" /> Payment (+₦2k)
                  </label>
                </div>
              </div>

              <div class="nera-form-group">
                <label class="nera-label">Languages (+₦3,500/mo per extra)</label>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 8px;">
                  <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem;">
                    <input type="checkbox" id="calc-lang-en" checked disabled /> English (Included)
                  </label>
                  <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                    <input type="checkbox" id="calc-lang-pid" /> Pidgin (+₦3.5k)
                  </label>
                  <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                    <input type="checkbox" id="calc-lang-yo" /> Yoruba (+₦3.5k)
                  </label>
                  <label style="display: flex; align-items: center; gap: 8px; font-size: 0.875rem; cursor: pointer;">
                    <input type="checkbox" id="calc-lang-ha" /> Hausa (+₦3.5k)
                  </label>
                </div>
              </div>

              <div class="nera-form-group">
                <div style="display: flex; justify-content: space-between; align-items: baseline;">
                  <label class="nera-label">Monthly Conversations</label>
                  <span style="font-size: 0.75rem; color: var(--slate-light);">₦5/conversation total</span>
                </div>
                <input type="range" id="calc-volume-slider" min="500" max="10000" step="500" value="1000" style="width: 100%; margin: 6px 0;" />
                <div style="font-family: var(--font-mono); font-size: 0.8125rem; color: var(--emerald-light);">
                  Volume: <strong id="calc-vol-disp">1,000</strong> conversations
                </div>
              </div>
            </div>

            <!-- Dynamic Quote Output -->
            <div style="background: var(--bg-ground); padding: 24px; border-radius: var(--radius-xl); border: 1px solid var(--border-subtle);" id="calc-quote-box">
              <div style="font-size: 0.8125rem; font-weight: 700; color: var(--emerald-light); margin-bottom: 8px;">CALCULATED QUOTE</div>
              <div style="display: flex; align-items: baseline; gap: 8px; margin-bottom: 16px;">
                <span class="nera-price-tag" id="calc-total-val" style="color: var(--emerald-light);">Set requirements to calculate</span>
                <span class="nera-price-period">/ month</span>
              </div>

              <div style="border-top: 1px solid var(--border-subtle); padding-top: 16px; margin-bottom: 20px;">
                <div style="font-size: 0.75rem; font-weight: 700; color: var(--slate); text-transform: uppercase; margin-bottom: 8px;">Itemized Breakdown:</div>
                <div id="calc-breakdown-list" style="display: flex; flex-direction: column; gap: 6px; font-size: 0.8125rem; font-family: var(--font-mono); color: var(--ivory-dim);">
                  <div style="display: flex; justify-content: space-between;"><span>Base Engine:</span> <span>₦199,000</span></div>
                  <div style="display: flex; justify-content: space-between;"><span>Volume (1,000 conversations):</span> <span>₦5,000</span></div>
                  <div style="display: flex; justify-content: space-between;"><span>Telegram Channel:</span> <span>₦4,000</span></div>
                  <div style="display: flex; justify-content: space-between;"><span>CRM Webhook:</span> <span>₦2,000</span></div>
                </div>
              </div>

              <a href="/build" class="nera-btn nera-btn-primary" style="width: 100%; text-align: center;" data-link="/build">
                Deploy with These Specifications
              </a>
            </div>
          </div>
        </section>
      </div>
    `;
  }

  onMounted() {
    this.setupListeners();

    document.querySelectorAll('[data-link]').forEach(anchor => {
      anchor.addEventListener('click', (e) => {
        e.preventDefault();
        const targetPath = anchor.getAttribute('data-link');
        this.router.navigate(targetPath);
      });
    });
  }

  setupListeners() {
    const productSelect = document.getElementById('calc-product');
    const tgCheck = document.getElementById('calc-chan-tg');
    const waCheck = document.getElementById('calc-chan-wa');
    const emailCheck = document.getElementById('calc-chan-email');
    const crmCheck = document.getElementById('calc-int-crm');
    const accCheck = document.getElementById('calc-int-accounting');
    const calCheck = document.getElementById('calc-int-calendar');
    const payCheck = document.getElementById('calc-int-payment');
    const pidCheck = document.getElementById('calc-lang-pid');
    const yoCheck = document.getElementById('calc-lang-yo');
    const haCheck = document.getElementById('calc-lang-ha');
    const volSlider = document.getElementById('calc-volume-slider');
    const volDisp = document.getElementById('calc-vol-disp');

    const updateCalc = async () => {
      const prod = productSelect ? productSelect.value : 'sales_agent';
      const channels = ['web'];
      if (tgCheck && tgCheck.checked) channels.push('telegram');
      if (waCheck && waCheck.checked) channels.push('whatsapp');
      if (emailCheck && emailCheck.checked) channels.push('email');

      const integrations = [];
      if (crmCheck && crmCheck.checked) integrations.push('crm');
      if (accCheck && accCheck.checked) integrations.push('accounting');
      if (calCheck && calCheck.checked) integrations.push('calendar');
      if (payCheck && payCheck.checked) integrations.push('payment');

      const languages = ['en'];
      if (pidCheck && pidCheck.checked) languages.push('pid');
      if (yoCheck && yoCheck.checked) languages.push('yo');
      if (haCheck && haCheck.checked) languages.push('ha');

      const monthly_conversations = volSlider ? parseInt(volSlider.value, 10) : 1000;
      if (volDisp) volDisp.textContent = monthly_conversations.toLocaleString();

      try {
        const quote = await api.getQuote({
          product_code: prod,
          channels,
          integrations,
          languages,
          monthly_conversations
        });

        const totalEl = document.getElementById('calc-total-val');
        const listEl = document.getElementById('calc-breakdown-list');
        const formattedTotal = quote.display_total || quote.display_amount;
        if (totalEl && formattedTotal) {
          totalEl.textContent = formattedTotal;
        }

        if (listEl && quote.line_items) {
          listEl.innerHTML = quote.line_items.map(item => `
            <div style="display: flex; justify-content: space-between;">
              <span>${item.label || item.description || item.name || 'Component'}:</span>
              <span>${item.display_amount || '₦' + ((item.amount_minor || 0) / 100).toLocaleString()}</span>
            </div>
          `).join('');
        }
      } catch (e) {
        console.warn('Calculation error:', e);
      }
    };

    [productSelect, tgCheck, waCheck, emailCheck, crmCheck, accCheck, calCheck, payCheck, pidCheck, yoCheck, haCheck].forEach(el => {
      if (el) el.addEventListener('change', updateCalc);
    });

    if (volSlider) {
      volSlider.addEventListener('input', updateCalc);
    }

    // Initial calculation on mount
    updateCalc();
  }
}
