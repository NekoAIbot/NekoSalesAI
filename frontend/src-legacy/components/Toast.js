/**
 * Nera 2.0 Toast Notification Component
 */
import { store } from '../core/store.js';

export class Toast {
  constructor() {
    this.el = document.createElement('div');
    this.el.id = 'nera-toast-container';
    this.el.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 9999;
      pointer-events: none;
      display: flex;
      flex-direction: column;
      gap: 10px;
    `;
    document.body.appendChild(this.el);

    store.subscribe((state) => {
      this.update(state.toast);
    });
  }

  update(toast) {
    this.el.innerHTML = '';
    if (!toast) return;

    const toastBox = document.createElement('div');
    toastBox.className = 'nera-card anim-fade-in-up';
    toastBox.style.cssText = `
      pointer-events: auto;
      padding: 12px 20px;
      display: flex;
      align-items: center;
      gap: 12px;
      background: ${toast.type === 'error' ? 'rgba(239, 68, 68, 0.95)' : toast.type === 'success' ? 'rgba(16, 185, 129, 0.95)' : 'rgba(30, 41, 59, 0.95)'};
      color: #FFFFFF;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
      border: 1px solid rgba(255,255,255,0.15);
      border-radius: 12px;
      font-size: 0.875rem;
      font-weight: 500;
    `;

    toastBox.innerHTML = `
      <span>${toast.message}</span>
      <button style="background: none; border: none; color: #FFF; font-weight: bold; cursor: pointer; margin-left: 8px;">&times;</button>
    `;

    toastBox.querySelector('button').addEventListener('click', () => {
      store.clearToast();
    });

    this.el.appendChild(toastBox);
  }
}
