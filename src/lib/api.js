// Жалпы fetch: timeout, retry, кэш (эс + sessionStorage)
const memory = new Map();
const TTL = 30 * 60 * 1000;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function getJSON(url, { timeout = 15000, retries = 2, cache = true, init } = {}) {
  if (cache && memory.has(url)) return memory.get(url);
  if (cache) {
    try {
      const raw = sessionStorage.getItem('api:' + url);
      if (raw) {
        const { t, d } = JSON.parse(raw);
        if (Date.now() - t < TTL) {
          memory.set(url, d);
          return d;
        }
      }
    } catch {
      /* ignore */
    }
  }
  let lastErr;
  for (let attempt = 0; attempt <= retries; attempt++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeout);
    try {
      const res = await fetch(url, { ...init, signal: ctrl.signal });
      clearTimeout(timer);
      if (res.status === 429) {
        await sleep(1200 * (attempt + 1));
        throw new Error('Too many requests');
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (cache) {
        memory.set(url, data);
        try {
          sessionStorage.setItem('api:' + url, JSON.stringify({ t: Date.now(), d: data }));
        } catch {
          /* quota */
        }
      }
      return data;
    } catch (e) {
      clearTimeout(timer);
      lastErr = e;
      if (attempt < retries) await sleep(500 * (attempt + 1));
    }
  }
  throw lastErr || new Error('Network error');
}

export async function sendJSON(url, method, body) {
  try {
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    const ct = res.headers.get('content-type') || '';
    const data = ct.includes('json') ? await res.json() : null;
    return { ok: res.ok, status: res.status, data };
  } catch (e) {
    return { ok: false, status: 0, data: null, error: e.message };
  }
}

export { sleep };
