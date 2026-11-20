// HS256 JWT (Web Crypto) — кирүү токендерин түзүү жана текшерүү
const SECRET = 'studyltaly-demo-secret-change-me';
const enc = new TextEncoder();

const b64url = (buf) =>
  btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
const b64urlStr = (str) => b64url(enc.encode(str));
const fromB64url = (s) => {
  const pad = s.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((s.length + 3) % 4);
  return decodeURIComponent(
    atob(pad)
      .split('')
      .map((c) => '%' + c.charCodeAt(0).toString(16).padStart(2, '0'))
      .join('')
  );
};

async function hmac(data) {
  const key = await crypto.subtle.importKey('raw', enc.encode(SECRET), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return b64url(await crypto.subtle.sign('HMAC', key, enc.encode(data)));
}

export async function signJWT(payload, expiresInSec = 60 * 60 * 24 * 7) {
  const header = b64urlStr(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const now = Math.floor(Date.now() / 1000);
  const body = b64urlStr(JSON.stringify({ ...payload, iat: now, exp: now + expiresInSec }));
  const sig = await hmac(`${header}.${body}`);
  return `${header}.${body}.${sig}`;
}

export function decodeJWT(token) {
  try {
    const [, body] = String(token).split('.');
    return JSON.parse(fromB64url(body));
  } catch {
    return null;
  }
}

export async function verifyJWT(token) {
  const parts = String(token || '').split('.');
  if (parts.length !== 3) return null;
  const payload = decodeJWT(token);
  if (!payload || (payload.exp && payload.exp * 1000 < Date.now())) return null;
  if (payload.iss === 'dummyjson') return payload; // сырткы API'нин токени — exp гана текшерилет
  const sig = await hmac(`${parts[0]}.${parts[1]}`);
  return sig === parts[2] ? payload : null;
}

export async function sha256(text) {
  const buf = await crypto.subtle.digest('SHA-256', enc.encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
