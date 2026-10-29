import { bindMotion } from './motion.js';

/**
 * Nera 2.0 Client-Side Router
 * Supports root (/) and mounted (/v2/) subpaths.
 */

export class Router {
  constructor(routes = {}, basePath = '') {
    this.routes = routes;
    this.basePath = basePath.replace(/\/$/, '');
    this.currentPath = null;
    this.currentView = null;
    this.mountPoint = null;

    window.addEventListener('popstate', () => {
      this.handleRoute();
    });
  }

  setBasePath(basePath) {
    this.basePath = basePath.replace(/\/$/, '');
  }

  register(path, viewHandler) {
    this.routes[path] = viewHandler;
  }

  navigate(path, replace = false) {
    const cleanPath = path.startsWith('/') ? path : '/' + path;
    const fullPath = `${this.basePath}${cleanPath}`;
    if (replace) {
      window.history.replaceState({}, '', fullPath);
    } else {
      window.history.pushState({}, '', fullPath);
    }
    this.handleRoute();
  }

  getCleanPath() {
    let pathname = window.location.pathname;
    if (this.basePath && pathname.startsWith(this.basePath)) {
      pathname = pathname.substring(this.basePath.length);
    }
    if (!pathname || pathname === '') {
      pathname = '/';
    }
    return pathname;
  }

  getQueryParams() {
    return new URLSearchParams(window.location.search);
  }

  async handleRoute() {
    const path = this.getCleanPath();
    const query = this.getQueryParams();
    this.currentPath = path;

    let handler = this.routes[path] || this.routes['/'] || null;

    if (handler && this.mountPoint) {
      if (this.currentView && typeof this.currentView.cleanup === 'function') {
        try {
          this.currentView.cleanup();
        } catch (e) {
          console.warn('View cleanup error:', e);
        }
      }

      this.mountPoint.innerHTML = '';
      const viewInstance = typeof handler === 'function' ? new handler({ router: this, query }) : handler;
      this.currentView = viewInstance;
      window.__activeView = viewInstance;

      const renderedElement = await viewInstance.render();
      if (typeof renderedElement === 'string') {
        this.mountPoint.innerHTML = renderedElement;
      } else if (renderedElement instanceof HTMLElement) {
        this.mountPoint.appendChild(renderedElement);
      }

      if (typeof viewInstance.onMounted === 'function') {
        try {
          viewInstance.onMounted();
        } catch (e) {
          console.error('View onMounted error:', e);
        }
      }

      bindMotion(this.mountPoint);

      // Smooth scroll to top on navigation
      window.scrollTo({ top: 0, behavior: 'smooth' });

      // Highlight active navigation links
      document.querySelectorAll('.nera-nav-link').forEach(link => {
        const target = link.getAttribute('data-link');
        if (target === path || (path === '/' && target === '/')) {
          link.classList.add('active');
        } else {
          link.classList.remove('active');
        }
      });
    }
  }

  init(mountPoint) {
    this.mountPoint = mountPoint;
    this.handleRoute();
  }
}
