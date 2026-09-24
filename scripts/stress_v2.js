/* Local API stress test v2 — with detailed error reporting */
const http = require('http');

const API = 'http://127.0.0.1:8000';
const PRODUCTS = ['sales_agent', 'support_agent', 'workforce_agent'];
const CHANNELS = ['web', 'telegram', 'whatsapp', 'email'];
const INTEGRATIONS = ['crm', 'calendar', 'payment', 'inventory', 'accounting', 'ecommerce', 'pos', 'helpdesk', 'stock', 'erp'];
const LANGUAGES = ['en', 'yo', 'ha', 'ig', 'pidgin'];
const VOLUMES = [250, 450, 500, 1000, 2450, 2500, 3750, 5000, 10000, 25000];

function rand(arr) { return arr[Math.floor(Math.random() * arr.length)]; }
function randN(arr, n) { const s = [...arr].sort(() => 0.5 - Math.random()); return s.slice(0, n); }

function post(path, body) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body);
    const r = http.request(API + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': data.length }
    }, res => {
      let b = '';
      res.on('data', c => b += c);
      res.on('end', () => {
        try { resolve({ status: res.statusCode, data: JSON.parse(b) }); }
        catch (e) { resolve({ status: res.statusCode, data: b }); }
      });
    });
    r.on('error', reject);
    r.write(data);
    r.end();
  });
}

async function customer(cid) {
  const results = [];

  try {
    const prod = rand(PRODUCTS);
    const chans = ['web', ...randN(CHANNELS.slice(1), Math.floor(Math.random() * 4))];
    const vol = rand(VOLUMES);
    const integs = randN(INTEGRATIONS, Math.floor(Math.random() * 11));
    const langs = ['en', ...randN(LANGUAGES.slice(1), Math.floor(Math.random() * 4))];

    // Step 1: Get quote
    const t1 = Date.now();
    const quote = await post('/api/v1/pricing/quote', {
      product_type: prod, channels: chans, monthly_conversations: vol,
      integrations: integs, languages: langs
    });
    const lat1 = Date.now() - t1;
    results.push({ step: 'quote', success: quote.status === 200 && !!quote.data.reference, status: quote.status, lat: lat1, ref: quote.data.reference, detail: quote.data.detail });

    if (quote.data.reference) {
      // Step 2: Create checkout order (unique email per customer)
      const t2 = Date.now();
      const order = await post('/api/v1/checkout/orders', {
        quote_reference: quote.data.reference,
        email: `stress${cid}_${Date.now()}@test.example.com`,
        product_type: prod, channels: chans, monthly_conversations: vol,
        integrations: integs, languages: langs
      });
      const lat2 = Date.now() - t2;
      results.push({ step: 'checkout', success: order.status === 200, status: order.status, lat: lat2, detail: order.data.detail || order.data.error });
    }
  } catch (e) {
    results.push({ success: false, status: 0, lat: 0, error: e.message });
  }

  return results;
}

async function main() {
  const N = parseInt(process.argv[2]) || 1500;
  console.log(`Starting stress test v2 with ${N} customers...`);

  const allResults = [];
  const quoteErrors = [];
  const checkoutErrors = [];
  const tStart = Date.now();

  // Run in batches of 20 concurrent (reduced for stability)
  for (let i = 0; i < N; i += 20) {
    const batch = [];
    for (let j = i; j < Math.min(i + 20, N); j++) {
      batch.push(customer(j).then(r => {
        allResults.push(...r);
        for (const res of r) {
          if (!res.success && res.step === 'quote') quoteErrors.push(res);
          if (!res.success && res.step === 'checkout') checkoutErrors.push(res);
        }
      }).catch(e => {
        allResults.push({ success: false, status: 0, lat: 0, error: e.message });
      }));
    }
    await Promise.all(batch);
    if (i % 200 === 0) console.log(`Progress: ${i}/${N}`);
  }

  const totalTime = Date.now() - tStart;
  const total = allResults.length;
  const successes = allResults.filter(r => r.success).length;
  const failures = total - successes;
  const quoteResults = allResults.filter(r => r.step === 'quote');
  const checkoutResults = allResults.filter(r => r.step === 'checkout');
  const lats = allResults.map(r => r.lat).filter(l => l > 0).sort((a, b) => a - b);

  const report = {
    total_customers: N,
    total_requests: total,
    successful: successes,
    failed: failures,
    success_rate: `${(successes/total*100).toFixed(1)}%`,
    total_time_ms: totalTime,
    requests_per_second: (total / (totalTime / 1000)).toFixed(1),
    quote_success: quoteResults.filter(r => r.success).length + '/' + quoteResults.length,
    checkout_success: checkoutResults.filter(r => r.success).length + '/' + checkoutResults.length,
    latency: {
      avg_ms: lats.length ? (lats.reduce((a,b) => a+b, 0) / lats.length).toFixed(1) : 0,
      min_ms: lats[0] || 0,
      p50_ms: lats[Math.floor(lats.length * 0.5)] || 0,
      p95_ms: lats[Math.floor(lats.length * 0.95)] || 0,
      p99_ms: lats[Math.floor(lats.length * 0.99)] || 0,
      max_ms: lats[lats.length - 1] || 0,
    },
    quote_error_samples: quoteErrors.slice(0, 5).map(e => ({ status: e.status, detail: e.detail })),
    checkout_error_samples: checkoutErrors.slice(0, 5).map(e => ({ status: e.status, detail: e.detail }))
  };

  console.log(JSON.stringify(report, null, 2));
  require('fs').writeFileSync('/home/user/screenshots/stress_report_v2.json', JSON.stringify(report, null, 2));
}

main().catch(e => { console.error(e); process.exit(1); });
