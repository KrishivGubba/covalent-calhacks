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
                backgroundColor: authStatus?.authenticated ? '#22c55e' : '#D4CFC6',
              }}
            />
            <span style={styles.statusText}>
              {authStatus?.authenticated ? 'Connected' : 'Not Connected'}
            </span>
          </div>

          {authStatus?.user && (
            <div style={styles.userInfo}>
              <span style={styles.userLabel}>Account</span>
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
            <button
              style={{ ...styles.primaryButton, opacity: polling ? 0.6 : 1, cursor: polling ? 'not-allowed' : 'pointer' }}
              onClick={handleLogin}
              disabled={polling}
            >
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

const styles: { [key: string]: React.CSSProperties } = {
  container: {
    padding: '40px',
    maxWidth: '700px',
  },
  header: {
    marginBottom: '28px',
  },
  title: {
    fontSize: '1.6rem',
    fontWeight: '700',
    color: '#1A1A1A',
    margin: '0 0 6px 0',
    letterSpacing: '-0.02em',
  },
  subtitle: {
    fontSize: '0.9rem',
    color: '#5A5A5A',
    margin: 0,
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: '14px',
    padding: '24px',
    border: '1px solid #E8E4DC',
    marginBottom: '20px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
  },
  statusSection: {
    marginBottom: '24px',
  },
  statusHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    marginBottom: '14px',
  },
  statusDot: {
    width: '9px',
    height: '9px',
    borderRadius: '50%',
    flexShrink: 0,
  },
  statusText: {
    fontSize: '1rem',
    fontWeight: '600',
    color: '#1A1A1A',
  },
  userInfo: {
    display: 'flex',
    gap: '10px',
    alignItems: 'center',
    marginBottom: '12px',
    padding: '10px 14px',
    backgroundColor: '#FAFAF8',
    borderRadius: '10px',
    border: '1px solid #E8E4DC',
  },
  userLabel: {
    color: '#9A9A96',
    fontSize: '0.825rem',
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  userName: {
    color: '#1A1A1A',
    fontWeight: '500',
    fontSize: '0.875rem',
  },
  messageBox: {
    backgroundColor: 'rgba(193, 122, 95, 0.08)',
    border: '1px solid rgba(193, 122, 95, 0.25)',
    borderRadius: '10px',
    padding: '12px 16px',
    color: '#5A5A5A',
    fontSize: '0.85rem',
    lineHeight: '1.55',
  },
  errorBox: {
    backgroundColor: 'rgba(239, 68, 68, 0.06)',
    border: '1px solid rgba(239, 68, 68, 0.22)',
    borderRadius: '10px',
    padding: '12px 16px',
    color: '#991b1b',
    fontSize: '0.85rem',
    marginBottom: '12px',
  },
  actions: {
    display: 'flex',
    gap: '10px',
  },
  primaryButton: {
    padding: '11px 24px',
    backgroundColor: '#1A1A1A',
    border: 'none',
    borderRadius: '100px',
    color: '#FFFFFF',
    fontSize: '0.875rem',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
    fontFamily: 'inherit',
  },
  secondaryButton: {
    padding: '11px 24px',
    backgroundColor: 'transparent',
    border: '1px solid #E8E4DC',
    borderRadius: '100px',
    color: '#5A5A5A',
    fontSize: '0.875rem',
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
    fontFamily: 'inherit',
  },
  loadingText: {
    color: '#9A9A96',
    fontSize: '0.9rem',
  },
  versionText: {
    position: 'fixed',
    bottom: '16px',
    right: '24px',
    color: '#D4CFC6',
    fontSize: '0.72rem',
    fontWeight: '500',
  },
};

export default AuthPage;
