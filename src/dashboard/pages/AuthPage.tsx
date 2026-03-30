import React, { useEffect, useState } from 'react';
import { getVersion } from '@tauri-apps/api/app';
import {
  loadAuthStatus,
  logoutAuth,
  startAuthLogin,
  type AuthStatus,
} from '../../shared/authService';

interface AuthPageProps {
  onAuthChange: (authenticated: boolean) => void;
}

const AuthPage: React.FC<AuthPageProps> = ({ onAuthChange }) => {
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [appVersion, setAppVersion] = useState<string>('');

  useEffect(() => {
    void hydrate();
    getVersion().then(setAppVersion).catch(() => setAppVersion(''));
  }, []);

  const hydrate = async () => {
    setLoading(true);
    try {
      const status = await loadAuthStatus();
      setAuthStatus(status);
      onAuthChange(status.authenticated);
    } catch {
      setAuthStatus({
        authenticated: false,
        user: null,
        message: 'Failed to load auth status',
      });
      onAuthChange(false);
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async () => {
    setAuthError(null);
    setPolling(true);

    const result = await startAuthLogin();
    setPolling(false);

    if (!result.ok) {
      setAuthError(result.error);
      return;
    }

    setAuthStatus(result.status);
    onAuthChange(true);
  };

  const handleLogout = async () => {
    await logoutAuth();
    const status: AuthStatus = {
      authenticated: false,
      user: null,
      message: 'Logged out',
    };
    setAuthStatus(status);
    setAuthError(null);
    onAuthChange(false);
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
            <div
              style={{
                ...styles.statusDot,
                backgroundColor: authStatus?.authenticated ? '#10B981' : '#6B7280',
              }}
            />
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

          {authError && <div style={styles.errorBox}>{authError}</div>}

          {polling && (
            <div style={styles.messageBox}>
              Waiting for you to sign in. You can close this after logging in from the browser.
            </div>
          )}

          {authStatus?.message && !authError && !polling && (
            <div style={styles.messageBox}>{authStatus.message}</div>
          )}
        </div>

        <div style={styles.actions}>
          {!authStatus?.authenticated ? (
            <button style={styles.primaryButton} onClick={handleLogin} disabled={polling}>
              {polling ? 'Signing in...' : 'Connect Account'}
            </button>
          ) : (
            <button style={styles.secondaryButton} onClick={handleLogout}>
              Disconnect
            </button>
          )}
        </div>
      </div>

      {appVersion && <div style={styles.versionText}>v{appVersion}</div>}
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
  versionText: {
    position: 'fixed' as const,
    bottom: '16px',
    right: '24px',
    color: '#52525b',
    fontSize: '0.75rem',
  },
};

export default AuthPage;
