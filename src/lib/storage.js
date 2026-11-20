// localStorage үстүндө сайтка бөлүнгөн (namespace) сактагыч
let ns = 'hub';
export const setNamespace = (n) => (ns = n);

export function load(key, fallback) {
  try {
    const raw = localStorage.getItem(`${ns}:${key}`);
    return raw == null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
}

export function save(key, value) {
  try {
    localStorage.setItem(`${ns}:${key}`, JSON.stringify(value));
  } catch {
    /* quota exceeded */
  }
}

export function loadGlobal(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw == null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
}

export function saveGlobal(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore */
  }
}
