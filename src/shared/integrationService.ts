import { openUrl } from '@tauri-apps/plugin-opener';
import { BACKEND_URL, FLASK_PORT } from './backend';
import { getValidAuthToken } from './authService';

export type IntegrationId =
  | 'filesystem'
  | 'google'
  | 'github'
  | 'notion'
  | 'jira'
  | 'slack'
  | 'perplexity';

export type OAuthProvider = 'google' | 'github' | 'notion' | 'jira' | 'slack';
export type RequiredIntegrationId = 'filesystem' | 'google' | 'github' | 'notion' | 'slack';

export interface JiraAccessibleResource {
  cloud_id: string;
  site_name: string;
  site_url: string;
  avatar_url?: string;
  scopes?: string[];
}

export interface IntegrationConfigurationStatus {
  site_id?: string | null;
  site_name?: string | null;
  site_url?: string | null;
  project_keys?: string[];
  project_count?: number;
  project_names_by_key?: Record<string, string>;
  accessible_resources?: JiraAccessibleResource[];
}

export interface IntegrationStatus {
  id: IntegrationId;
  name: string;
  connected: boolean;
  description: string;
  icon?: string;
  included?: boolean;
  auth_kind?: 'oauth' | 'local' | 'included';
  configurable?: boolean;
  configured?: boolean;
  needs_configuration?: boolean;
  required_onboarding?: boolean;
  configuration?: IntegrationConfigurationStatus | null;
}

export interface JiraProject {
  id: string;
  key: string;
  name: string;
  projectTypeKey?: string;
}

export interface JiraConfigResponse {
  ok: boolean;
  connected: boolean;
  configured: boolean;
  config: {
    cloud_id?: string | null;
    site_name?: string | null;
    site_url?: string | null;
    project_keys: string[];
    project_names_by_key: Record<string, string>;
    accessible_resources: JiraAccessibleResource[];
  };
}

export interface LargeContextIntegrationStatus {
  integration_id: string;
  display_name: string;
  provider_ids: string[];
  connected: boolean;
  enabled: boolean;
  interval_minutes: number;
  status: string;
  last_started_at?: string | null;
  last_completed_at?: string | null;
  last_success_at?: string | null;
  last_error?: string | null;
  next_run_at?: string | null;
}

export interface LargeContextSyncStatusResponse {
  config: {
    enabled: boolean;
    interval_minutes: number;
    projection_mode: string;
    markdown_root: string;
    last_scheduler_heartbeat?: string | null;
  };
  scheduler: {
    running: boolean;
    next_run_at?: string | null;
    last_started_at?: string | null;
    last_completed_at?: string | null;
  };
  integrations: LargeContextIntegrationStatus[];
  providers: Array<Record<string, unknown>>;
  last_run?: Record<string, unknown> | null;
}

export const REQUIRED_INTEGRATION_IDS: RequiredIntegrationId[] = [
  'filesystem',
  'google',
  'github',
  'notion',
  'slack',
];

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';
const GITHUB_CLIENT_ID = import.meta.env.VITE_GITHUB_CLIENT_ID || '';
const NOTION_CLIENT_ID = import.meta.env.VITE_NOTION_CLIENT_ID || '';
const JIRA_CLIENT_ID = import.meta.env.VITE_JIRA_CLIENT_ID || '';
const SLACK_CLIENT_ID = import.meta.env.VITE_SLACK_CLIENT_ID || '';

const GOOGLE_REDIRECT_URI = `http://127.0.0.1:${FLASK_PORT}/integrations/google/callback`;
const GITHUB_REDIRECT_URI = `http://127.0.0.1:${FLASK_PORT}/integrations/github/callback`;
const NOTION_REDIRECT_URI = `http://localhost:${FLASK_PORT}/integrations/notion/callback`;
const JIRA_REDIRECT_URI = `http://127.0.0.1:${FLASK_PORT}/integrations/jira/callback`;
// Slack only allows http://localhost (not 127.0.0.1) for non-https redirect URIs.
const SLACK_REDIRECT_URI = `http://localhost:${FLASK_PORT}/integrations/slack/callback`;

const GOOGLE_SCOPES =
  'openid https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/documents https://www.googleapis.com/auth/userinfo.email';
const GITHUB_SCOPES = 'repo read:user';
const JIRA_SCOPES = 'offline_access read:me read:jira-user read:jira-work write:jira-work';
// Slack user-token scopes — must mirror SLACK_USER_SCOPES on the FastAPI router.
const SLACK_USER_SCOPES =
  'channels:history,channels:read,groups:history,groups:read,mpim:history,mpim:read,im:history,im:read,users:read,team:read';

const PKCE_PROVIDERS: OAuthProvider[] = ['google', 'github'];
const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

function getMissingOAuthConfigError(provider: OAuthProvider): string | null {
  if (provider === 'google' && !GOOGLE_CLIENT_ID) {
    return 'Google OAuth is not configured. Set VITE_GOOGLE_CLIENT_ID and rebuild the app.';
  }
  if (provider === 'github' && !GITHUB_CLIENT_ID) {
    return 'GitHub OAuth is not configured. Set VITE_GITHUB_CLIENT_ID and rebuild the app.';
  }
  if (provider === 'notion' && !NOTION_CLIENT_ID) {
    return 'Notion OAuth is not configured. Set VITE_NOTION_CLIENT_ID and rebuild the app.';
  }
  if (provider === 'jira' && !JIRA_CLIENT_ID) {
    return 'Jira OAuth is not configured. Set VITE_JIRA_CLIENT_ID and rebuild the app.';
  }
  if (provider === 'slack' && !SLACK_CLIENT_ID) {
    return 'Slack OAuth is not configured. Set VITE_SLACK_CLIENT_ID and rebuild the app.';
  }
  return null;
}

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

  if (provider === 'notion') {
    const authUrl = new URL('https://api.notion.com/v1/oauth/authorize');
    authUrl.searchParams.set('client_id', NOTION_CLIENT_ID);
    authUrl.searchParams.set('redirect_uri', NOTION_REDIRECT_URI);
    authUrl.searchParams.set('response_type', 'code');
    authUrl.searchParams.set('state', state);
    authUrl.searchParams.set('owner', 'user');
    return authUrl.toString();
  }

  if (provider === 'slack') {
    // Slack OAuth v2 — request user scopes only so we get a user token (xoxp-).
    // ``scope`` (bot scopes) is intentionally empty.
    const authUrl = new URL('https://slack.com/oauth/v2/authorize');
    authUrl.searchParams.set('client_id', SLACK_CLIENT_ID);
    authUrl.searchParams.set('redirect_uri', SLACK_REDIRECT_URI);
    authUrl.searchParams.set('user_scope', SLACK_USER_SCOPES);
    authUrl.searchParams.set('scope', '');
    authUrl.searchParams.set('state', state);
    return authUrl.toString();
  }

  const authUrl = new URL('https://auth.atlassian.com/authorize');
  authUrl.searchParams.set('audience', 'api.atlassian.com');
  authUrl.searchParams.set('client_id', JIRA_CLIENT_ID);
  authUrl.searchParams.set('scope', JIRA_SCOPES);
  authUrl.searchParams.set('redirect_uri', JIRA_REDIRECT_URI);
  authUrl.searchParams.set('state', state);
  authUrl.searchParams.set('response_type', 'code');
  authUrl.searchParams.set('prompt', 'consent');
  return authUrl.toString();
}

async function startOAuth(
  provider: OAuthProvider,
  state: string,
  codeVerifier: string | null,
  authToken: string,
) {
  const body: Record<string, unknown> = PKCE_PROVIDERS.includes(provider)
    ? { state, code_verifier: codeVerifier, auth_token: authToken }
    : { state, auth_token: authToken };

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

async function pollOAuth(
  provider: OAuthProvider,
  state: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  const started = Date.now();
  while (Date.now() - started <= POLL_TIMEOUT_MS) {
    const response = await fetch(
      `${BACKEND_URL}/integrations/${provider}/check?state=${encodeURIComponent(state)}`,
    );
    const result = await response.json();

    if (result.status === 'ready' || result.status === 'consumed') {
      return { ok: true };
    }
    if (result.status === 'error') {
      return {
        ok: false,
        error: result.error_description || result.error || `${provider} auth failed`,
      };
    }

    await sleep(POLL_INTERVAL_MS);
  }
  return { ok: false, error: `${provider} authentication timed out` };
}

export async function connectOAuthIntegration(
  provider: OAuthProvider,
): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    const configError = getMissingOAuthConfigError(provider);
    if (configError) {
      return { ok: false, error: configError };
    }

    const authToken = await getValidAuthToken();
    if (!authToken) {
      return { ok: false, error: 'Please log in first.' };
    }

    const state = generateRandomString(32);
    let codeVerifier: string | null = null;
    let codeChallenge: string | undefined;
    if (PKCE_PROVIDERS.includes(provider)) {
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

export async function connectFilesystem(
  rootPath: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    const response = await fetch(`${BACKEND_URL}/integrations/filesystem/connect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ root_path: rootPath }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || !result.ok) {
      return {
        ok: false,
        error: result.error || result.detail || 'Failed to connect filesystem',
      };
    }
    return { ok: true };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

export async function disconnectIntegration(provider: string): Promise<boolean> {
  const endpoint = `${BACKEND_URL}/integrations/${provider}/disconnect`;
  try {
    const postResponse = await fetch(endpoint, { method: 'POST' });
    if (postResponse.ok) return true;
    const deleteResponse = await fetch(endpoint, { method: 'DELETE' });
    return deleteResponse.ok;
  } catch {
    return false;
  }
}

export async function fetchJiraConfig(): Promise<JiraConfigResponse> {
  const response = await fetch(`${BACKEND_URL}/integrations/jira/config`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || data.detail || 'Failed to load Jira configuration');
  }
  return data as JiraConfigResponse;
}

export async function listJiraProjects(cloudId: string): Promise<JiraProject[]> {
  const response = await fetch(
    `${BACKEND_URL}/integrations/jira/projects?cloud_id=${encodeURIComponent(cloudId)}`,
  );
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || data.detail || 'Failed to load Jira projects');
  }
  return data.projects || [];
}

export async function updateJiraConfig(
  cloudId: string,
  projectKeys: string[],
): Promise<JiraConfigResponse> {
  const response = await fetch(`${BACKEND_URL}/integrations/jira/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cloud_id: cloudId, project_keys: projectKeys }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || data.detail || 'Failed to update Jira configuration');
  }
  return data as JiraConfigResponse;
}

export async function fetchLargeContextSyncStatus(): Promise<LargeContextSyncStatusResponse> {
  const response = await fetch(`${BACKEND_URL}/integrations/large-context-sync/status`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || data.detail || 'Failed to load large context sync status');
  }
  return data as LargeContextSyncStatusResponse;
}

export async function updateLargeContextIntegrationConfig(
  integrationId: string,
  enabled: boolean,
  intervalMinutes: number,
): Promise<LargeContextIntegrationStatus> {
  const response = await fetch(
    `${BACKEND_URL}/integrations/large-context-sync/integrations/${encodeURIComponent(integrationId)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        enabled,
        interval_minutes: intervalMinutes,
      }),
    },
  );
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || data.detail || 'Failed to update sync settings');
  }
  return data.integration as LargeContextIntegrationStatus;
}

export async function runLargeContextIntegrationSync(
  integrationId: string,
): Promise<{ ok: true } | { ok: false; busy?: boolean; error: string }> {
  const response = await fetch(`${BACKEND_URL}/integrations/large-context-sync/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      mode: 'integrations',
      integration_ids: [integrationId],
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (response.ok) {
    return { ok: true };
  }
  return {
    ok: false,
    busy: response.status === 409,
    error: data.error || data.detail || 'Failed to start large context sync',
  };
}

export function getRequiredIntegrations(
  integrations: IntegrationStatus[],
): Record<RequiredIntegrationId, IntegrationStatus | null> {
  return {
    filesystem: integrations.find((i) => i.id === 'filesystem') ?? null,
    google: integrations.find((i) => i.id === 'google') ?? null,
    github: integrations.find((i) => i.id === 'github') ?? null,
    notion: integrations.find((i) => i.id === 'notion') ?? null,
    slack: integrations.find((i) => i.id === 'slack') ?? null,
  };
}

export function areRequiredIntegrationsConnected(integrations: IntegrationStatus[]): boolean {
  const required = getRequiredIntegrations(integrations);
  return REQUIRED_INTEGRATION_IDS.every((id) => required[id]?.connected === true);
}
