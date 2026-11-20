// Сервердик /api/notify (Telegram + Email). Локалдуу dev'де жок болсо — үнсүз өтөт.
import { sendJSON } from './api.js';

export async function notifyOrder(payload) {
  const r = await sendJSON('/api/notify', 'POST', payload);
  return r.ok ? r.data : { ok: false, telegram: 'unavailable', email: 'unavailable' };
}

export async function createStripeSession(payload) {
  const r = await sendJSON('/api/checkout', 'POST', payload);
  if (r.ok && r.data?.url) return { url: r.data.url };
  return { demo: true, error: r.data?.error };
}
