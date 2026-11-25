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
    const path = window.location.pathname;
    if (path.includes('verify-email') || query.get('mode') === 'verify') {
      this.mode = 'verify';
    } else if (path.includes('signup') || query.get('mode') === 'signup') {
      this.mode = 'signup';
    } else {
      this.mode = 'login';
    }
    this.isSubmitting = false;
  }

  async render() {
    if (this.mode === 'verify') {
      const email = sessionStorage.getItem('nera_verification_email') || this.query.get('email') || '';
      return `
        <div class="anim-fade-in-up" style="max-width: 440px; margin: 40px auto;">
          <div class="nera-card" id="auth-card" style="padding: 36px;">
            <div style="text-align: center; margin-bottom: 28px;">
              <div class="nera-badge nera-badge-emerald" style="margin-bottom: 12px;">Email Verification</div>
              <h1 style="font-size: 1.75rem; font-weight: 800; letter-spacing: -0.02em;">Check your inbox</h1>
              <p style="color: var(--slate-light); font-size: 0.875rem; margin-top: 6px; line-height: 1.5;">
                Enter the 6-digit code sent to <strong id="verify-email-address">${email || 'your email'}</strong>.
              </p>
            </div>
            <form id="verify-email-form">
              <div class="nera-form-group">
                <label class="nera-label" for="verify-code">6-digit code</label>
                <input type="text" id="verify-code" name="code" class="nera-input" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" placeholder="000000" required />
              </div>
              <button type="submit" id="verify-submit-btn" class="nera-btn nera-btn-primary" style="width: 100%; margin-top: 12px;">
                Verify Email
              </button>
              <button type="button" id="resend-verification-btn" class="nera-btn" style="width: 100%; margin-top: 10px;">
                Resend Code
              </button>
              <div id="verify-error-msg" style="color: var(--signal-error); font-size: 0.8125rem; margin-top: 12px; display: none; text-align: center;"></div>
            </form>
            <div style="text-align: center; margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--border-subtle); font-size: 0.875rem; color: var(--slate-light);">
              <a href="/login" style="color: var(--emerald-light); font-weight: 600;" data-link="/login">Back to sign in</a>
            </div>
          </div>
        </div>
      `;
    }
    const isSignup = this.mode === 'signup';
    const prefillEmail = !isSignup ? (this.query.get('email') || '') : '';
    const isVerified = !isSignup && this.query.get('verified') === '1';
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
          ${isVerified ? `<div style="color: #34d399; font-size: 0.875rem; margin-bottom: 16px; text-align: center;">Email verified. Sign in to access your workspace.</div>` : ''}

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
              <input type="email" id="auth-email" class="nera-input" value="${prefillEmail.replace(/"/g, '&quot;')}" placeholder="name@company.com" required />
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
    if (this.mode === 'verify') {
      const verifyForm = document.getElementById('verify-email-form');
      const errBox = document.getElementById('verify-error-msg');
      const resendBtn = document.getElementById('resend-verification-btn');
      const submitBtn = document.getElementById('verify-submit-btn');
      const email = sessionStorage.getItem('nera_verification_email') || this.query.get('email') || '';
      const justSent = sessionStorage.getItem('nera_verification_just_sent') === '1';
      sessionStorage.removeItem('nera_verification_just_sent');

      const startCooldown = (seconds = 60) => {
        let left = Math.max(1, Number(seconds) || 60);
        if (!resendBtn) return;
        resendBtn.disabled = true;
        const tick = () => {
          resendBtn.textContent = `Resend code in ${left}s`;
          if (left-- <= 0) {
            resendBtn.disabled = false;
            resendBtn.textContent = 'Resend Code';
            return;
          }
          setTimeout(tick, 1000);
        };
        tick();
      };

      const sendCode = async () => {
        if (!email) {
          errBox.textContent = 'Missing email address. Please sign up or sign in again.';
          errBox.style.display = 'block';
          return;
        }
        try {
          await api.sendEmailVerification(email);
          errBox.style.display = 'none';
          startCooldown(60);
        } catch (err) {
          const msg = err.message || 'Could not send verification code.';
          const waitMatch = msg.match(/wait\s+(\d+)\s+seconds/i);
          if (waitMatch) {
            startCooldown(Number(waitMatch[1]));
            errBox.style.display = 'none';
          } else {
            errBox.textContent = msg;
            errBox.style.display = 'block';
          }
        }
      };

      if (justSent) {
        startCooldown(60);
      } else if (email) {
        sendCode();
      } else if (errBox) {
        errBox.textContent = 'Missing email address. Please sign up or sign in again.';
        errBox.style.display = 'block';
      }

      resendBtn?.addEventListener('click', sendCode);
      verifyForm?.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (this.isSubmitting) return;
        this.isSubmitting = true;
        submitBtn.disabled = true;
        errBox.style.display = 'none';
        try {
          const code = document.getElementById('verify-code').value.trim();
          await api.verifyEmail(email, code);
          sessionStorage.removeItem('nera_verification_email');
          api.logout();
          store.showToast('Email verified! Please sign in.', 'success');
          this.router.navigate(`/login?email=${encodeURIComponent(email)}&verified=1`, true);
        } catch (err) {
          errBox.textContent = err.message || 'Verification failed. Check the code and try again.';
          errBox.style.display = 'block';
        } finally {
          this.isSubmitting = false;
          submitBtn.disabled = false;
        }
      });
    }

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
            await api.register({ email, password, full_name: name, company_name: org });
            sessionStorage.setItem('nera_verification_email', email);
            sessionStorage.setItem('nera_verification_just_sent', '1');
            store.showToast('Account created! Please verify your email.', 'success');
            this.router.navigate('/verify-email', true);
            return;
          } else {
            try {
              const loginRes = await api.login(email, password);
              if (loginRes.token || loginRes.access_token) {
                const token = loginRes.token || loginRes.access_token;
                localStorage.setItem('nera_auth_token', token);
                api.setToken(token);
                const user = await api.getMe();
                store.setUser(user);
              }
              store.showToast('Signed in successfully', 'success');
            } catch (loginErr) {
              if (loginErr.status === 403 && String(loginErr.message).toLowerCase().includes('verification')) {
                sessionStorage.setItem('nera_verification_email', email);
                sessionStorage.removeItem('nera_verification_just_sent');
                this.router.navigate('/verify-email', true);
                return;
              }
              throw loginErr;
            }
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
