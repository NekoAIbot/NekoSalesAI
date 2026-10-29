/**
 * Nera 2.0 Navigation Component
 * Fully responsive with mobile hamburger toggle and seamless SPA routing.
 */
import { store } from '../core/store.js';
import { api } from '../core/api.js';

export class Navbar {
  constructor({ router }) {
    this.router = router;
    this.isMobileMenuOpen = false;
  }

  render() {
    const state = store.getState();
    const isAuth = state.isAuthenticated;
    const user = state.user;

    const el = document.createElement('header');
    el.className = 'nera-nav';
    el.innerHTML = `
      <div class="nera-nav-inner">
        <a href="/" class="nera-nav-brand" data-link="/">
          <img src="/frontend/src/brand/nera-logo.svg" alt="Nera" height="34" style="height:34px;width:auto;" />
        </a>

        <nav class="nera-nav-links">
          <a href="/" class="nera-nav-link" data-link="/">Home</a>
          <a href="/products" class="nera-nav-link" data-link="/products">Products</a>
          <a href="/pricing" class="nera-nav-link" data-link="/pricing">Pricing</a>
          <a href="/build" class="nera-nav-link" data-link="/build">Build</a>
          ${isAuth ? `<a href="/dashboard" class="nera-nav-link" data-link="/dashboard">Dashboard</a>` : ''}
          <a href="/workforce" class="nera-nav-link" data-link="/workforce">Workforce</a>
          <a href="/demo" class="nera-nav-link" data-link="/demo">Live Demo</a>
          <a href="/trust" class="nera-nav-link" data-link="/trust">Trust &amp; Safety</a>
        </nav>

        <div class="nera-nav-actions">
          ${isAuth ? `
            <a href="/dashboard" class="nera-btn nera-btn-secondary nera-btn-sm" data-link="/dashboard">
              <span class="nera-badge-dot"></span>
              Workspace
            </a>
            <button class="nera-btn nera-btn-ghost nera-btn-sm" id="nav-logout-btn">Log out</button>
          ` : `
            <a href="/login" class="nera-btn nera-btn-ghost nera-btn-sm nav-login-link" data-link="/login">Sign In</a>
            <a href="/build" class="nera-btn nera-btn-primary nera-btn-sm nav-cta-btn" data-link="/build">
              Automate Your Business
            </a>
          `}
          <button class="nera-nav-toggle-btn" id="nav-toggle-btn" aria-label="Toggle Menu" aria-expanded="false" type="button" style="min-width: 44px; min-height: 44px; display: none; align-items: center; justify-content: center; cursor: pointer;">
            <span>☰</span>
          </button>
        </div>
      </div>

      <!-- Mobile Dropdown Navigation Drawer -->
      <div class="nera-nav-mobile-drawer" id="nav-mobile-drawer" style="display: none;">
        <a href="/" class="nera-mobile-nav-link" data-link="/">Home</a>
        <a href="/products" class="nera-mobile-nav-link" data-link="/products">Products</a>
        <a href="/pricing" class="nera-mobile-nav-link" data-link="/pricing">Pricing</a>
        <a href="/build" class="nera-mobile-nav-link" data-link="/build">Build</a>
        <a href="/workforce" class="nera-mobile-nav-link" data-link="/workforce">Workforce</a>
        <a href="/demo" class="nera-mobile-nav-link" data-link="/demo">Live Demo</a>
        <a href="/trust" class="nera-mobile-nav-link" data-link="/trust">Trust &amp; Safety</a>
        ${isAuth ? `
          <a href="/dashboard" class="nera-mobile-nav-link" data-link="/dashboard">Dashboard</a>
          <a href="/settings" class="nera-mobile-nav-link" data-link="/settings">Settings</a>
          <button class="nera-btn nera-btn-ghost" id="nav-mobile-logout-btn" type="button">Log out</button>
        ` : `
          <a href="/login" class="nera-mobile-nav-link" data-link="/login">Sign In</a>
          <a href="/build" class="nera-btn nera-btn-primary" style="margin-top: 8px; text-align: center; min-height: 44px; display: flex; align-items: center; justify-content: center;" data-link="/build">Automate Your Business</a>
        `}
      </div>
    `;

    // Intercept clicks on links with data-link
    el.querySelectorAll('[data-link]').forEach(anchor => {
      anchor.addEventListener('click', (e) => {
        e.preventDefault();
        const drawer = el.querySelector('#nav-mobile-drawer');
        const toggleBtn = el.querySelector('#nav-toggle-btn');
        if (drawer) drawer.style.display = 'none';
        this.isMobileMenuOpen = false;
        if (toggleBtn) {
          toggleBtn.innerHTML = '<span>☰</span>';
          toggleBtn.setAttribute('aria-expanded', 'false');
        }
        const targetPath = anchor.getAttribute('data-link');
        this.router.navigate(targetPath);
      });
    });

    // Mobile Hamburger Toggle
    const toggleBtn = el.querySelector('#nav-toggle-btn');
    const drawer = el.querySelector('#nav-mobile-drawer');
    if (toggleBtn && drawer) {
      toggleBtn.addEventListener('click', () => {
        this.isMobileMenuOpen = !this.isMobileMenuOpen;
        drawer.style.display = this.isMobileMenuOpen ? 'flex' : 'none';
        toggleBtn.innerHTML = this.isMobileMenuOpen ? '<span>✕</span>' : '<span>☰</span>';
        toggleBtn.setAttribute('aria-expanded', this.isMobileMenuOpen ? 'true' : 'false');
      });
    }

    const logoutBtn = el.querySelector('#nav-logout-btn') || el.querySelector('#nav-mobile-logout-btn');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', () => {
        api.logout();
        store.setUser(null);
        store.showToast('Logged out successfully', 'info');
        this.router.navigate('/');
      });
    }

    return el;
  }
}
