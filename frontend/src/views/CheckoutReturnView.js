/**
 * Nera 2.0 Greenfield — Checkout Return View
 * Post-Paystack redirect state machine: handles success, pending, cancellation, and error states.
 */
import { api } from '../core/api.js';

export class CheckoutReturnView {
  constructor({ router, query }) {
    this.router = router;
    this.query = query;
    this.reference = query.get('reference') || query.get('trxref') || '';
    this.isCancelled = query.get('cancelled') === 'true' || query.get('status') === 'cancelled';
    this.pollInterval = null;
    this.pollCount = 0;
  }

  async render() {
    return `
      <div class="anim-fade-in-up" style="max-width: 640px; margin: 40px auto;">
        <!-- Card Shell -->
        <div class="nera-card" id="return-state-container" style="padding: 40px; text-align: center;">
          <!-- Checking / Pending State (Default) -->
          <div id="status-checking">
            <div style="font-size: 2.5rem; margin-bottom: 16px;" class="anim-status-blink">🔄</div>
            <h1 style="font-size: 1.5rem; font-weight: 700; margin-bottom: 8px;">Verifying Settlement Status</h1>
            <p style="color: var(--slate-light); font-size: 0.9375rem;">
              Communicating with Paystack and checking idempotent transaction ledger...
            </p>
            <div class="nera-mono" style="margin-top: 16px; font-size: 0.8125rem; color: var(--electric-blue-light);" id="ret-ref-display">
              ${this.reference ? `Ref: ${this.reference}` : 'No reference provided in URL'}
            </div>
            <div style="margin-top: 12px; font-size: 0.75rem; color: var(--slate);" id="ret-poll-count">
              Checking status (attempt 1/30)...
            </div>
          </div>

          <!-- Dynamic Result Container -->
          <div id="status-result" style="display: none; text-align: left; margin-top: 24px;"></div>
        </div>
      </div>
    `;
  }

  async onMounted() {
    if (this.isCancelled) {
      this.showCancellation();
      return;
    }

    if (!this.reference) {
      this.showError('No payment reference found in URL query parameters.');
      return;
    }

    this.startPolling();
  }

  cleanup() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
  }

  startPolling() {
    this.checkStatus();
    this.pollInterval = setInterval(() => {
      this.pollCount++;
      const pollDisplay = document.getElementById('ret-poll-count');
      if (pollDisplay) {
        pollDisplay.textContent = `Checking status (attempt ${this.pollCount + 1}/30)...`;
      }

      if (this.pollCount >= 30) {
        this.cleanup();
        this.showError('Verification timeout. If your card was debited, your automation engine will provision automatically once Paystack confirms the webhook.');
      } else {
        this.checkStatus();
      }
    }, 2000);
  }

  async checkStatus() {
    try {
      const res = await api.checkPaymentStatus(this.reference);
      const rawStatus = (res && res.order && res.order.status) || (res && res.status) || '';
      const status = rawStatus.toLowerCase();

      if (status === 'success' || status === 'paid' || status === 'completed') {
        this.cleanup();
        this.showSuccess(res);
      } else if (status === 'cancelled' || status === 'abandoned') {
        this.cleanup();
        this.showCancellation();
      } else if (status === 'failed') {
        this.cleanup();
        this.showError('Paystack declined the payment transaction. Please try another card or payment method.');
      }
    } catch (err) {
      console.warn('Poll check warning:', err);
    }
  }

  showSuccess(data) {
    const checking = document.getElementById('status-checking');
    const result = document.getElementById('status-result');
    if (checking) checking.style.display = 'none';
    if (!result) return;

    result.style.display = 'block';
    result.innerHTML = `
      <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid var(--emerald); border-radius: var(--radius-xl); padding: 28px; text-align: center;">
        <div style="font-size: 2.5rem; margin-bottom: 12px;">✅</div>
        <h2 style="font-size: 1.5rem; font-weight: 800; color: var(--emerald-light); margin-bottom: 8px;">
          Settlement Confirmed &amp; Provisioned!
        </h2>
        <p style="color: var(--ivory); font-size: 0.9375rem; margin-bottom: 20px;">
          Your business automation engine has been provisioned idempotently.
        </p>

        <div style="background: var(--bg-ground); padding: 16px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle); text-align: left; font-family: var(--font-mono); font-size: 0.8125rem; margin-bottom: 24px;">
          <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
            <span style="color: var(--slate);">Reference:</span>
            <span style="color: var(--ivory);">${this.reference}</span>
          </div>
          <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
            <span style="color: var(--slate);">Status:</span>
            <span style="color: var(--emerald-light); font-weight: 700;">PROVISIONED &amp; ACTIVE</span>
          </div>
          <div style="display: flex; justify-content: space-between;">
            <span style="color: var(--slate);">Shared Memory:</span>
            <span style="color: var(--electric-blue-light);">SYNCHRONIZED</span>
          </div>
        </div>

        <a href="/dashboard" class="nera-btn nera-btn-primary nera-btn-lg" style="display: inline-block; width: 100%; text-align: center;" data-link="/dashboard">
          Go to Automation Workspace →
        </a>
      </div>
    `;

    result.querySelectorAll('[data-link]').forEach(anchor => {
      anchor.addEventListener('click', (e) => {
        e.preventDefault();
        const targetPath = anchor.getAttribute('data-link');
        this.router.navigate(targetPath);
      });
    });
  }

  showCancellation() {
    const checking = document.getElementById('status-checking');
    const result = document.getElementById('status-result');
    if (checking) checking.style.display = 'none';
    if (!result) return;

    result.style.display = 'block';
    result.innerHTML = `
      <div style="background: rgba(148, 163, 184, 0.1); border: 1px solid var(--border-subtle); border-radius: var(--radius-xl); padding: 28px; text-align: center;">
        <div style="font-size: 2.5rem; margin-bottom: 12px;">⏹️</div>
        <h2 style="font-size: 1.35rem; font-weight: 800; color: var(--ivory); margin-bottom: 8px;">
          Checkout Session Cancelled
        </h2>
        <p style="color: var(--slate-light); font-size: 0.9375rem; margin-bottom: 24px;">
          You cancelled your Paystack checkout session. No charges were made to your account.
        </p>

        <div style="display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;">
          <a href="/build" class="nera-btn nera-btn-primary" data-link="/build">Resume Configuration</a>
          <a href="/pricing" class="nera-btn nera-btn-secondary" data-link="/pricing">Review Pricing</a>
        </div>
      </div>
    `;

    result.querySelectorAll('[data-link]').forEach(anchor => {
      anchor.addEventListener('click', (e) => {
        e.preventDefault();
        const targetPath = anchor.getAttribute('data-link');
        this.router.navigate(targetPath);
      });
    });
  }

  showError(msg) {
    const checking = document.getElementById('status-checking');
    const result = document.getElementById('status-result');
    if (checking) checking.style.display = 'none';
    if (!result) return;

    result.style.display = 'block';
    result.innerHTML = `
      <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid var(--signal-error); border-radius: var(--radius-xl); padding: 28px; text-align: center;">
        <div style="font-size: 2.5rem; margin-bottom: 12px;">⚠️</div>
        <h2 style="font-size: 1.35rem; font-weight: 800; color: var(--signal-error); margin-bottom: 8px;">
          Settlement Verification Notice
        </h2>
        <p style="color: var(--slate-light); font-size: 0.9375rem; margin-bottom: 24px;">
          ${msg}
        </p>

        <div style="display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;">
          <a href="/build" class="nera-btn nera-btn-secondary" data-link="/build">Reconfigure Plan</a>
          <a href="/demo" class="nera-btn nera-btn-primary" data-link="/demo">Try Simulation</a>
        </div>
      </div>
    `;

    result.querySelectorAll('[data-link]').forEach(anchor => {
      anchor.addEventListener('click', (e) => {
        e.preventDefault();
        const targetPath = anchor.getAttribute('data-link');
        this.router.navigate(targetPath);
      });
    });
  }
}
