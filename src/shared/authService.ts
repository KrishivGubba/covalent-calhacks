import { openUrl } from '@tauri-apps/plugin-opener';
import { BACKEND_URL, FLASK_PORT } from './backend';

const AUTH0_DOMAIN = 'dev-sb3sx3jnljwod4ab.us.auth0.com';
const AUTH0_AUDIENCE = 'https://dev-sb3sx3jnljwod4ab.us.auth0.com/api/v2/';
const AUTH0_CLIENT_ID = import.meta.env.VITE_AUTH0_CLIENT_ID ?? '';
const REDIRECT_URI = `http://localhost:${FLASK_PORT}/callback`;
const SCOPE = 'openid profile email offline_access';
const AUTH_CHECK_URL = `${BACKEND_URL}/auth/check`;
const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

export const USER_ID_KEY = 'covalent_user_id';
export const ACCESS_TOKEN_KEY = 'auth0_access_token';
export const LEGACY_ACCESS_TOKEN_KEY = 'access_token';

export interface AuthStatus {
  authenticated: boolean;
  user: string | null;
  message: string;
}

type AuthCheckResponse = {
  status: 'pending' | 'ready' | 'error';
  access_token?: string;
  id_token?: string;
  refresh_token?: string;
  user_info?: { email?: string; name?: string; sub?: string; [key: string]: unknown };
  error?: string;
  error_description?: string;
};

function randomString(length: number): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
  const array = new Uint8Array(length);
  crypto.getRandomValues(array);
  return Array.from(array, (b) => chars[b % chars.length]).join('');
}

function base64UrlEncode(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function sha256(plain: string): Promise<ArrayBuffer> {
  const encoder = new TextEncoder();
  return crypto.subtle.digest('SHA-256', encoder.encode(plain));
}

async function buildAuth0AuthorizeUrl(): Promise<string> {
  const state = randomString(32);
  const codeVerifier = randomString(64);
  const codeChallenge = base64UrlEncode(await sha256(codeVerifier));

  sessionStorage.setItem('auth0_state', state);
  sessionStorage.setItem('auth0_code_verifier', codeVerifier);

  const params = new URLSearchParams({
    response_type: 'code',
    client_id: AUTH0_CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    scope: SCOPE,
    audience: AUTH0_AUDIENCE,
    state,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
  });
  return `https://${AUTH0_DOMAIN}/authorize?${params.toString()}`;
}

export function storeAccessToken(token: string) {
  sessionStorage.setItem(ACCESS_TOKEN_KEY, token);
  // Backward-compatible mirror for old code paths.
  sessionStorage.setItem(LEGACY_ACCESS_TOKEN_KEY, token);
}

export function getStoredAccessToken(): string | null {
  return (
    sessionStorage.getItem(ACCESS_TOKEN_KEY) ||
    sessionStorage.getItem(LEGACY_ACCESS_TOKEN_KEY)
  );
}

export async function getValidAuthToken(): Promise<string | null> {
  const direct = getStoredAccessToken();
  if (direct) return direct;

  const userId = localStorage.getItem(USER_ID_KEY);
  if (!userId) return null;

  try {
    const response = await fetch(`${BACKEND_URL}/auth/session?user_id=${encodeURIComponent(userId)}`);
    const data = await response.json();
    const token = data?.session?.access_token as string | undefined;
    if (token) {
      storeAccessToken(token);
      return token;
    }
  } catch {
    // no-op
  }

  return null;
}

export async function loadAuthStatus(): Promise<AuthStatus> {
  try {
    const userId = localStorage.getItem(USER_ID_KEY);
    if (userId) {
      const sessionRes = await fetch(`${BACKEND_URL}/auth/session?user_id=${encodeURIComponent(userId)}`);
      const sessionData = await sessionRes.json();

      if (sessionData.session) {
        const session = sessionData.session;
        if (sessionData.expired) {
          const refreshRes = await fetch(`${BACKEND_URL}/auth/session/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId }),
          });

          if (refreshRes.ok) {
            const refreshData = await refreshRes.json();
            if (refreshData.access_token) {
              storeAccessToken(refreshData.access_token);
            }
            if (session.user_info) {
              sessionStorage.setItem('auth0_user', JSON.stringify(session.user_info));
            }
            const user = session.user_info;
            return {
              authenticated: true,
              user: user?.email || user?.name || 'Authenticated',
              message: 'Session restored',
            };
          }

          localStorage.removeItem(USER_ID_KEY);
          clearAuthStorage();
          return { authenticated: false, user: null, message: 'Session expired. Please log in again.' };
        }

        if (session.access_token) storeAccessToken(session.access_token);
        if (session.id_token) sessionStorage.setItem('auth0_id_token', session.id_token);
        if (session.refresh_token) sessionStorage.setItem('auth0_refresh_token', session.refresh_token);
        if (session.user_info) sessionStorage.setItem('auth0_user', JSON.stringify(session.user_info));

        const user = session.user_info;
        return {
          authenticated: true,
          user: user?.email || user?.name || 'Authenticated',
          message: 'Connected via Auth0',
        };
      }

      localStorage.removeItem(USER_ID_KEY);
    }

    const token = getStoredAccessToken();
    const userJson = sessionStorage.getItem('auth0_user');
    if (token) {
      const user = userJson ? JSON.parse(userJson) : null;
      return {
        authenticated: true,
        user: user?.email || user?.name || 'Authenticated',
        message: 'Connected via Auth0',
      };
    }

    return { authenticated: false, user: null, message: 'Not connected' };
  } catch {
    return { authenticated: false, user: null, message: 'Failed to load auth status' };
  }
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function startAuthLogin(): Promise<{ ok: true; status: AuthStatus } | { ok: false; error: string }> {
  if (!AUTH0_CLIENT_ID) {
    return { ok: false, error: 'Auth0 is not configured. Set VITE_AUTH0_CLIENT_ID in .env.' };
  }

  try {
    const url = await buildAuth0AuthorizeUrl();
    const state = sessionStorage.getItem('auth0_state');
    const codeVerifier = sessionStorage.getItem('auth0_code_verifier');
    if (!state || !codeVerifier) {
      return { ok: false, error: 'Failed to generate auth session. Please try again.' };
    }

    const startRes = await fetch(`${BACKEND_URL}/auth/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state, code_verifier: codeVerifier }),
    });
    if (!startRes.ok) {
      const errData = await startRes.json().catch(() => ({}));
      return { ok: false, error: errData.error || 'Failed to start auth session' };
    }

    await openUrl(url);

    const started = Date.now();
    while (Date.now() - started <= POLL_TIMEOUT_MS) {
      const r = await fetch(`${AUTH_CHECK_URL}?state=${encodeURIComponent(state)}`);
      const data: AuthCheckResponse = await r.json();
      if (data.status === 'ready' && data.access_token) {
        storeAccessToken(data.access_token);
        if (data.id_token) sessionStorage.setItem('auth0_id_token', data.id_token);
        if (data.refresh_token) sessionStorage.setItem('auth0_refresh_token', data.refresh_token);
        if (data.user_info) sessionStorage.setItem('auth0_user', JSON.stringify(data.user_info));
        sessionStorage.removeItem('auth0_state');
        sessionStorage.removeItem('auth0_code_verifier');

        const user = data.user_info;
        if (user?.sub) {
          localStorage.setItem(USER_ID_KEY, user.sub);
        }

        return {
          ok: true,
          status: {
            authenticated: true,
            user: user?.email || user?.name || user?.sub || 'Authenticated',
            message: 'Successfully authenticated',
          },
        };
      }

      if (data.status === 'error') {
        sessionStorage.removeItem('auth0_state');
        sessionStorage.removeItem('auth0_code_verifier');
        return { ok: false, error: data.error_description || data.error || 'Login failed' };
      }

      await sleep(POLL_INTERVAL_MS);
    }

    return { ok: false, error: 'Login timed out. Please try again.' };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

export function clearAuthStorage() {
  localStorage.removeItem(USER_ID_KEY);
  sessionStorage.removeItem(ACCESS_TOKEN_KEY);
  sessionStorage.removeItem(LEGACY_ACCESS_TOKEN_KEY);
  sessionStorage.removeItem('auth0_id_token');
  sessionStorage.removeItem('auth0_refresh_token');
  sessionStorage.removeItem('auth0_user');
  sessionStorage.removeItem('auth0_state');
  sessionStorage.removeItem('auth0_code_verifier');
}

export async function logoutAuth(): Promise<void> {
  const userId = localStorage.getItem(USER_ID_KEY);
  if (userId) {
    try {
      await fetch(`${BACKEND_URL}/auth/logout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId }),
      });
    } catch {
      // no-op
    }
  }
  clearAuthStorage();
}
