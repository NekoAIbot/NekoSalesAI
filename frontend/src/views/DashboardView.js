/**
 * Nera 2.0 Greenfield — Dashboard View
 * Customer organization workspace, automation workflow orchestrator, and embed snippets.
 */
import { api } from '../core/api.js';
import { store } from '../core/store.js';

export class DashboardView {
  constructor({ router }) {
    this.router = router;
    this.profiles = [];
    this.user = null;
  }

  async render() {
    return `
      <div class="anim-fade-in-up" style="max-width: 1040px; margin: 0 auto;">
        <!-- Header -->
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 36px; flex-wrap: wrap; gap: 16px;">
          <div>
            <div class="nera-badge nera-badge-emerald" style="margin-bottom: 8px;">Automation Workspace Active</div>
            <h1 style="font-size: 2rem; font-weight: 800;">Workflow Orchestration Hub</h1>
            <p style="color: var(--slate-light); font-size: 0.9375rem;" id="dash-user-subtitle">
              Manage and monitor your autonomous business automation workflows.
            </p>
          </div>

          <div style="display: flex; gap: 12px;">
            <a href="/demo" class="nera-btn nera-btn-secondary" data-link="/demo">Launch Studio</a>
            <a href="/build" class="nera-btn nera-btn-primary" data-link="/build">+ New Workflow</a>
          </div>
        </div>

        <nav class="account-tabs" aria-label="Account pages">
          <a href="/dashboard" data-link="/dashboard" class="active" aria-current="page">Dashboard</a>
          <a href="/workspace" data-link="/workspace">Workspace</a>
          <a href="/settings" data-link="/settings">Settings</a>
        </nav>

        <!-- Automation Operational Status HUD -->
        <div class="canvas-metrics" style="margin-bottom: 32px;">
          <div class="metric-box">
            <div class="metric-val">14 Tasks</div>
            <div class="metric-lbl">Active Workflows</div>
          </div>
          <div class="metric-box">
            <div class="metric-val">100%</div>
            <div class="metric-lbl">Deterministic Pricing</div>
          </div>
          <div class="metric-box">
            <div class="metric-val">Sub-second</div>
            <div class="metric-lbl">Target Cycle Time</div>
          </div>
        </div>

        <!-- Provisioned Automation Engines Section -->
        <div class="nera-card" style="margin-bottom: 36px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h2 style="font-size: 1.25rem; font-weight: 700;">Provisioned Automation Engines</h2>
            <span class="nera-mono" style="font-size: 0.8125rem; color: var(--emerald-light);">ORCHESTRATOR: ONLINE</span>
          </div>

          <div id="dash-profiles-container" style="display: flex; flex-direction: column; gap: 16px;">
            <!-- Rendered by onMounted -->
            <div style="text-align: center; padding: 32px; color: var(--slate-light);">
              Loading automation engines...
            </div>
          </div>
        </div>

        <!-- Integration Snippets Section -->
        <div class="nera-grid-2">
          <!-- Web Widget Embed -->
          <div class="nera-card">
            <div class="nera-badge nera-badge-blue" style="margin-bottom: 12px;">Web Integration</div>
            <h3 style="font-size: 1.125rem; font-weight: 700; margin-bottom: 8px;">Embed Automation on Your Site</h3>
            <p style="color: var(--slate-light); font-size: 0.875rem; margin-bottom: 16px;">
              Paste this snippet into your website's HTML before the closing <code>&lt;/body&gt;</code> tag to initiate autonomous sales &amp; support workflows:
            </p>
            <div style="background: var(--bg-ground); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-card); font-family: var(--font-mono); font-size: 0.8125rem; color: var(--emerald-light); word-break: break-all;">
              &lt;script src="https://nera.app/widget.js" data-agent-id="agt_live_948201" async&gt;&lt;/script&gt;
            </div>
          </div>

          <!-- Telegram Bot Pairing -->
          <div class="nera-card">
            <div class="nera-badge nera-badge-emerald" style="margin-bottom: 12px;">Telegram Dispatcher</div>
            <h3 style="font-size: 1.125rem; font-weight: 700; margin-bottom: 8px;">Connect to Telegram</h3>
            <p style="color: var(--slate-light); font-size: 0.875rem; margin-bottom: 16px;">
              Open your business bot in Telegram and send the pairing command to synchronize customer memory:
            </p>
            <div style="background: var(--bg-ground); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-card); font-family: var(--font-mono); font-size: 0.8125rem; color: var(--electric-blue-light); word-break: break-all;">
              /connect_nera agt_live_948201
            </div>
          </div>
        </div>
      </div>
    `;
  }

  async onMounted() {
    document.querySelectorAll('[data-link]').forEach(anchor => {
      anchor.addEventListener('click', (e) => {
        e.preventDefault();
        const targetPath = anchor.getAttribute('data-link');
        this.router.navigate(targetPath);
      });
    });

    const userSubtitle = document.getElementById('dash-user-subtitle');
    const container = document.getElementById('dash-profiles-container');

    const token = localStorage.getItem('nera_auth_token');
    if (!token) {
      store.showToast('Please sign in to access your organization workspace.', 'info');
      this.router.navigate('/login?return_to=/dashboard');
      return;
    }

    try {
      this.user = await api.getMe();
      if (userSubtitle && this.user) {
        userSubtitle.textContent = `Organization: ${this.user.organization_name || 'Standard Account'} (${this.user.email})`;
      }

      this.profiles = await api.getProfiles();
      if (!this.profiles || this.profiles.length === 0) {
        this.renderProfiles([
          {
            id: 'prf_default_sales',
            name: 'Primary Inbound Sales Engine',
            product_code: 'sales_agent',
            status: 'ACTIVE',
            channels: ['web', 'telegram'],
            created_at: new Date().toISOString()
          }
        ]);
      } else {
        this.renderProfiles(this.profiles);
      }
    } catch (err) {
      console.warn('Dashboard load error:', err);
      if (err.status === 401 || err.status === 403) {
        api.setToken(null);
        localStorage.removeItem('nera_auth_token');
        store.setUser(null);
        store.showToast('Session expired. Please sign in again.', 'warning');
        this.router.navigate('/login?return_to=/dashboard');
        return;
      }
      if (userSubtitle) {
        userSubtitle.textContent = 'Workspace Telemetry Active';
      }
    }
  }

  renderProfiles(profiles) {
    const container = document.getElementById('dash-profiles-container');
    if (!container) return;

    container.innerHTML = profiles.map(p => `
      <div style="background: var(--bg-surface-elevated); padding: 20px; border-radius: var(--radius-lg); border: 1px solid var(--border-subtle); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px;">
        <div>
          <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 6px;">
            <span class="nera-badge nera-badge-emerald" style="padding: 2px 8px; font-size: 0.6875rem;">${p.status || 'ACTIVE'}</span>
            <strong style="font-size: 1.0625rem;">${p.name || 'Nera Business Automation Engine'}</strong>
          </div>
          <div style="font-size: 0.8125rem; color: var(--slate-light);">
            Engine: <span class="nera-mono" style="color: var(--ivory);">${p.product_code || 'sales_agent'}</span> • 
            Channels: <span class="nera-mono">${(p.channels || ['web']).join(', ')}</span>
          </div>
        </div>

        <div style="display: flex; gap: 10px;">
          <a href="/demo" class="nera-btn nera-btn-secondary nera-btn-sm" data-link="/demo">Test Pipeline</a>
          <a href="/build" class="nera-btn nera-btn-primary nera-btn-sm" data-link="/build">Configure</a>
        </div>
      </div>
    `).join('');

    container.querySelectorAll('[data-link]').forEach(anchor => {
      anchor.addEventListener('click', (e) => {
        e.preventDefault();
        const targetPath = anchor.getAttribute('data-link');
        this.router.navigate(targetPath);
      });
    });
  }
}
