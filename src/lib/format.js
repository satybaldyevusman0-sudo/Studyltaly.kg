export const money = (n) => '$' + Number(n || 0).toFixed(2);

// id боюнча туруктуу "кокустук" сан (баасы жок API'лер үчүн)
export function seeded(id, min, max) {
  const s = String(id);
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const r = ((h >>> 0) % 10000) / 10000;
  return min + r * (max - min);
}

export const price = (id, min, max) => Math.round(seeded(id, min, max)) - 0.01;
export const rating = (id) => Math.round(seeded(id + 'r', 3.2, 5) * 10) / 10;

export const stripHtml = (html) => String(html || '').replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').trim();

export const formatDate = (d, lang = 'ru') => {
  try {
    return new Date(d).toLocaleDateString(lang === 'ky' ? 'ky-KG' : lang === 'en' ? 'en-US' : 'ru-RU', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return String(d);
  }
};

export const uid = (p = '') => p + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
