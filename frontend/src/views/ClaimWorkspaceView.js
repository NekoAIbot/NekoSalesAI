/**
 * Nera 2.0 Greenfield — Workspace Setup Claim View
 * Handles single-use token redemption, email verification, and initial password creation.
 */
import { api } from '../core/api.js';
import { store } from '../core/store.js';

export class ClaimWorkspaceView {
  constructor({ router, query }) {
    this.router = router;
    this.query = query;
    this.token = (query.get('token') || query.get('claim_token') || '').trim();
    this.email = (query.get('email') || '').trim();
    this.isSubmitting = false;
    this.setupResult = null;
  }

  async render() {
    if (!this.token) {
      return `
        <div class="anim-fade-in-up" style="max-width: 520px; margin: 60px auto;">
          <div class="nera-card" style="padding: 40px; text-align: center;">
            <div style="font-size: 2.5rem; margin-bottom: 16px;">⚠️</div>
            <h1 style="font-size: 1.5rem; font-weight: 700; margin-bottom: 8px;">Missing Setup Token</h1>
            <p style="color: var(--slate-light); font-size: 0.9375rem; line-height: 1.5; margin-bottom: 24px;">
              This setup link does not contain a valid authorization token. Please click the full link directly from your setup email.
            </p>
            <a href="/login" class="nera-btn nera-btn-primary" data-link="/login">Return to Sign In</a>
          </div>
        </div>
      `;
    }

    return `
      <div class="anim-fade-in-up" style="max-width: 480px; margin: 40px auto;">
        <div class="nera-card" id="claim-card" style="padding: 36px;">
          <!-- Header -->
          <div style="text-align: center; margin-bottom: 24px;">
            <div class="nera-badge nera-badge-emerald" style="margin-bottom: 12px;">Workspace Onboarding</div>
            <h1 style="font-size: 1.625rem; font-weight: 800; letter-spacing: -0.02em;">
              Complete Your Setup
            </h1>
            <p style="color: var(--slate-light); font-size: 0.875rem; margin-top: 6px; line-height: 1.5;">
              Set your administrator password to activate your automation engine and access your workspace.
            </p>
          </div>

          <!-- Dynamic Result Box (Success State) -->
          <div id="claim-success-box" style="display: none;"></div>

          <!-- Setup Form -->
          <form id="claim-form">
            <div class="nera-form-group">
              <label class="nera-label" for="claim-email">Email Address</label>
              <input
                type="email"
                id="claim-email"
                class="nera-input"
                placeholder="name@company.com"
                value="${this.email}"
                ${this.email ? 'readonly' : 'required'}
                required
              />
              <span style="font-size: 0.75rem; color: var(--slate); margin-top: 4px; display: block;">
                Must match the buyer email used at checkout.
              </span>
            </div>

            <div class="nera-form-group pw-wrap">
              <label class="nera-label" for="claim-password">New Password</label>
              <input
                type="password"
                id="claim-password"
                class="nera-input"
                placeholder="••••••••••••"
                autocomplete="new-password"
                required
              />
              <button type="button" class="pw-toggle" data-pw-target="claim-password" aria-label="Show password">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              </button>
            </div>

            <div class="nera-form-group pw-wrap">
              <label class="nera-label" for="claim-password-confirm">Confirm Password</label>
              <input
                type="password"
                id="claim-password-confirm"
                class="nera-input"
                placeholder="••••••••••••"
                autocomplete="new-password"
                required
              />
              <button type="button" class="pw-toggle" data-pw-target="claim-password-confirm" aria-label="Show password">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              </button>
            </div>

            <div style="font-size: 0.75rem; color: var(--slate); margin-bottom: 16px; line-height: 1.4;">
              Password must be at least 8 characters long and contain at least one uppercase letter, one lowercase letter, and one digit.
            </div>

            <button type="submit" id="claim-submit-btn" class="nera-btn nera-btn-primary" style="width: 100%;">
              Activate Workspace Credentials →
            </button>

            <div id="claim-error-msg" style="color: var(--signal-error); font-size: 0.8125rem; margin-top: 14px; display: none; text-align: center; line-height: 1.4;"></div>
          </form>
        </div>
      </div>
    `;
  }

  onMounted() {
    const form = document.getElementById('claim-form');
    const errBox = document.getElementById('claim-error-msg');
    const submitBtn = document.getElementById('claim-submit-btn');

    // Bind password show/hide toggles
    document.querySelectorAll('.pw-toggle').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const targetId = btn.getAttribute('data-pw-target');
        const input = document.getElementById(targetId);
        if (input) {
          const isPw = input.type === 'password';
          input.type = isPw ? 'text' : 'password';
          btn.setAttribute('aria-label', isPw ? 'Hide password' : 'Show password');
        }
      });
    });

    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (this.isSubmitting) return;

        errBox.style.display = 'none';
        const email = document.getElementById('claim-email').value.trim();
        const password = document.getElementById('claim-password').value;
        const confirm = document.getElementById('claim-password-confirm').value;

        // Client-side validations
        if (!email) {
          errBox.textContent = 'Please enter your email address.';
          errBox.style.display = 'block';
          return;
        }

        if (password.length < 8) {
          errBox.textContent = 'Password must be at least 8 characters long.';
          errBox.style.display = 'block';
          return;
        }

        if (!/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/[0-9]/.test(password)) {
          errBox.textContent = 'Password must contain uppercase, lowercase, and numeric characters.';
          errBox.style.display = 'block';
          return;
        }

        if (password !== confirm) {
          errBox.textContent = 'Passwords do not match. Please re-enter.';
          errBox.style.display = 'block';
          return;
        }

        this.isSubmitting = true;
        submitBtn.disabled = true;
        submitBtn.textContent = 'Activating Workspace...';

        try {
          const res = await api.completeSetup(this.token, email, password);
          this.showSuccess(res);
        } catch (err) {
          const msg = err.message || 'Failed to complete workspace setup. Please verify your link and try again.';
          errBox.textContent = msg;
          errBox.style.display = 'block';
          this.isSubmitting = false;
          submitBtn.disabled = false;
          submitBtn.textContent = 'Activate Workspace Credentials →';
        }
      });
    }
  }

  showSuccess(result) {
    const form = document.getElementById('claim-form');
    const successBox = document.getElementById('claim-success-box');
    if (form) form.style.display = 'none';
    if (!successBox) return;

    successBox.style.display = 'block';
    successBox.innerHTML = `
      <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid var(--emerald); border-radius: var(--radius-xl); padding: 24px; text-align: center;">
        <div style="font-size: 2.5rem; margin-bottom: 12px;">✅</div>
        <h2 style="font-size: 1.375rem; font-weight: 800; color: var(--emerald-light); margin-bottom: 8px;">
          Workspace Activated!
        </h2>
        <p style="color: var(--ivory); font-size: 0.875rem; margin-bottom: 18px; line-height: 1.5;">
          Your administrator credentials and verified account are ready. You can now access your automation workspace.
        </p>

        ${result && result.api_key ? `
          <div style="background: var(--bg-ground); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle); text-align: left; margin-bottom: 20px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <span style="font-size: 0.75rem; color: var(--slate); font-weight: 600;">WORKSPACE API KEY</span>
              <button type="button" id="copy-api-key-btn" style="background: none; border: none; color: var(--emerald-light); font-size: 0.75rem; cursor: pointer; font-weight: 600;">
                Copy Key
              </button>
            </div>
            <div class="nera-mono" style="font-size: 0.8125rem; color: var(--electric-blue-light); word-break: break-all;">
              ${result.api_key}
            </div>
            <div style="font-size: 0.6875rem; color: var(--slate); margin-top: 6px;">
              Store this key safely. It will not be shown again.
            </div>
          </div>
        ` : ''}

        <a href="/dashboard" id="goto-dashboard-btn" class="nera-btn nera-btn-primary" style="display: block; width: 100%; text-align: center;" data-link="/dashboard">
          Enter Automation Workspace →
        </a>
      </div>
    `;

    const copyBtn = document.getElementById('copy-api-key-btn');
    if (copyBtn && result && result.api_key) {
      copyBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(result.api_key).then(() => {
          copyBtn.textContent = 'Copied!';
          setTimeout(() => { copyBtn.textContent = 'Copy Key'; }, 2000);
        });
      });
    }

    const dashBtn = document.getElementById('goto-dashboard-btn');
    if (dashBtn) {
      dashBtn.addEventListener('click', (e) => {
        e.preventDefault();
        this.router.navigate('/dashboard');
      });
    }
  }
}
