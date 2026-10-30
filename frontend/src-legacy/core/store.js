/**
 * Nera 2.0 Global Reactive Store
 */

class Store {
  constructor() {
    this.state = {
      user: null,
      isAuthenticated: false,
      catalog: null,
      selectedProduct: 'sales_agent',
      activeQuote: null,
      quoteError: null,
      isQuoteLoading: false,
      conversation: {
        token: null,
        messages: [],
        isLoading: false
      },
      toast: null
    };
    this.listeners = new Set();
  }

  getState() {
    return this.state;
  }

  setState(partial) {
    this.state = { ...this.state, ...partial };
    this.notify();
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  notify() {
    for (const listener of this.listeners) {
      try {
        listener(this.state);
      } catch (e) {
        console.error('Store listener error:', e);
      }
    }
  }

  setSelectedProduct(product) {
    if (this.state.selectedProduct !== product) {
      this.setState({
        selectedProduct: product,
        activeQuote: null, // Invalidate stale quote immediately
        quoteError: null
      });
    }
  }

  showToast(message, type = 'info', duration = 4000) {
    this.setState({ toast: { message, type } });
    if (this._toastTimer) clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      this.setState({ toast: null });
    }, duration);
  }

  clearToast() {
    this.setState({ toast: null });
  }

  setUser(user) {
    this.setState({
      user,
      isAuthenticated: Boolean(user)
    });
  }
}

export const store = new Store();
