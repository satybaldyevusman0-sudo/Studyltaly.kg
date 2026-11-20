// Контентти которуу: MyMemory Translation API (en → ru / ky)
import { getJSON } from './api.js';

const LANG = { ru: 'ru', ky: 'ky', en: 'en' };

export async function translateText(text, to, from = 'en') {
  if (!text || to === from) return text;
  const chunks = [];
  let rest = String(text);
  while (rest.length) {
    let cut = rest.length > 450 ? rest.lastIndexOf('. ', 450) + 1 : rest.length;
    if (cut <= 0) cut = 450;
    chunks.push(rest.slice(0, cut));
    rest = rest.slice(cut).trimStart();
  }
  const parts = await Promise.all(
    chunks.slice(0, 4).map((c) =>
      getJSON(
        `https://api.mymemory.translated.net/get?q=${encodeURIComponent(c)}&langpair=${from}|${LANG[to] || 'ru'}`,
        { retries: 1 }
      ).then((d) => d?.responseData?.translatedText || c)
    )
  );
  return parts.join(' ');
}
