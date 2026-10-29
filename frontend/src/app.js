/**
 * Nera 2.0 Greenfield Web Application Entrypoint
 * Owner-Approved Brand | Purpose-Built Components | Shared Nera Brain
 */
import { Router } from './core/router.js';
import { store } from './core/store.js';
import { api } from './core/api.js';

// Components
import { Navbar } from './components/Navbar.js';
import { Footer } from './components/Footer.js';
import { Toast } from './components/Toast.js';

// Views
import { HomeView } from './views/HomeView.js';
import { ProductsView } from './views/ProductsView.js';
import { WorkforceView } from './views/WorkforceView.js';
import { DemoView } from './views/DemoView.js';
import { PricingView } from './views/PricingView.js';
import { BuildView } from './views/BuildView.js';
import { TrustView } from './views/TrustView.js';
import { AuthView } from './views/AuthView.js';
import { DashboardView } from './views/DashboardView.js';
import { CheckoutReturnView } from './views/CheckoutReturnView.js';

class App {
  constructor() {
    this.appRoot = document.getElementById('app');
    
    // Auto-detect if mounted under /v2 or root /
    const isV2 = window.location.pathname.startsWith('/v2');
    const basePath = isV2 ? '/v2' : '';

    this.router = new Router({}, basePath);
    this.toast = new Toast();
  }

  async init() {
    // 1. Build persistent layout shell
    this.appRoot.innerHTML = '';

    const navbar = new Navbar({ router: this.router });
    const headerEl = navbar.render();
    this.appRoot.appendChild(headerEl);

    const mainEl = document.createElement('main');
    mainEl.id = 'main-content';
    mainEl.className = 'nera-content-wrapper';
    this.appRoot.appendChild(mainEl);

    const footer = new Footer({ router: this.router });
    const footerEl = footer.render();
    this.appRoot.appendChild(footerEl);

    // Re-render navbar whenever auth state changes in store
    store.subscribe((state) => {
      const newHeader = navbar.render();
      if (headerEl.parentNode) {
        headerEl.parentNode.replaceChild(newHeader, headerEl);
      }
    });

    // 2. Register Routes
    this.router.register('/', HomeView);
    this.router.register('/products', ProductsView);
    this.router.register('/workforce', WorkforceView);
    this.router.register('/demo', DemoView);
    this.router.register('/pricing', PricingView);
    this.router.register('/build', BuildView);
    this.router.register('/trust', TrustView);
    this.router.register('/login', AuthView);
    this.router.register('/signup', AuthView);
    this.router.register('/dashboard', DashboardView);
    this.router.register('/checkout/return', CheckoutReturnView);

    // 3. Check for existing session token
    const token = localStorage.getItem('nera_auth_token');
    if (token) {
      api.setToken(token);
      try {
        const user = await api.getMe();
        store.setUser(user);
      } catch (err) {
        console.warn('Session expired or invalid token:', err);
        api.setToken(null);
        store.setUser(null);
      }
    }

    // 4. Initialize Router on main content container
    this.router.init(mainEl);
  }
}

// Boot application when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    const app = new App();
    app.init();
  });
} else {
  const app = new App();
  app.init();
}
