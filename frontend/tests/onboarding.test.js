/**
 * Zero-dependency Node.js verification for Nera Organic Onboarding & Email Verification
 * Covers both the active SPA (frontend/app/) and Greenfield /v2 (frontend/src/).
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const frontendRoot = path.resolve(__dirname, '..');

function installBrowserGlobals(pathname = '/login', search = '') {
  const storage = () => {
    const map = new Map();
    return {
      getItem: (k) => (map.has(k) ? map.get(k) : null),
      setItem: (k, v) => map.set(k, String(v)),
      removeItem: (k) => map.delete(k),
      clear: () => map.clear(),
    };
  };
  globalThis.localStorage = storage();
  globalThis.sessionStorage = storage();
  globalThis.location = { pathname, search, origin: 'http://localhost:8000' };
  globalThis.window = {
    location: globalThis.location,
    localStorage: globalThis.localStorage,
    sessionStorage: globalThis.sessionStorage,
    history: { replaceState: () => {}, pushState: () => {} },
    addEventListener: () => {},
    scrollTo: () => {},
  };
}

test('Active SPA (frontend/app): auth() pre-fills email and shows verified banner', async () => {
  installBrowserGlobals('/login', '?email=ada%40example.com&verified=1');
  const { auth } = await import('../app/public-pages.js');
  const html = auth('login');
  assert.ok(html.includes('Email verified. Sign in to access your workspace.'));
  assert.ok(html.includes('value="ada@example.com"'));
});

test('Active SPA (frontend/app): main.js fixes immediate resend cooldown and handles verification flow', () => {
  const mainJs = fs.readFileSync(path.join(frontendRoot, 'app', 'main.js'), 'utf8');
  assert.ok(mainJs.includes("sessionStorage.setItem('nera_verification_just_sent','1')"));
  assert.ok(mainJs.includes("const justSent=sessionStorage.getItem('nera_verification_just_sent')==='1'"));
  assert.ok(mainJs.includes('if(justSent){startCooldown(60);}'));
  assert.ok(mainJs.includes("path==='/verify-email'"));
  assert.ok(mainJs.includes("go('/login?email='+encodeURIComponent(email)+'&verified=1',true)"));
});

test('Greenfield /v2 (frontend/src): api.js exposes sendEmailVerification and verifyEmail', async () => {
  installBrowserGlobals('/v2/signup', '');
  const calls = [];
  globalThis.fetch = async (url, opts) => {
    calls.push({ url, opts });
    return {
      ok: true,
      status: 200,
      headers: { get: () => 'application/json' },
      json: async () => ({ message: 'ok' }),
    };
  };

  const { api } = await import('../src/core/api.js');
  await api.sendEmailVerification('ada@example.com');
  await api.verifyEmail('ada@example.com', '123456');

  assert.equal(calls.length, 2);
  assert.equal(calls[0].url, '/api/v1/auth/email-verification/send');
  assert.equal(JSON.parse(calls[0].opts.body).email, 'ada@example.com');
  assert.equal(calls[1].url, '/api/v1/auth/email-verification/verify');
  assert.deepEqual(JSON.parse(calls[1].opts.body), { email: 'ada@example.com', code: '123456' });
});

test('Greenfield /v2 (frontend/src): AuthView renders verify mode and app.js registers /verify-email', async () => {
  installBrowserGlobals('/v2/verify-email', '?email=ada%40example.com');
  const { AuthView } = await import('../src/views/AuthView.js');
  const view = new AuthView({
    router: { navigate: () => {} },
    query: new URLSearchParams('?email=ada%40example.com'),
  });
  assert.equal(view.mode, 'verify');
  const html = await view.render();
  assert.ok(html.includes('id="verify-email-form"'));
  assert.ok(html.includes('id="resend-verification-btn"'));
  assert.ok(html.includes('ada@example.com'));

  const appJs = fs.readFileSync(path.join(frontendRoot, 'src', 'app.js'), 'utf8');
  assert.ok(appJs.includes("this.router.register('/verify-email', AuthView)"));
});
