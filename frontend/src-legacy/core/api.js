/**
 * Nera 2.0 API Client
 * Shared Nera Brain connector for customer-facing interfaces.
 * Connects directly to backend /api/v1/ endpoints with zero data leakage.
 */

class ApiClient {
  constructor(baseUrl = '') {
    this.baseUrl = baseUrl;
    this.token = (typeof localStorage !== 'undefined' ? localStorage.getItem('nera_auth_token') : null) || null;
  }

  setToken(token) {
    this.token = token;
    if (typeof localStorage !== 'undefined') {
      if (token) {
        localStorage.setItem('nera_auth_token', token);
      } else {
        localStorage.removeItem('nera_auth_token');
      }
    }
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const headers = {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
      ...(options.headers || {})
    };

    try {
      const response = await fetch(url, { ...options, headers });
      const contentType = response.headers.get('content-type') || '';
      let data = null;
      if (contentType.includes('application/json')) {
        data = await response.json();
      } else {
        data = await response.text();
      }

      if (!response.ok) {
        const errorMsg = (data && data.detail) || (data && data.message) || response.statusText || 'Request failed';
        const err = new Error(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg));
        err.status = response.status;
        err.data = data;
        throw err;
      }

      return data;
    } catch (err) {
      console.error(`API [${options.method || 'GET'} ${endpoint}] failed:`, err);
      throw err;
    }
  }

  // --- Catalog & Capabilities ---
  async getCatalog() {
    return this.request('/api/v1/sales/catalog');
  }

  // --- Authoritative Pricing ---
  async getPricingOptions() {
    return this.request('/api/v1/pricing/options');
  }

  async calculateQuote({ product_type, product_code, channels, integrations, languages, monthly_conversations = 500 }) {
    const product = product_type || product_code || 'sales_agent';
    return this.request('/api/v1/pricing/quote', {
      method: 'POST',
      body: JSON.stringify({
        product_type: product,
        product_code: product,
        channels: channels || ['web'],
        integrations: integrations || [],
        languages: languages || ['en'],
        monthly_conversations
      })
    });
  }

  async getQuote(referenceOrPayload) {
    if (typeof referenceOrPayload === 'object' && referenceOrPayload !== null) {
      return this.calculateQuote(referenceOrPayload);
    }
    return this.request(`/api/v1/pricing/quotes/${encodeURIComponent(referenceOrPayload)}`);
  }

  // --- Customer Sales & Support Conversations ---
  async createConversation(channel = 'web', metadata = {}) {
    return this.request('/api/v1/sales/conversations', {
      method: 'POST',
      body: JSON.stringify({ channel, metadata })
    });
  }

  async postMessage(token, message) {
    return this.request(`/api/v1/sales/conversations/${encodeURIComponent(token)}/messages`, {
      method: 'POST',
      body: JSON.stringify({ body: message })
    });
  }

  async getTranscript(token) {
    return this.request(`/api/v1/sales/conversations/${encodeURIComponent(token)}`);
  }

  // --- Order Processing & Paystack Checkout ---
  async createOrder({ email, customer_email, name, full_name, company, organization_name, company_name, quote_reference, product_type, products, channels, integrations, languages, monthly_conversations, callback_url }) {
    const targetEmail = email || customer_email;
    const targetName = name || full_name;
    const targetCompany = company || organization_name || company_name;
    const returnUrl = callback_url || (typeof window !== 'undefined' ? `${window.location.origin}/v2/checkout/return` : undefined);
    return this.request('/api/v1/checkout/orders', {
      method: 'POST',
      body: JSON.stringify({
        email: targetEmail,
        name: targetName || undefined,
        company: targetCompany || undefined,
        quote_reference: quote_reference || undefined,
        product_type: product_type || undefined,
        products: products || undefined,
        channels: channels || undefined,
        integrations: integrations || undefined,
        languages: languages || undefined,
        monthly_conversations: monthly_conversations || undefined,
        callback_url: returnUrl
      })
    });
  }

  async createCheckoutSession(params) {
    const res = await this.createOrder(params);
    return {
      ...res,
      authorization_url: res.checkout_url
    };
  }

  async createQuote(params) {
    return this.calculateQuote(params);
  }

  async getOrderStatus(reference) {
    return this.request(`/api/v1/checkout/orders/${encodeURIComponent(reference)}`);
  }

  async checkPaymentStatus(reference) {
    return this.getOrderStatus(reference);
  }

  // --- Auth & Customer Workspace ---
  async login(email, password) {
    const data = await this.request('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    });
    if (data && data.access_token) {
      this.setToken(data.access_token);
    }
    return data;
  }

  async register(emailOrPayload, password, fullName, orgName) {
    let payload;
    if (typeof emailOrPayload === 'object' && emailOrPayload !== null) {
      payload = {
        email: emailOrPayload.email,
        password: emailOrPayload.password,
        full_name: emailOrPayload.full_name || emailOrPayload.fullName || emailOrPayload.name,
        company_name: emailOrPayload.company_name || emailOrPayload.organization_name || emailOrPayload.company || emailOrPayload.orgName || undefined
      };
    } else {
      payload = {
        email: emailOrPayload,
        password,
        full_name: fullName,
        company_name: orgName || undefined
      };
    }
    return this.request('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async createTelegramLinkToken() {
    return this.request("/api/v1/telegram/link-token", { method: "POST" });
  }

  async getMe() {
    return this.request('/api/v1/auth/me');
  }

  async updateProfile({ full_name, company_name }) {
    return this.request('/api/v1/auth/profile', {
      method: 'PUT',
      body: JSON.stringify({ full_name, company_name })
    });
  }

  async changePassword(current_password, new_password) {
    return this.request('/api/v1/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password, new_password })
    });
  }

  async getWorkspaceProfiles() {
    return this.request('/api/v1/organizations/workspace/profiles');
  }

  async getProfiles() {
    return this.getWorkspaceProfiles();
  }

  logout() {
    this.setToken(null);
  }
}

export const api = new ApiClient();
