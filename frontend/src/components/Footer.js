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
          <img src="/frontend/src/brand/nera-logo-light.svg" alt="Nera" height="32" />
          <p>
            <strong>AI that knows when to act, and when to ask.</strong><br/>
            Meet your AI Sales Representative and AI Support Agent. Built for useful work, clear boundaries, and handoffs you can trust.
          </p>
          <div style="margin-top: 16px; display: inline-flex; align-items: center; gap: 8px;" class="nera-badge nera-badge-emerald">
            <span class="nera-badge-dot"></span>
            Provable restraint, by design
          </div>
        </div>

        <div class="nera-footer-col">
          <h4>AI agents</h4>
          <ul>
            <li><a href="/products" data-link="/products">AI Sales Representative (₦199k)</a></li>
            <li><a href="/products" data-link="/products">AI Support Agent (₦149k)</a></li>
            <li><a href="/workforce" data-link="/workforce">Both agents, together</a></li>
            <li><a href="/demo" data-link="/demo">Try a conversation</a></li>
          </ul>
        </div>

        <div class="nera-footer-col">
          <h4>How it works</h4>
          <ul>
            <li><a href="/pricing" data-link="/pricing">Simple, rule-based pricing</a></li>
            <li><a href="/build" data-link="/build">Set up your agents</a></li>
            <li><a href="/trust" data-link="/trust">What Nera will not do</a></li>
            <li><a href="/login" data-link="/login">Your workspace</a></li>
          </ul>
        </div>

        <div class="nera-footer-col">
          <h4>Connected tools</h4>
          <ul>
            <li><a href="https://t.me" target="_blank" rel="noopener">Telegram</a></li>
            <li><a href="https://paystack.com" target="_blank" rel="noopener">Paystack payments</a></li>
            <li><a href="/trust" data-link="/trust">Privacy and boundaries</a></li>
            <li><a href="/trust" data-link="/trust">Our approach to AI</a></li>
          </ul>
        </div>
      </div>

      <div class="nera-footer-bottom">
        <div>&copy; ${new Date().getFullYear()} Nera Technologies Inc. All rights reserved.</div>
        <div style="display: flex; gap: 16px;">
          <span>Grounded in your rules</span>
          <span>•</span>
          <span>Honest handoffs</span>
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
