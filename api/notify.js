// Заказ/бронь тууралуу Telegram-ботко жана почтага билдирүү жөнөтөт.
// Vercel env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, RESEND_API_KEY, ORDER_EMAIL_TO
function esc(s) {
  return String(s ?? '').replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]);
}

function buildText(p) {
  const lines = [];
  lines.push(`<b>${p.type === 'booking' ? '📅 Жаңы бронь' : '🛒 Жаңы заказ'}</b> — ${esc(p.site)}`);
  lines.push(`№ ${esc(p.id)}`);
  if (p.customer) {
    lines.push(`👤 ${esc(p.customer.name)} · ${esc(p.customer.phone)} · ${esc(p.customer.email)}`);
    if (p.customer.address) lines.push(`📍 ${esc(p.customer.address)}`);
  }
  (p.items || []).forEach((i) => lines.push(`• ${esc(i.title)} × ${i.qty} = $${(i.price * i.qty).toFixed(2)}`));
  if (p.booking) lines.push(`🗓 ${esc(p.booking.date)} ${esc(p.booking.time)} · ${esc(p.booking.guests)} · ${esc(p.booking.title)}`);
  if (p.total != null) lines.push(`💰 Жалпы: $${Number(p.total).toFixed(2)} (${esc(p.payment)})`);
  return lines.join('\n');
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });
  const payload = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : req.body || {};
  const text = buildText(payload);
  const result = { telegram: 'skipped', email: 'skipped' };

  const { TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, RESEND_API_KEY, ORDER_EMAIL_TO } = process.env;

  if (TELEGRAM_BOT_TOKEN && TELEGRAM_CHAT_ID) {
    try {
      const r = await fetch(`https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: TELEGRAM_CHAT_ID, text, parse_mode: 'HTML' }),
      });
      result.telegram = r.ok ? 'sent' : `error ${r.status}`;
    } catch (e) {
      result.telegram = 'error';
    }
  }

  const to = [ORDER_EMAIL_TO, payload.customer?.email].filter(Boolean);
  if (RESEND_API_KEY && to.length) {
    try {
      const r = await fetch('https://api.resend.com/emails', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${RESEND_API_KEY}` },
        body: JSON.stringify({
          from: 'Orders <onboarding@resend.dev>',
          to,
          subject: `${payload.type === 'booking' ? 'Бронь' : 'Заказ'} №${payload.id} — ${payload.site}`,
          html: `<div style="font-family:sans-serif">${text.replace(/\n/g, '<br>')}</div>`,
        }),
      });
      result.email = r.ok ? 'sent' : `error ${r.status}`;
    } catch (e) {
      result.email = 'error';
    }
  }

  return res.status(200).json({ ok: true, ...result });
}
