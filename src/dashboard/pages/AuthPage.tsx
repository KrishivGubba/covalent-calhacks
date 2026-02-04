import React, { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';
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
const SCOPE = 'openid profile email';
const AUTH0_CLIENT_ID = import.meta.env.VITE_AUTH0_CLIENT_ID ?? '';

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

const AuthPage: React.FC = () => {
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadAuthStatus();
  }, []);

  const loadAuthStatus = async () => {
    try {
      const status = await invoke<AuthStatus>('get_auth_status');
      setAuthStatus(status);
    } catch (error) {
      console.error('Failed to load auth status:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async () => {
    if (!AUTH0_CLIENT_ID) {
      alert('Auth0 is not configured. Set VITE_AUTH0_CLIENT_ID in .env.');
      return;
    }
    try {
      const url = await buildAuth0AuthorizeUrl();
      await openUrl(url);
    } catch (error) {
      console.error('Failed to open auth URL:', error);
      alert('Could not open login page. Check the console.');
    }
  };

  const handleLogout = () => {
    console.log('Logout clicked');
    alert('Logout under construction');
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

          {authStatus?.message && (
            <div style={styles.messageBox}>
              Under Construction
            </div>
          )}
        </div>

        <div style={styles.actions}>
          {!authStatus?.authenticated ? (
            <button style={styles.primaryButton} onClick={handleLogin}>
              Connect Account
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
