// Stripe Checkout Session түзөт. Vercel env: STRIPE_SECRET_KEY (sk_test_...)
export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });
  const key = process.env.STRIPE_SECRET_KEY;
  if (!key) return res.status(200).json({ demo: true });

  const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : req.body || {};
  const { items = [], successUrl, cancelUrl, email } = body;
  const params = new URLSearchParams();
  params.append('mode', 'payment');
  params.append('success_url', successUrl);
  params.append('cancel_url', cancelUrl);
  if (email) params.append('customer_email', email);
  items.slice(0, 50).forEach((it, i) => {
    params.append(`line_items[${i}][quantity]`, String(Math.max(1, Number(it.qty) || 1)));
    params.append(`line_items[${i}][price_data][currency]`, 'usd');
    params.append(`line_items[${i}][price_data][unit_amount]`, String(Math.round(Number(it.price) * 100)));
    params.append(`line_items[${i}][price_data][product_data][name]`, String(it.title).slice(0, 200));
  });

  try {
    const r = await fetch('https://api.stripe.com/v1/checkout/sessions', {
      method: 'POST',
      headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/x-www-form-urlencoded' },
      body: params,
    });
    const data = await r.json();
    if (!r.ok) return res.status(400).json({ error: data.error?.message || 'Stripe error' });
    return res.status(200).json({ url: data.url, id: data.id });
  } catch (e) {
    return res.status(500).json({ error: 'Stripe unreachable' });
  }
}
