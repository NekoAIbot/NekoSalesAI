/**
 * Nera 2.0 Greenfield — Auth View (Login & Registration)
 * Connects directly to /api/v1/auth/login and /api/v1/auth/register.
 */
import { api } from '../core/api.js';
import { store } from '../core/store.js';

export class AuthView {
  constructor({ router, query }) {
    this.router = router;
    this.query = query;
    this.mode = (window.location.pathname.includes('signup') || query.get('mode') === 'signup') ? 'signup' : 'login';
    this.isSubmitting = false;
  }

  async render() {
    const isSignup = this.mode === 'signup';
    return `
      <div class="anim-fade-in-up" style="max-width: 440px; margin: 40px auto;">
        <div class="nera-card" id="auth-card" style="padding: 36px;">
          <!-- Header -->
          <div style="text-align: center; margin-bottom: 28px;">
            <div class="nera-badge nera-badge-emerald" style="margin-bottom: 12px;">Automation Workspace</div>
            <h1 style="font-size: 1.75rem; font-weight: 800; letter-spacing: -0.02em;">
              ${isSignup ? 'Automate Your Business' : 'Welcome to Nera'}
            </h1>
            <p style="color: var(--slate-light); font-size: 0.875rem; margin-top: 6px; line-height: 1.5;">
              ${isSignup ? 'Create an account to manage your business automation engines.' : 'Access your active workflows, provisioned engines, and API credentials.'}
            </p>
          </div>

          <!-- Auth Form -->
          <form id="auth-form">
            ${isSignup ? `
              <div class="nera-form-group">
                <label class="nera-label">Full Name</label>
                <input type="text" id="auth-name" class="nera-input" placeholder="e.g. Chinelo Okonkwo" required />
              </div>

              <div class="nera-form-group">
                <label class="nera-label">Organization / Business Name</label>
                <input type="text" id="auth-org" class="nera-input" placeholder="e.g. SwiftPay Africa" required />
              </div>
            ` : ''}

            <div class="nera-form-group">
              <label class="nera-label">Email Address</label>
              <input type="email" id="auth-email" class="nera-input" placeholder="name@company.com" required />
            </div>

            <div class="nera-form-group pw-wrap">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <label class="nera-label" for="auth-password">Password</label>
              </div>
              <input type="password" id="auth-password" class="nera-input" placeholder="••••••••••••" autocomplete="current-password" required />
              <button type="button" class="pw-toggle" data-pw-target="auth-password" aria-label="Show password">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              </button>
            </div>

            <button type="submit" id="auth-submit-btn" class="nera-btn nera-btn-primary" style="width: 100%; margin-top: 12px;">
              ${isSignup ? 'Create Automation Account' : 'Sign In to Workspace'}
            </button>

            <div id="auth-error-msg" style="color: var(--signal-error); font-size: 0.8125rem; margin-top: 12px; display: none; text-align: center;"></div>
          </form>

          <!-- Mode Toggle -->
          <div style="text-align: center; margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--border-subtle); font-size: 0.875rem; color: var(--slate-light);">
            ${isSignup ? `
              Already have an account? <a href="/login" style="color: var(--emerald-light); font-weight: 600;" data-link="/login">Sign in</a>
            ` : `
              New to Nera? <a href="/signup" style="color: var(--emerald-light); font-weight: 600;" data-link="/signup">Create account</a>
            `}
          </div>
        </div>
      </div>
    `;
  }

  onMounted() {
    const form = document.getElementById('auth-form');
    const errBox = document.getElementById('auth-error-msg');
    const submitBtn = document.getElementById('auth-submit-btn');

    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (this.isSubmitting) return;

        errBox.style.display = 'none';
        const email = document.getElementById('auth-email').value.trim();
        const password = document.getElementById('auth-password').value;

        this.isSubmitting = true;
        submitBtn.disabled = true;
        submitBtn.textContent = 'Authenticating...';

        try {
          if (this.mode === 'signup') {
            const name = document.getElementById('auth-name').value.trim();
            const org = document.getElementById('auth-org').value.trim();
            await api.register({ email, password, full_name: name, organization_name: org });
            const loginRes = await api.login(email, password);
            const token = loginRes.token || loginRes.access_token;
            if (token) {
              localStorage.setItem('nera_auth_token', token);
              api.setToken(token);
              const user = await api.getMe();
              store.setUser(user);
            }
            store.showToast('Account created and signed in!', 'success');
          } else {
            const loginRes = await api.login(email, password);
            if (loginRes.token || loginRes.access_token) {
              const token = loginRes.token || loginRes.access_token;
              localStorage.setItem('nera_auth_token', token);
              api.setToken(token);
              const user = await api.getMe();
              store.setUser(user);
            }
            store.showToast('Signed in successfully', 'success');
          }
          // unique sign-in moment: card departs, welcome mark, then enter the app
          const card = document.getElementById('auth-card');
          if (card) {
            card.classList.add('auth-success-card');
            const overlay = document.createElement('div');
            overlay.className = 'auth-welcome-overlay';
            overlay.innerHTML = '<div class="welcome-mark" style="color:#34d399;">Welcome to Nera</div>';
            document.body.appendChild(overlay);
            await new Promise(r => setTimeout(r, 1000));
          }
          const returnTo = this.query.get('return_to') || this.query.get('next');
          if (returnTo) {
            const safeReturnTo = returnTo.startsWith('/') && !returnTo.startsWith('//') ? returnTo : '/dashboard';
            this.router.navigate(safeReturnTo);
          } else {
            this.router.navigate('/dashboard');
          }
        } catch (err) {
          console.error('Auth error:', err);
          errBox.textContent = err.message || 'Authentication failed. Please verify credentials.';
          errBox.style.display = 'block';
        } finally {
          this.isSubmitting = false;
          submitBtn.disabled = false;
          submitBtn.textContent = this.mode === 'signup' ? 'Create Automation Account' : 'Sign In to Workspace';
        }
      });
    }

    document.querySelectorAll('.pw-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        const input = document.getElementById(btn.getAttribute('data-pw-target'));
        if (!input) return;
        const show = input.type === 'password';
        input.type = show ? 'text' : 'password';
        btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
        btn.style.color = show ? '#34d399' : '';
      });
    });

    document.querySelectorAll('[data-link]').forEach(anchor => {
      anchor.addEventListener('click', (e) => {
        e.preventDefault();
        const targetPath = anchor.getAttribute('data-link');
        this.router.navigate(targetPath);
      });
    });
  }
}
