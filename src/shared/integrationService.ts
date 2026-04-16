import { openUrl } from '@tauri-apps/plugin-opener';
import { BACKEND_URL, FLASK_PORT } from './backend';
import { getValidAuthToken } from './authService';

export interface IntegrationStatus {
  id: string;
  name: string;
  connected: boolean;
  description: string;
  icon?: string;
  included?: boolean;
}

type OAuthProvider = 'google' | 'github' | 'notion';
export type RequiredIntegrationId = 'filesystem' | 'google' | 'github' | 'notion';
export const REQUIRED_INTEGRATION_IDS: RequiredIntegrationId[] = [
  'filesystem',
  'google',
  'github',
  'notion',
];

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';
const GITHUB_CLIENT_ID = import.meta.env.VITE_GITHUB_CLIENT_ID || '';
const NOTION_CLIENT_ID = import.meta.env.VITE_NOTION_CLIENT_ID || '';

const GOOGLE_REDIRECT_URI = `http://127.0.0.1:${FLASK_PORT}/integrations/google/callback`;
const GITHUB_REDIRECT_URI = `http://127.0.0.1:${FLASK_PORT}/integrations/github/callback`;
const NOTION_REDIRECT_URI = `http://localhost:${FLASK_PORT}/integrations/notion/callback`;

const GOOGLE_SCOPES =
  'openid https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/userinfo.email';
const GITHUB_SCOPES = 'repo read:user';

const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function generateRandomString(length: number): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
  const array = new Uint8Array(length);
  crypto.getRandomValues(array);
  return Array.from(array, (byte) => chars[byte % chars.length]).join('');
}

async function sha256(plain: string): Promise<ArrayBuffer> {
  const encoder = new TextEncoder();
  return crypto.subtle.digest('SHA-256', encoder.encode(plain));
}

function base64UrlEncode(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  bytes.forEach((b) => (binary += String.fromCharCode(b)));
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function generateCodeChallenge(verifier: string): Promise<string> {
  const hashed = await sha256(verifier);
  return base64UrlEncode(hashed);
}

export async function fetchIntegrationsStatus(): Promise<IntegrationStatus[]> {
  const response = await fetch(`${BACKEND_URL}/integrations/status`);
  if (!response.ok) {
    throw new Error(`Failed to fetch integrations: HTTP ${response.status}`);
  }
  const data = await response.json();
  return data.integrations || [];
}

function buildOAuthUrl(provider: OAuthProvider, state: string, codeChallenge?: string): string {
  if (provider === 'google') {
    const authUrl = new URL('https://accounts.google.com/o/oauth2/v2/auth');
    authUrl.searchParams.set('client_id', GOOGLE_CLIENT_ID);
    authUrl.searchParams.set('redirect_uri', GOOGLE_REDIRECT_URI);
    authUrl.searchParams.set('response_type', 'code');
    authUrl.searchParams.set('scope', GOOGLE_SCOPES);
    authUrl.searchParams.set('state', state);
    authUrl.searchParams.set('code_challenge', codeChallenge || '');
    authUrl.searchParams.set('code_challenge_method', 'S256');
    authUrl.searchParams.set('access_type', 'offline');
    authUrl.searchParams.set('prompt', 'consent');
    return authUrl.toString();
  }

  if (provider === 'github') {
    const authUrl = new URL('https://github.com/login/oauth/authorize');
    authUrl.searchParams.set('client_id', GITHUB_CLIENT_ID);
    authUrl.searchParams.set('redirect_uri', GITHUB_REDIRECT_URI);
    authUrl.searchParams.set('scope', GITHUB_SCOPES);
    authUrl.searchParams.set('state', state);
    authUrl.searchParams.set('code_challenge', codeChallenge || '');
    authUrl.searchParams.set('code_challenge_method', 'S256');
    return authUrl.toString();
  }

  const authUrl = new URL('https://api.notion.com/v1/oauth/authorize');
  authUrl.searchParams.set('client_id', NOTION_CLIENT_ID);
  authUrl.searchParams.set('redirect_uri', NOTION_REDIRECT_URI);
  authUrl.searchParams.set('response_type', 'code');
  authUrl.searchParams.set('state', state);
  authUrl.searchParams.set('owner', 'user');
  return authUrl.toString();
}

async function startOAuth(provider: OAuthProvider, state: string, codeVerifier: string | null, authToken: string) {
  let body: Record<string, unknown> = { state, auth_token: authToken };
  if (provider === 'google' || provider === 'github') {
    body = { ...body, code_verifier: codeVerifier };
  }

  const response = await fetch(`${BACKEND_URL}/integrations/${provider}/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || data.detail || `Failed to start ${provider} OAuth`);
  }
}

async function pollOAuth(provider: OAuthProvider, state: string): Promise<{ ok: true } | { ok: false; error: string }> {
  const started = Date.now();
  while (Date.now() - started <= POLL_TIMEOUT_MS) {
    const response = await fetch(`${BACKEND_URL}/integrations/${provider}/check?state=${encodeURIComponent(state)}`);
    const result = await response.json();

    if (result.status === 'ready' || result.status === 'consumed') {
      return { ok: true };
    }
    if (result.status === 'error') {
      return { ok: false, error: result.error_description || result.error || `${provider} auth failed` };
    }

    await sleep(POLL_INTERVAL_MS);
  }
  return { ok: false, error: `${provider} authentication timed out` };
}

export async function connectOAuthIntegration(provider: OAuthProvider): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    const authToken = await getValidAuthToken();
    if (!authToken) {
      return { ok: false, error: 'Please log in first.' };
    }

    const state = generateRandomString(32);
    let codeVerifier: string | null = null;
    let codeChallenge: string | undefined = undefined;
    if (provider === 'google' || provider === 'github') {
      codeVerifier = generateRandomString(64);
      codeChallenge = await generateCodeChallenge(codeVerifier);
    }

    await startOAuth(provider, state, codeVerifier, authToken);
    const oauthUrl = buildOAuthUrl(provider, state, codeChallenge);
    await openUrl(oauthUrl);

    return await pollOAuth(provider, state);
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

export async function connectFilesystem(rootPath: string): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    const response = await fetch(`${BACKEND_URL}/integrations/filesystem/connect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ root_path: rootPath }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || !result.ok) {
      return { ok: false, error: result.error || result.detail || 'Failed to connect filesystem' };
    }
    return { ok: true };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

export async function disconnectIntegration(provider: string): Promise<boolean> {
  const endpoint = `${BACKEND_URL}/integrations/${provider}/disconnect`;
  try {
    // Most routes are POST; google/filesystem support POST and DELETE in backend for compatibility.
    const postResponse = await fetch(endpoint, { method: 'POST' });
    if (postResponse.ok) return true;
    const deleteResponse = await fetch(endpoint, { method: 'DELETE' });
    return deleteResponse.ok;
  } catch {
    return false;
  }
}

export function getRequiredIntegrations(
  integrations: IntegrationStatus[],
): Record<RequiredIntegrationId, IntegrationStatus | null> {
  return {
    filesystem: integrations.find((i) => i.id === 'filesystem') ?? null,
    google: integrations.find((i) => i.id === 'google') ?? null,
    github: integrations.find((i) => i.id === 'github') ?? null,
    notion: integrations.find((i) => i.id === 'notion') ?? null,
  };
}

export function areRequiredIntegrationsConnected(integrations: IntegrationStatus[]): boolean {
  const required = getRequiredIntegrations(integrations);
  return REQUIRED_INTEGRATION_IDS.every((id) => required[id]?.connected === true);
}
