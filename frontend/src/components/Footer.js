import { store } from '../core/store.js';

/**
 * Nera 2.0 Footer Component
 */
export class Footer {
  constructor({ router }) {
    this.router = router;
  }

  render() {
    const el = document.createElement('footer');
    el.className = 'nera-footer';
    const state = store.getState();
    el.innerHTML = `
      <div class="nera-footer-inner">
        <div class="nera-footer-brand">
          <img src="/frontend/src/brand/nera-logo.svg" alt="Nera" height="32" />
          <p><strong>Nera builds the AI your business needs, and hands it over working.</strong><br/>Two focused products. Quotes grounded in requirements. No invented capabilities.</p>
          <div style="margin-top: 16px; display: inline-flex; align-items: center; gap: 8px;" class="nera-badge nera-badge-emerald"><span class="nera-badge-dot"></span> Provable restraint</div>
        </div>
        <div class="nera-footer-col"><h4>Products</h4><ul><li><a href="/products" data-link="/products">AI Sales Representative</a></li><li><a href="/products" data-link="/products">AI Support Agent</a></li><li><a href="/demo" data-link="/demo">Product demo</a></li></ul></div>
        <div class="nera-footer-col"><h4>Learn</h4><ul><li><a href="/pricing" data-link="/pricing">Pricing</a></li><li><a href="/trust" data-link="/trust">Trust &amp; boundaries</a></li><li><a href="/login" data-link="/login">Sign in</a></li></ul></div>
        ${state.isAuthenticated ? `<div class="nera-footer-col"><h4>Your workspace</h4><ul><li><a href="/build" data-link="/build">Build</a></li><li><a href="/dashboard" data-link="/dashboard">Dashboard</a></li><li><a href="/workspace" data-link="/workspace">Workspace</a></li><li><a href="/settings" data-link="/settings">Settings</a></li></ul></div>` : ''}
      </div>
      <div class="nera-footer-bottom"><div>&copy; ${new Date().getFullYear()} Nera</div><div><span>Bounded builds</span><span> · </span><span>Deterministic quotes</span></div></div>
    `;

    el.querySelectorAll('[data-link]').forEach(anchor => {
      anchor.addEventListener('click', (e) => {
        e.preventDefault();
        const targetPath = anchor.getAttribute('data-link');
        this.router.navigate(targetPath);
      });
    });

    return el;
  }
}
