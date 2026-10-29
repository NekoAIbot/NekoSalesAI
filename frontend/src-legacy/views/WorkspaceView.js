import { api } from '../core/api.js';
import { store } from '../core/store.js';

export class WorkspaceView {
  constructor({ router }) { this.router = router; }
  async render() {
    return `<section class="account-page anim-fade-in-up">
      <div class="account-heading"><div><div class="nera-badge nera-badge-emerald">Account</div><h1>Workspace</h1><p>Your provisioned automation profiles and configuration.</p></div><button class="nera-btn nera-btn-ghost" id="workspace-logout">Log out</button></div>
      <nav class="account-tabs" aria-label="Account pages"><a href="/dashboard" data-link="/dashboard">Dashboard</a><a href="/workspace" data-link="/workspace" class="active" aria-current="page">Workspace</a><a href="/settings" data-link="/settings">Settings</a></nav>
      <section class="nera-card"><div class="account-heading"><div><h2>Provisioned profiles</h2><p>Profiles connected to your organization.</p></div><a href="/build" class="nera-btn nera-btn-primary" data-link="/build">Build an agent</a></div><div id="workspace-profiles" class="workspace-profile-list">Loading profiles…</div></section>
    </section>`;
  }
  async onMounted() {
    document.querySelectorAll('[data-link]').forEach((anchor) => anchor.addEventListener('click', (event) => { event.preventDefault(); this.router.navigate(anchor.getAttribute('data-link')); }));
    document.getElementById('workspace-logout').addEventListener('click', () => { api.logout(); store.setUser(null); this.router.navigate('/'); });
    if (!localStorage.getItem('nera_auth_token')) { this.router.navigate('/login?return_to=/workspace'); return; }
    const container = document.getElementById('workspace-profiles');
    try {
      const profiles = await api.getProfiles();
      container.innerHTML = profiles.length ? profiles.map((profile) => `<article class="workspace-profile"><div><span class="nera-badge nera-badge-emerald">${profile.status || 'ACTIVE'}</span><h3>${this.escape(profile.agent_name || profile.name || 'Automation profile')}</h3><p>${this.escape(profile.company_name || '')}${profile.plan_code ? ` · ${this.escape(profile.plan_code)}` : ''}</p></div><div class="workspace-profile-meta">${this.escape(profile.role || 'Agent')}</div></article>`).join('') : '<div class="workspace-empty"><h3>No profiles yet</h3><p>Your provisioned agents will appear here after setup.</p><a href="/build" class="nera-btn nera-btn-secondary" data-link="/build">Configure an agent</a></div>';
      container.querySelectorAll('[data-link]').forEach((anchor) => anchor.addEventListener('click', (event) => { event.preventDefault(); this.router.navigate(anchor.getAttribute('data-link')); }));
    } catch (error) {
      if (error.status === 401 || error.status === 403) { api.logout(); store.setUser(null); this.router.navigate('/login?return_to=/workspace'); }
      else container.textContent = error.message || 'Could not load workspace profiles.';
    }
  }
  escape(value) { const span = document.createElement('span'); span.textContent = String(value); return span.innerHTML; }
}
