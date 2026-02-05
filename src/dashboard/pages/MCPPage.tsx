import React, { useState, useEffect, useRef } from 'react';
import { openUrl } from '@tauri-apps/plugin-opener';

const BACKEND_URL = 'http://localhost:5001';

// Google OAuth config (must match backend)
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';
const GOOGLE_REDIRECT_URI = 'http://127.0.0.1:5001/integrations/google/callback';
const GOOGLE_SCOPES = 'openid https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/userinfo.email';

// GitHub OAuth config (must match backend)
const GITHUB_CLIENT_ID = import.meta.env.VITE_GITHUB_CLIENT_ID || '';
const GITHUB_REDIRECT_URI = 'http://127.0.0.1:5001/integrations/github/callback';
const GITHUB_SCOPES = 'repo read:user'; // repo = full repo access, read:user = profile

// PKCE utilities
function generateRandomString(length: number): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
  const array = new Uint8Array(length);
  crypto.getRandomValues(array);
  return Array.from(array, (byte) => chars[byte % chars.length]).join('');
}

async function sha256(plain: string): Promise<ArrayBuffer> {
  const encoder = new TextEncoder();
  const data = encoder.encode(plain);
  return crypto.subtle.digest('SHA-256', data);
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

interface MCPIntegration {
  id: string;
  name: string;
  connected: boolean;
  description: string;
  icon?: string;
  included?: boolean;
}

interface MCPPageProps {
  isAuthenticated: boolean;
}

const MCPPage: React.FC<MCPPageProps> = ({ isAuthenticated }) => {
  const [integrations, setIntegrations] = useState<MCPIntegration[]>([]);
  const [loading, setLoading] = useState(true);
  const [connectingId, setConnectingId] = useState<string | null>(null);
  const pollIntervalRef = useRef<number | null>(null);

  useEffect(() => {
    loadIntegrations();
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  const loadIntegrations = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${BACKEND_URL}/integrations/status`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      setIntegrations(data.integrations || []);
    } catch (error) {
      console.error('Failed to load MCP integrations:', error);
      // Fallback to default list on error
      setIntegrations([
        { id: 'filesystem', name: 'Filesystem', description: 'Access local files and directories', connected: false, icon: '📁' },
        { id: 'github', name: 'GitHub', description: 'Access repositories, issues, and pull requests', connected: false, icon: '🐙' },
        { id: 'perplexity', name: 'Perplexity Search', description: 'AI-powered web search', connected: true, icon: '🔍', included: true },
        { id: 'notion', name: 'Notion', description: 'Access Notion workspaces and pages', connected: false, icon: '📝' },
        { id: 'google', name: 'Google Workspace', description: 'Calendar, Drive, Mail', connected: false, icon: '🔷' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleConnectGoogle = async () => {
    console.log('handleConnectGoogle called');
    setConnectingId('google');
    
    try {
      // Get Auth0 access token (required for Lambda call)
      let authToken = sessionStorage.getItem('access_token');
      console.log('Auth token in sessionStorage:', !!authToken);
      
      // If not in sessionStorage, try to get from backend session
      if (!authToken) {
        const userId = localStorage.getItem('covalent_user_id');
        if (userId) {
          console.log('Fetching token from backend session...');
          try {
            const sessionResponse = await fetch(`${BACKEND_URL}/auth/session?user_id=${encodeURIComponent(userId)}`);
            const sessionData = await sessionResponse.json();
            if (sessionData.session?.access_token) {
              authToken = sessionData.session.access_token as string;
              // Restore to sessionStorage for future use
              sessionStorage.setItem('access_token', authToken);
              console.log('Token restored from backend session');
            }
          } catch (err) {
            console.error('Failed to fetch session:', err);
          }
        }
      }
      
      if (!authToken) {
        alert('Please log in again to connect Google (session expired)');
        setConnectingId(null);
        return;
      }
      
      // Generate PKCE values
      const codeVerifier = generateRandomString(64);
      const codeChallenge = await generateCodeChallenge(codeVerifier);
      const state = generateRandomString(32);
      
      // Tell backend to store the code_verifier and auth token
      const startResponse = await fetch(`${BACKEND_URL}/integrations/google/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state, code_verifier: codeVerifier, auth_token: authToken }),
      });
      
      if (!startResponse.ok) {
        const errorData = await startResponse.json().catch(() => ({}));
        console.error('Start response error:', errorData);
        throw new Error(errorData.error || 'Failed to start Google auth');
      }
      
      console.log('Google auth start successful, building OAuth URL');
      
      // Build Google OAuth URL
      const authUrl = new URL('https://accounts.google.com/o/oauth2/v2/auth');
      authUrl.searchParams.set('client_id', GOOGLE_CLIENT_ID);
      authUrl.searchParams.set('redirect_uri', GOOGLE_REDIRECT_URI);
      authUrl.searchParams.set('response_type', 'code');
      authUrl.searchParams.set('scope', GOOGLE_SCOPES);
      authUrl.searchParams.set('state', state);
      authUrl.searchParams.set('code_challenge', codeChallenge);
      authUrl.searchParams.set('code_challenge_method', 'S256');
      authUrl.searchParams.set('access_type', 'offline'); // Get refresh token
      authUrl.searchParams.set('prompt', 'consent'); // Force consent to get refresh token
      
      // Open in default browser
      console.log('Opening Google OAuth URL:', authUrl.toString());
      try {
        await openUrl(authUrl.toString());
        console.log('openUrl completed successfully');
      } catch (openError) {
        console.error('openUrl failed:', openError);
        // Fallback to window.open
        window.open(authUrl.toString(), '_blank');
      }
      
      // Poll for completion
      pollIntervalRef.current = window.setInterval(async () => {
        try {
          const checkResponse = await fetch(`${BACKEND_URL}/integrations/google/check?state=${state}`);
          const result = await checkResponse.json();
          
          if (result.status === 'ready') {
            clearInterval(pollIntervalRef.current!);
            pollIntervalRef.current = null;
            setConnectingId(null);
            console.log('Google connected:', result.email);
            loadIntegrations(); // Refresh the list
          } else if (result.status === 'error') {
            clearInterval(pollIntervalRef.current!);
            pollIntervalRef.current = null;
            setConnectingId(null);
            console.error('Google auth error:', result.error, result.error_description);
            alert(`Google auth failed: ${result.error_description || result.error}`);
          }
          // status === 'pending' -> keep polling
        } catch (err) {
          console.error('Error polling Google auth status:', err);
        }
      }, 1500);
      
      // Stop polling after 5 minutes
      setTimeout(() => {
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
          setConnectingId(null);
        }
      }, 5 * 60 * 1000);
      
    } catch (error) {
      console.error('Failed to connect Google:', error);
      setConnectingId(null);
      alert('Failed to start Google authentication');
    }
  };

  const handleConnectGithub = async () => {
    console.log('handleConnectGithub called');
    setConnectingId('github');
    
    try {
      // Get Auth0 access token (required for Lambda call)
      let authToken = sessionStorage.getItem('access_token');
      console.log('Auth token in sessionStorage:', !!authToken);
      
      // If not in sessionStorage, try to get from backend session
      if (!authToken) {
        const userId = localStorage.getItem('covalent_user_id');
        if (userId) {
          console.log('Fetching token from backend session...');
          try {
            const sessionResponse = await fetch(`${BACKEND_URL}/auth/session?user_id=${encodeURIComponent(userId)}`);
            const sessionData = await sessionResponse.json();
            if (sessionData.session?.access_token) {
              authToken = sessionData.session.access_token as string;
              // Restore to sessionStorage for future use
              sessionStorage.setItem('access_token', authToken);
              console.log('Token restored from backend session');
            }
          } catch (err) {
            console.error('Failed to fetch session:', err);
          }
        }
      }
      
      if (!authToken) {
        alert('Please log in again to connect GitHub (session expired)');
        setConnectingId(null);
        return;
      }
      
      // Generate PKCE values
      const codeVerifier = generateRandomString(64);
      const codeChallenge = await generateCodeChallenge(codeVerifier);
      const state = generateRandomString(32);
      
      // Tell backend to store the code_verifier and auth token
      const startResponse = await fetch(`${BACKEND_URL}/integrations/github/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state, code_verifier: codeVerifier, auth_token: authToken }),
      });
      
      if (!startResponse.ok) {
        const errorData = await startResponse.json().catch(() => ({}));
        console.error('Start response error:', errorData);
        throw new Error(errorData.error || 'Failed to start GitHub auth');
      }
      
      console.log('GitHub auth start successful, building OAuth URL');
      
      // Build GitHub OAuth URL with PKCE
      const authUrl = new URL('https://github.com/login/oauth/authorize');
      authUrl.searchParams.set('client_id', GITHUB_CLIENT_ID);
      authUrl.searchParams.set('redirect_uri', GITHUB_REDIRECT_URI);
      authUrl.searchParams.set('scope', GITHUB_SCOPES);
      authUrl.searchParams.set('state', state);
      authUrl.searchParams.set('code_challenge', codeChallenge);
      authUrl.searchParams.set('code_challenge_method', 'S256');
      
      // Open in default browser
      console.log('Opening GitHub OAuth URL:', authUrl.toString());
      try {
        await openUrl(authUrl.toString());
        console.log('openUrl completed successfully');
      } catch (openError) {
        console.error('openUrl failed:', openError);
        // Fallback to window.open
        window.open(authUrl.toString(), '_blank');
      }
      
      // Poll for completion
      pollIntervalRef.current = window.setInterval(async () => {
        try {
          const checkResponse = await fetch(`${BACKEND_URL}/integrations/github/check?state=${state}`);
          const result = await checkResponse.json();
          
          if (result.status === 'ready') {
            clearInterval(pollIntervalRef.current!);
            pollIntervalRef.current = null;
            setConnectingId(null);
            console.log('GitHub connected:', result.username);
            loadIntegrations(); // Refresh the list
          } else if (result.status === 'error') {
            clearInterval(pollIntervalRef.current!);
            pollIntervalRef.current = null;
            setConnectingId(null);
            console.error('GitHub auth error:', result.error, result.error_description);
            alert(`GitHub auth failed: ${result.error_description || result.error}`);
          }
          // status === 'pending' -> keep polling
        } catch (err) {
          console.error('Error polling GitHub auth status:', err);
        }
      }, 1500);
      
      // Stop polling after 5 minutes
      setTimeout(() => {
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
          setConnectingId(null);
        }
      }, 5 * 60 * 1000);
      
    } catch (error) {
      console.error('Failed to connect GitHub:', error);
      setConnectingId(null);
      alert('Failed to start GitHub authentication');
    }
  };

  const handleConnect = async (id: string) => {
    console.log(`handleConnect called with id: ${id}, isAuthenticated: ${isAuthenticated}`);
    if (id === 'google') {
      await handleConnectGoogle();
    } else if (id === 'github') {
      await handleConnectGithub();
    } else {
      console.log(`Connecting to ${id}`);
      alert(`${id} integration coming soon`);
    }
  };

  const handleDisconnect = async (id: string) => {
    if (id === 'google') {
      try {
        const response = await fetch(`${BACKEND_URL}/integrations/google/disconnect`, {
          method: 'POST',
        });
        if (response.ok) {
          console.log('Google disconnected');
          loadIntegrations();
        } else {
          alert('Failed to disconnect Google');
        }
      } catch (error) {
        console.error('Failed to disconnect Google:', error);
        alert('Failed to disconnect Google');
      }
    } else if (id === 'github') {
      try {
        const response = await fetch(`${BACKEND_URL}/integrations/github/disconnect`, {
          method: 'POST',
        });
        if (response.ok) {
          console.log('GitHub disconnected');
          loadIntegrations();
        } else {
          alert('Failed to disconnect GitHub');
        }
      } catch (error) {
        console.error('Failed to disconnect GitHub:', error);
        alert('Failed to disconnect GitHub');
      }
    } else {
      console.log(`Disconnecting from ${id}`);
      alert(`Disconnect for ${id} coming soon`);
    }
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
        <h1 style={styles.title}>Integrations</h1>
        <p style={styles.subtitle}>
          Connect external services and tools
        </p>
      </div>

      {!isAuthenticated && (
        <div style={styles.loginPrompt}>
          Please log in on the Profile page to manage integrations.
        </div>
      )}

      <div style={styles.grid}>
        {integrations.map((integration) => (
          <div key={integration.id} style={styles.card}>
            <div style={styles.cardHeader}>
              <div style={styles.cardTitleRow}>
                <h3 style={styles.cardTitle}>
                  {integration.icon && <span style={styles.icon}>{integration.icon}</span>}
                  {integration.name}
                </h3>
                <div
                  style={{
                    ...styles.statusBadge,
                    ...(integration.connected
                      ? styles.statusBadgeConnected
                      : styles.statusBadgeDisconnected),
                  }}
                >
                  <div style={{
                    ...styles.statusDot,
                    backgroundColor: integration.connected ? '#10B981' : '#6B7280'
                  }}></div>
                  {integration.connected ? 'Connected' : 'Not Connected'}
                </div>
              </div>
              <p style={styles.cardDescription}>{integration.description}</p>
            </div>

            <div style={styles.cardActions}>
              {integration.included ? (
                <div style={styles.includedBadge}>
                  Included
                </div>
              ) : !integration.connected ? (
                <button
                  style={{
                    ...styles.connectButton,
                    ...(!isAuthenticated || connectingId === integration.id ? styles.buttonDisabled : {}),
                  }}
                  onClick={() => handleConnect(integration.id)}
                  disabled={!isAuthenticated || connectingId === integration.id}
                  title={!isAuthenticated ? 'Please log in first' : undefined}
                >
                  {connectingId === integration.id ? 'Connecting...' : 'Connect'}
                </button>
              ) : (
                <button
                  style={{
                    ...styles.disconnectButton,
                    ...(isAuthenticated ? {} : styles.buttonDisabled),
                  }}
                  onClick={() => handleDisconnect(integration.id)}
                  disabled={!isAuthenticated}
                  title={isAuthenticated ? undefined : 'Please log in first'}
                >
                  Disconnect
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <div style={styles.constructionNote}>
        Under Construction
      </div>
    </div>
  );
};

const styles = {
  container: {
    padding: '40px',
    maxWidth: '1000px',
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
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
    gap: '16px',
    marginBottom: '32px',
  },
  card: {
    backgroundColor: '#141414',
    borderRadius: '12px',
    padding: '20px',
    border: '1px solid #27272a',
    display: 'flex',
    flexDirection: 'column' as const,
    justifyContent: 'space-between',
    minHeight: '160px',
  },
  cardHeader: {
    marginBottom: '16px',
  },
  cardTitleRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '12px',
  },
  cardTitle: {
    fontSize: '1.05rem',
    fontWeight: '600',
    color: '#ffffff',
    margin: 0,
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  icon: {
    fontSize: '1.2rem',
  },
  statusBadge: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '4px 10px',
    borderRadius: '12px',
    fontSize: '0.7rem',
    fontWeight: '500',
  },
  statusBadgeConnected: {
    backgroundColor: 'rgba(197, 244, 103, 0.1)',
    color: '#C5F467',
    border: '1px solid rgba(197, 244, 103, 0.3)',
  },
  statusBadgeDisconnected: {
    backgroundColor: '#1a1a1a',
    color: '#71717a',
    border: '1px solid #27272a',
  },
  statusDot: {
    width: '6px',
    height: '6px',
    borderRadius: '50%',
  },
  cardDescription: {
    fontSize: '0.85rem',
    color: '#a1a1aa',
    margin: 0,
    lineHeight: '1.5',
  },
  cardActions: {
    display: 'flex',
    gap: '8px',
  },
  connectButton: {
    flex: 1,
    padding: '10px 18px',
    backgroundColor: '#C5F467',
    border: 'none',
    borderRadius: '8px',
    color: '#0a0a0a',
    fontSize: '0.85rem',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  disconnectButton: {
    flex: 1,
    padding: '10px 18px',
    backgroundColor: 'transparent',
    border: '1px solid #27272a',
    borderRadius: '8px',
    color: '#a1a1aa',
    fontSize: '0.85rem',
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  buttonDisabled: {
    opacity: 0.5,
    cursor: 'not-allowed',
  },
  includedBadge: {
    flex: 1,
    padding: '10px 18px',
    backgroundColor: 'rgba(197, 244, 103, 0.1)',
    border: '1px solid rgba(197, 244, 103, 0.3)',
    borderRadius: '8px',
    color: '#C5F467',
    fontSize: '0.85rem',
    fontWeight: '500',
    textAlign: 'center' as const,
  },
  loadingText: {
    color: '#a1a1aa',
    fontSize: '0.95rem',
  },
  constructionNote: {
    backgroundColor: 'rgba(197, 244, 103, 0.08)',
    border: '1px solid rgba(197, 244, 103, 0.2)',
    borderRadius: '8px',
    padding: '12px 16px',
    color: '#a1a1aa',
    fontSize: '0.85rem',
    textAlign: 'center' as const,
  },
  loginPrompt: {
    backgroundColor: 'rgba(251, 191, 36, 0.1)',
    border: '1px solid rgba(251, 191, 36, 0.3)',
    borderRadius: '8px',
    padding: '12px 16px',
    color: '#fbbf24',
    fontSize: '0.9rem',
    marginBottom: '24px',
    textAlign: 'center' as const,
  },
};

export default MCPPage;
