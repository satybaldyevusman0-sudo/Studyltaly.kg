// Realtime: бир браузердин табдары ортосунда BroadcastChannel,
// VITE_FIREBASE_DB_URL берилсе — Firebase Realtime Database (REST + SSE).
import { firebaseDbUrl } from './firebase.js';

let channel;
let siteId = 'hub';
const listeners = new Set();
let es;

export function initRealtime(id) {
  siteId = id;
  try {
    channel = new BroadcastChannel('rt:' + id);
    channel.onmessage = (e) => listeners.forEach((fn) => fn(e.data));
  } catch {
    channel = null;
  }
  if (firebaseDbUrl && typeof EventSource !== 'undefined') {
    try {
      es = new EventSource(`${firebaseDbUrl}/sites/${id}/events.json?orderBy="$key"&limitToLast=1`);
      let first = true;
      es.addEventListener('put', (e) => {
        if (first) {
          first = false;
          return;
        }
        try {
          const { data } = JSON.parse(e.data);
          if (data && data.type) listeners.forEach((fn) => fn({ ...data, remote: true }));
          else if (data) Object.values(data).forEach((d) => d?.type && listeners.forEach((fn) => fn({ ...d, remote: true })));
        } catch {
          /* ignore */
        }
      });
    } catch {
      es = null;
    }
  }
}

export function publish(type, payload) {
  const msg = { type, payload, at: Date.now() };
  try {
    channel?.postMessage(msg);
  } catch {
    /* ignore */
  }
  if (firebaseDbUrl) {
    fetch(`${firebaseDbUrl}/sites/${siteId}/events.json`, { method: 'POST', body: JSON.stringify(msg) }).catch(() => {});
  }
}

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
