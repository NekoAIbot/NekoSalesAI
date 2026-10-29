import { api } from '../core/api.js';
import { store } from '../core/store.js';

export class SettingsView {
  constructor({ router }) { this.router = router; this.user = null; }

  async render() {
    return `
      <section class="account-page anim-fade-in-up">
        <div class="account-heading"><div><div class="nera-badge nera-badge-blue">Account</div><h1>Settings</h1><p>Manage your profile and sign-in details.</p></div><button class="nera-btn nera-btn-ghost" id="settings-logout">Log out</button></div>
        <nav class="account-tabs" aria-label="Account pages">
          <a href="/dashboard" data-link="/dashboard">Dashboard</a><a href="/workspace" data-link="/workspace">Workspace</a><a href="/settings" data-link="/settings" class="active" aria-current="page">Settings</a>
        </nav>
        <div class="nera-grid-2 account-settings-grid">
          <form class="nera-card" id="profile-form"><h2>Profile</h2><p class="account-card-copy">Update the name shown on your account.</p>
            <div class="nera-form-group"><label class="nera-label" for="settings-name">Full name</label><input class="nera-input" id="settings-name" name="full_name" required /></div>
            <div class="nera-form-group"><label class="nera-label" for="settings-email">Email</label><input class="nera-input" id="settings-email" type="email" disabled /></div>
            <div class="nera-form-group"><label class="nera-label" for="settings-company">Organization</label><input class="nera-input" id="settings-company" name="company_name" /></div>
            <button class="nera-btn nera-btn-primary" type="submit">Save profile</button><p class="settings-status" id="profile-status" role="status"></p>
          </form>
          <form class="nera-card" id="password-form"><h2>Password</h2><p class="account-card-copy">Change your account password securely.</p>
            <div class="nera-form-group"><label class="nera-label" for="current-password">Current password</label><input class="nera-input" id="current-password" type="password" autocomplete="current-password" required /></div>
            <div class="nera-form-group"><label class="nera-label" for="new-password">New password</label><input class="nera-input" id="new-password" type="password" autocomplete="new-password" minlength="8" required /></div>
            <button class="nera-btn nera-btn-secondary" type="submit">Update password</button><p class="settings-status" id="password-status" role="status"></p>
          </form>
          <section class="nera-card notification-card"><h2>Notifications</h2><p class="account-card-copy">Choose whether this browser should show Nera account updates.</p>
            <label class="notification-toggle"><input id="notification-pref" type="checkbox" /> <span>Enable in-app notifications</span></label>
            <p class="account-card-copy">This preference is stored in this browser. Email notification controls are not available in the account API yet.</p>
          </section>
        </div>
      </section>`;
  }

  async onMounted() {
    this.bindNavigation();
    if (!localStorage.getItem('nera_auth_token')) { this.router.navigate('/login?return_to=/settings'); return; }
    try {
      this.user = await api.getMe();
      document.getElementById('settings-name').value = this.user.full_name || '';
      document.getElementById('settings-email').value = this.user.email || '';
      document.getElementById('settings-company').value = this.user.organization_name || '';
    } catch (error) { this.handleAuthError(error); return; }

    const pref = document.getElementById('notification-pref');
    pref.checked = localStorage.getItem('nera_notifications_enabled') !== 'false';
    pref.addEventListener('change', () => localStorage.setItem('nera_notifications_enabled', String(pref.checked)));
    document.getElementById('profile-form').addEventListener('submit', async (event) => {
      event.preventDefault(); this.setStatus('profile-status', 'Saving…');
      try {
        this.user = await api.updateProfile({ full_name: document.getElementById('settings-name').value.trim(), company_name: document.getElementById('settings-company').value.trim() });
        store.setUser(this.user); this.setStatus('profile-status', 'Profile saved.');
      } catch (error) { this.setStatus('profile-status', error.message || 'Could not save profile.'); }
    });
    document.getElementById('password-form').addEventListener('submit', async (event) => {
      event.preventDefault(); this.setStatus('password-status', 'Updating…');
      try { await api.changePassword(document.getElementById('current-password').value, document.getElementById('new-password').value); event.currentTarget.reset(); this.setStatus('password-status', 'Password updated.'); }
      catch (error) { this.setStatus('password-status', error.message || 'Could not update password.'); }
    });
    document.getElementById('settings-logout').addEventListener('click', () => this.logout());
  }

  bindNavigation() {
    document.querySelectorAll('[data-link]').forEach((anchor) => anchor.addEventListener('click', (event) => { event.preventDefault(); this.router.navigate(anchor.getAttribute('data-link')); }));
  }
  setStatus(id, message) { document.getElementById(id).textContent = message; }
  handleAuthError(error) {
    if (error.status === 401 || error.status === 403) { this.logout(false); this.router.navigate('/login?return_to=/settings'); }
    else this.setStatus('profile-status', error.message || 'Could not load account settings.');
  }
  logout(showMessage = true) {
    api.logout(); store.setUser(null);
    if (showMessage) store.showToast('Logged out successfully', 'info');
    this.router.navigate('/');
  }
}
