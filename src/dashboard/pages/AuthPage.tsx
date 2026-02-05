import React, { useState, useEffect } from 'react';
import { openUrl } from '@tauri-apps/plugin-opener';

interface AuthStatus {
  authenticated: boolean;
  user: string | null;
  message: string;
}

// Auth0 PKCE config (for opening login in browser)
const AUTH0_DOMAIN = 'dev-sb3sx3jnljwod4ab.us.auth0.com';
const AUTH0_AUDIENCE = 'https://dev-sb3sx3jnljwod4ab.us.auth0.com/api/v2/';
const REDIRECT_URI = 'http://localhost:5001/callback';
const SCOPE = 'openid profile email offline_access';
const AUTH0_CLIENT_ID = import.meta.env.VITE_AUTH0_CLIENT_ID ?? '';

const AUTH_CHECK_URL = 'http://localhost:5001/auth/check';
const SERVER_BASE = 'http://localhost:5001';
const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

// localStorage key for persistent user_id
const USER_ID_KEY = 'covalent_user_id';

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
  const data = encoder.encode(plain);
  return await crypto.subtle.digest('SHA-256', data);
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

type AuthCheckResponse = {
  status: 'pending' | 'ready' | 'error';
  access_token?: string;
  id_token?: string;
  refresh_token?: string;
  user_info?: { email?: string; name?: string; sub?: string; [key: string]: unknown };
  error?: string;
  error_description?: string;
};

interface AuthPageProps {
  onAuthChange: (authenticated: boolean) => void;
}

const AuthPage: React.FC<AuthPageProps> = ({ onAuthChange }) => {
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    loadAuthStatus();
  }, []);

  const loadAuthStatus = async () => {
    try {
      // First check localStorage for persistent user_id
      const userId = localStorage.getItem(USER_ID_KEY);
      
      if (userId) {
        console.log('[AuthPage] Found saved user_id, checking backend session...');
        
        // Check backend for persistent session
        const sessionRes = await fetch(`${SERVER_BASE}/auth/session?user_id=${encodeURIComponent(userId)}`);
        const sessionData = await sessionRes.json();
        
        if (sessionData.session) {
          const session = sessionData.session;
          
          // Check if token is expired
          if (sessionData.expired) {
            console.log('[AuthPage] Session expired, attempting refresh...');
            
            // Try to refresh the token
            const refreshRes = await fetch(`${SERVER_BASE}/auth/session/refresh`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ user_id: userId }),
            });
            
            if (refreshRes.ok) {
              const refreshData = await refreshRes.json();
              console.log('[AuthPage] Token refreshed successfully');
              
              // Update sessionStorage with new token
              sessionStorage.setItem('auth0_access_token', refreshData.access_token);
              if (session.user_info) {
                sessionStorage.setItem('auth0_user', JSON.stringify(session.user_info));
              }
              
              const user = session.user_info;
              setAuthStatus({
                authenticated: true,
                user: user?.email || user?.name || 'Authenticated',
                message: 'Session restored',
              });
              onAuthChange(true);
              return;
            } else {
              // Refresh failed - clear everything and require re-login
              console.log('[AuthPage] Token refresh failed, clearing session');
              localStorage.removeItem(USER_ID_KEY);
              sessionStorage.clear();
              setAuthStatus({ authenticated: false, user: null, message: 'Session expired. Please log in again.' });
              onAuthChange(false);
              return;
            }
          }
          
          // Session is valid and not expired
          console.log('[AuthPage] Valid session found');
          sessionStorage.setItem('auth0_access_token', session.access_token);
          if (session.id_token) sessionStorage.setItem('auth0_id_token', session.id_token);
          if (session.refresh_token) sessionStorage.setItem('auth0_refresh_token', session.refresh_token);
          if (session.user_info) sessionStorage.setItem('auth0_user', JSON.stringify(session.user_info));
          
          const user = session.user_info;
          setAuthStatus({
            authenticated: true,
            user: user?.email || user?.name || 'Authenticated',
            message: 'Connected via Auth0',
          });
          onAuthChange(true);
          return;
        } else {
          // No session found in backend - clear stale localStorage
          console.log('[AuthPage] No backend session found, clearing localStorage');
          localStorage.removeItem(USER_ID_KEY);
          onAuthChange(false);
        }
      }
      
      // Fallback: check sessionStorage (for current session tokens)
      const token = sessionStorage.getItem('auth0_access_token');
      const userJson = sessionStorage.getItem('auth0_user');
      if (token) {
        const user = userJson ? JSON.parse(userJson) : null;
        setAuthStatus({
          authenticated: true,
          user: user?.email || user?.name || 'Authenticated',
          message: 'Connected via Auth0',
        });
        onAuthChange(true);
      } else {
        // No auth found
        setAuthStatus({ authenticated: false, user: null, message: 'Not connected' });
        onAuthChange(false);
      }
    } catch (error) {
      console.error('Failed to load auth status:', error);
      setAuthStatus({ authenticated: false, user: null, message: 'Failed to load auth status' });
      onAuthChange(false);
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async () => {
    if (!AUTH0_CLIENT_ID) {
      alert('Auth0 is not configured. Set VITE_AUTH0_CLIENT_ID in .env.');
      return;
    }
    setAuthError(null);
    try {
      // Build Auth0 URL (also stores state + code_verifier in sessionStorage)
      const url = await buildAuth0AuthorizeUrl();
      const state = sessionStorage.getItem('auth0_state');
      const codeVerifier = sessionStorage.getItem('auth0_code_verifier');
      if (!state || !codeVerifier) {
        setAuthError('Failed to generate auth session. Please try again.');
        return;
      }

      // Send code_verifier to backend so it can do the token exchange
      const startRes = await fetch(`${SERVER_BASE}/auth/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state, code_verifier: codeVerifier }),
      });
      if (!startRes.ok) {
        const errData = await startRes.json().catch(() => ({}));
        setAuthError(errData.error || 'Failed to start auth session');
        return;
      }

      // Open Auth0 login in browser
      await openUrl(url);
      setPolling(true);

      const started = Date.now();
      const poll = async (): Promise<void> => {
        if (Date.now() - started > POLL_TIMEOUT_MS) {
          setPolling(false);
          setAuthError('Login timed out. Please try again.');
          return;
        }
        try {
          const r = await fetch(`${AUTH_CHECK_URL}?state=${encodeURIComponent(state)}`);
          const data: AuthCheckResponse = await r.json();

          if (data.status === 'ready' && data.access_token) {
            setPolling(false);
            // Store tokens received from backend
            sessionStorage.setItem('auth0_access_token', data.access_token);
            if (data.id_token) sessionStorage.setItem('auth0_id_token', data.id_token);
            if (data.refresh_token) sessionStorage.setItem('auth0_refresh_token', data.refresh_token);
            if (data.user_info) sessionStorage.setItem('auth0_user', JSON.stringify(data.user_info));
            sessionStorage.removeItem('auth0_state');
            sessionStorage.removeItem('auth0_code_verifier');

            // Save user_id to localStorage for persistent sessions
            const user = data.user_info;
            if (user?.sub) {
              localStorage.setItem(USER_ID_KEY, user.sub);
              console.log('[AuthPage] Saved user_id to localStorage:', user.sub);
            }

            setAuthStatus({
              authenticated: true,
              user: user?.email || user?.name || user?.sub || 'Authenticated',
              message: 'Successfully authenticated',
            });
            onAuthChange(true);
            return;
          }
          if (data.status === 'error') {
            setPolling(false);
            setAuthError(data.error_description || data.error || 'Login failed');
            sessionStorage.removeItem('auth0_state');
            sessionStorage.removeItem('auth0_code_verifier');
            return;
          }
        } catch (e) {
          console.error('Auth poll error:', e);
        }
        setTimeout(poll, POLL_INTERVAL_MS);
      };
      setTimeout(poll, POLL_INTERVAL_MS);
    } catch (error) {
      console.error('Failed to open auth URL:', error);
      alert('Could not open login page. Check the console.');
    }
  };

  const handleLogout = async () => {
    // Call backend to delete the persistent session
    const userId = localStorage.getItem(USER_ID_KEY);
    if (userId) {
      try {
        await fetch(`${SERVER_BASE}/auth/logout`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: userId }),
        });
        console.log('[AuthPage] Backend session deleted');
      } catch (error) {
        console.error('[AuthPage] Failed to delete backend session:', error);
      }
    }

    // Clear localStorage (persistent user_id)
    localStorage.removeItem(USER_ID_KEY);

    // Clear sessionStorage (current session tokens)
    sessionStorage.removeItem('auth0_access_token');
    sessionStorage.removeItem('auth0_id_token');
    sessionStorage.removeItem('auth0_refresh_token');
    sessionStorage.removeItem('auth0_user');
    sessionStorage.removeItem('auth0_state');
    sessionStorage.removeItem('auth0_code_verifier');

    setAuthStatus({ authenticated: false, user: null, message: 'Logged out' });
    onAuthChange(false);
    setAuthError(null);
  };

  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.loadingText}>Loading...</div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h1 style={styles.title}>Profile</h1>
        <p style={styles.subtitle}>Manage your Covalent account</p>
      </div>

      <div style={styles.card}>
        <div style={styles.statusSection}>
          <div style={styles.statusHeader}>
            <div style={{
              ...styles.statusDot,
              backgroundColor: authStatus?.authenticated ? '#10B981' : '#6B7280'
            }}></div>
            <span style={styles.statusText}>
              {authStatus?.authenticated ? 'Connected' : 'Not Connected'}
            </span>
          </div>

          {authStatus?.user && (
            <div style={styles.userInfo}>
              <span style={styles.userLabel}>Account:</span>
              <span style={styles.userName}>{authStatus.user}</span>
            </div>
          )}

          {authError && (
            <div style={styles.errorBox}>{authError}</div>
          )}

          {polling && (
            <div style={styles.messageBox}>Waiting for you to sign in… You can close this after logging in in the browser.</div>
          )}

          {authStatus?.message && !authError && !polling && (
            <div style={styles.messageBox}>{authStatus.message}</div>
          )}
        </div>

        <div style={styles.actions}>
          {!authStatus?.authenticated ? (
            <button style={styles.primaryButton} onClick={handleLogin} disabled={polling}>
              {polling ? 'Signing in…' : 'Connect Account'}
            </button>
          ) : (
            <button style={styles.secondaryButton} onClick={handleLogout}>
              Disconnect
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

const styles = {
  container: {
    padding: '40px',
    maxWidth: '800px',
  },
  header: {
    marginBottom: '32px',
  },
  title: {
    fontSize: '1.75rem',
    fontWeight: '600',
    color: '#ffffff',
    margin: '0 0 8px 0',
    letterSpacing: '-0.02em',
  },
  subtitle: {
    fontSize: '0.95rem',
    color: '#a1a1aa',
    margin: 0,
  },
  card: {
    backgroundColor: '#141414',
    borderRadius: '12px',
    padding: '28px',
    border: '1px solid #27272a',
    marginBottom: '24px',
  },
  statusSection: {
    marginBottom: '28px',
  },
  statusHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    marginBottom: '16px',
  },
  statusDot: {
    width: '10px',
    height: '10px',
    borderRadius: '50%',
  },
  statusText: {
    fontSize: '1.05rem',
    fontWeight: '500',
    color: '#ffffff',
  },
  userInfo: {
    display: 'flex',
    gap: '8px',
    marginBottom: '12px',
  },
  userLabel: {
    color: '#a1a1aa',
    fontSize: '0.9rem',
  },
  userName: {
    color: '#ffffff',
    fontWeight: '500',
    fontSize: '0.9rem',
  },
  messageBox: {
    backgroundColor: 'rgba(197, 244, 103, 0.08)',
    border: '1px solid rgba(197, 244, 103, 0.2)',
    borderRadius: '8px',
    padding: '12px 16px',
    color: '#a1a1aa',
    fontSize: '0.85rem',
  },
  errorBox: {
    backgroundColor: 'rgba(239, 68, 68, 0.08)',
    border: '1px solid rgba(239, 68, 68, 0.3)',
    borderRadius: '8px',
    padding: '12px 16px',
    color: '#ef4444',
    fontSize: '0.85rem',
    marginBottom: '12px',
  },
  actions: {
    display: 'flex',
    gap: '12px',
  },
  primaryButton: {
    padding: '12px 24px',
    backgroundColor: '#C5F467',
    border: 'none',
    borderRadius: '8px',
    color: '#0a0a0a',
    fontSize: '0.9rem',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  secondaryButton: {
    padding: '12px 24px',
    backgroundColor: 'transparent',
    border: '1px solid #27272a',
    borderRadius: '8px',
    color: '#ffffff',
    fontSize: '0.9rem',
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  loadingText: {
    color: '#a1a1aa',
    fontSize: '0.95rem',
  },
};

export default AuthPage;
