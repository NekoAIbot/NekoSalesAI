/**
 * Greenfield Frontend Module & Asset Verification Test
 */
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, '..');

console.log('Testing Greenfield Frontend Assets and Modules...');

// 1. Verify Brand Assets
const brandDir = path.join(rootDir, 'src', 'brand');
const emblemPath = path.join(brandDir, 'nera-emblem.svg');
const logoPath = path.join(brandDir, 'nera-logo.svg');
const faviconPath = path.join(brandDir, 'favicon.svg');

assert(fs.existsSync(emblemPath), 'Emblem SVG must exist');
assert(fs.existsSync(logoPath), 'Logo SVG must exist');
assert(fs.existsSync(faviconPath), 'Favicon SVG must exist');

const emblemContent = fs.readFileSync(emblemPath, 'utf8');
assert(emblemContent.includes('<svg'), 'Emblem must contain SVG tag');
assert(emblemContent.includes('#10B981'), 'Emblem must contain emerald brand token');
assert(emblemContent.includes('#3B82F6'), 'Emblem must contain electric blue brand token');

// 2. Verify Design Tokens
const tokensPath = path.join(rootDir, 'src', 'styles', 'tokens.css');
const tokensContent = fs.readFileSync(tokensPath, 'utf8');
assert(tokensContent.includes('--emerald: #10B981;'), 'Tokens must declare emerald');
assert(tokensContent.includes('--electric-blue: #3B82F6;'), 'Tokens must declare electric blue');
assert(tokensContent.includes('--grad-ribbon:'), 'Tokens must declare grad-ribbon');

// 3. Verify All 10 Greenfield Views Exist
const viewsDir = path.join(rootDir, 'src', 'views');
const views = [
  'HomeView.js',
  'ProductsView.js',
  'WorkforceView.js',
  'DemoView.js',
  'PricingView.js',
  'BuildView.js',
  'TrustView.js',
  'AuthView.js',
  'DashboardView.js',
  'CheckoutReturnView.js'
];

for (const v of views) {
  const filePath = path.join(viewsDir, v);
  assert(fs.existsSync(filePath), `View file ${v} must exist`);
  const content = fs.readFileSync(filePath, 'utf8');
  assert(content.includes('class ') && content.includes('render('), `View ${v} must export a class with a render method`);
}

// 4. Verify Router & Store
const routerPath = path.join(rootDir, 'src', 'core', 'router.js');
const storePath = path.join(rootDir, 'src', 'core', 'store.js');
const apiPath = path.join(rootDir, 'src', 'core', 'api.js');

assert(fs.existsSync(routerPath), 'router.js must exist');
assert(fs.existsSync(storePath), 'store.js must exist');
assert(fs.existsSync(apiPath), 'api.js must exist');

const apiContent = fs.readFileSync(apiPath, 'utf8');
assert(apiContent.includes('createCheckoutSession'), 'api.js must provide createCheckoutSession');
assert(apiContent.includes('createQuote'), 'api.js must provide createQuote');
assert(apiContent.includes('createOrder'), 'api.js must provide createOrder');

// 5. Verify Complete Add-On Catalog in Configurator and Pricing
const buildContent = fs.readFileSync(path.join(viewsDir, 'BuildView.js'), 'utf8');
assert(buildContent.includes('value="whatsapp"'), 'BuildView must include WhatsApp channel');
assert(buildContent.includes('value="email"'), 'BuildView must include Email channel');
assert(buildContent.includes('value="calendar"'), 'BuildView must include Calendar integration');
assert(buildContent.includes('value="pid"'), 'BuildView must include Pidgin language');
assert(buildContent.includes('restorePendingBuild'), 'BuildView must restore saved configuration');

const pricingContent = fs.readFileSync(path.join(viewsDir, 'PricingView.js'), 'utf8');
assert(pricingContent.includes('calc-chan-wa'), 'PricingView must include WhatsApp channel checkbox');
assert(pricingContent.includes('calc-chan-email'), 'PricingView must include Email channel checkbox');
assert(pricingContent.includes('calc-lang-pid'), 'PricingView must include Pidgin language checkbox');

console.log('✓ All Greenfield frontend asset, catalog and view integrity checks passed successfully.');
