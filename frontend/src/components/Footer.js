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
    el.innerHTML = `
      <div class="nera-footer-inner">
        <div class="nera-footer-brand">
          <img src="/frontend/src/brand/nera-logo.svg" alt="Nera" height="32" />
          <p>
            <strong>Nera — AI-Powered Business Automation.</strong><br/>
            Automate the work behind your business. Nera helps coordinate tasks and execute supported workflows, so you can spend less time managing routine operations and more time growing your business.
          </p>
          <div style="margin-top: 16px; display: inline-flex; align-items: center; gap: 8px;" class="nera-badge nera-badge-emerald">
            <span class="nera-badge-dot"></span>
            Operational • Orchestration Engine
          </div>
        </div>

        <div class="nera-footer-col">
          <h4>Automation Engines</h4>
          <ul>
            <li><a href="/products" data-link="/products">Sales Automation (₦199k)</a></li>
            <li><a href="/products" data-link="/products">Support Automation (₦149k)</a></li>
            <li><a href="/workforce" data-link="/workforce">Unified Workforce Pipeline</a></li>
            <li><a href="/demo" data-link="/demo">Live Simulation Studio</a></li>
          </ul>
        </div>

        <div class="nera-footer-col">
          <h4>Platform &amp; Workflows</h4>
          <ul>
            <li><a href="/pricing" data-link="/pricing">Deterministic Pricing</a></li>
            <li><a href="/build" data-link="/build">Workflow Configurator</a></li>
            <li><a href="/trust" data-link="/trust">Provable Safety &amp; Limits</a></li>
            <li><a href="/login" data-link="/login">Automation Workspace</a></li>
          </ul>
        </div>

        <div class="nera-footer-col">
          <h4>Execution &amp; Standards</h4>
          <ul>
            <li><a href="https://t.me" target="_blank" rel="noopener">Telegram Dispatcher</a></li>
            <li><a href="https://paystack.com" target="_blank" rel="noopener">Paystack Settlement</a></li>
            <li><a href="/trust" data-link="/trust">NDPR Data Isolation</a></li>
            <li><a href="/trust" data-link="/trust">Deterministic Boundaries</a></li>
          </ul>
        </div>
      </div>

      <div class="nera-footer-bottom">
        <div>&copy; ${new Date().getFullYear()} Nera Technologies Inc. All rights reserved.</div>
        <div style="display: flex; gap: 16px;">
          <span>Single Source of Truth Backend</span>
          <span>•</span>
          <span>Deterministic Integer Quoting</span>
        </div>
      </div>
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
