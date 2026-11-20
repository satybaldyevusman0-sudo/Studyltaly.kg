// Firebase — Google / GitHub OAuth. Конфиг жок болсо демо режим иштейт.
const cfg = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
  databaseURL: import.meta.env.VITE_FIREBASE_DB_URL,
};

export const firebaseEnabled = Boolean(cfg.apiKey && cfg.authDomain);

let authPromise;
function getAuthLazy() {
  if (!authPromise) {
    authPromise = Promise.all([import('firebase/app'), import('firebase/auth')]).then(([appMod, authMod]) => {
      const app = appMod.getApps().length ? appMod.getApp() : appMod.initializeApp(cfg);
      return { auth: authMod.getAuth(app), authMod };
    });
  }
  return authPromise;
}

export async function oauthSignIn(providerName) {
  if (!firebaseEnabled) {
    // Демо: Firebase туташтырылбаганда OAuth жоопту окшоштуруу
    const demo = providerName === 'google'
      ? { name: 'Google User', email: 'google.user@gmail.com', avatar: 'https://i.pravatar.cc/150?img=12' }
      : { name: 'GitHub Dev', email: 'dev@github.com', avatar: 'https://i.pravatar.cc/150?img=33' };
    return { ...demo, provider: providerName, demo: true };
  }
  const { auth, authMod } = await getAuthLazy();
  const provider = providerName === 'google' ? new authMod.GoogleAuthProvider() : new authMod.GithubAuthProvider();
  const res = await authMod.signInWithPopup(auth, provider);
  const u = res.user;
  return {
    name: u.displayName || u.email?.split('@')[0] || 'User',
    email: u.email || `${u.uid}@${providerName}.oauth`,
    avatar: u.photoURL,
    provider: providerName,
  };
}

export const firebaseDbUrl = (cfg.databaseURL || '').replace(/\/$/, '');
