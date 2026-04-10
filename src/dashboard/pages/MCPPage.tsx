import React, { useEffect, useState } from 'react';
import { open } from '@tauri-apps/plugin-dialog';
import {
  connectFilesystem,
  connectOAuthIntegration,
  disconnectIntegration,
  fetchIntegrationsStatus,
  type IntegrationStatus,
} from '../../shared/integrationService';

interface MCPPageProps {
  isAuthenticated: boolean;
}

const FALLBACK_INTEGRATIONS: IntegrationStatus[] = [
  {
    id: 'filesystem',
    name: 'Filesystem',
    connected: false,
    description: 'Choose a folder to access local files and directories',
  },
  {
    id: 'github',
    name: 'GitHub',
    connected: false,
    description: 'Access repositories, issues, and pull requests',
  },
  {
    id: 'perplexity',
    name: 'Perplexity Search',
    connected: true,
    description: 'AI-powered web search',
    included: true,
  },
  {
    id: 'notion',
    name: 'Notion',
    connected: false,
    description: 'Access Notion workspaces and pages',
  },
  {
    id: 'google',
    name: 'Google Workspace',
    connected: false,
    description: 'Calendar, Drive, Mail',
  },
];

const MCPPage: React.FC<MCPPageProps> = ({ isAuthenticated }) => {
  const [integrations, setIntegrations] = useState<IntegrationStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [connectingId, setConnectingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadIntegrations();
  }, []);

  const loadIntegrations = async () => {
    setLoading(true);
    setError(null);
    try {
      const statuses = await fetchIntegrationsStatus();
      setIntegrations(statuses);
    } catch (e) {
      setIntegrations(FALLBACK_INTEGRATIONS);
      setError(e instanceof Error ? e.message : 'Failed to fetch integrations');
    } finally {
      setLoading(false);
    }
  };

  const handleConnectFilesystem = async () => {
    const selected = await open({
      directory: true,
      multiple: false,
      title: 'Choose a folder for Covalent to access',
    });
    if (!selected) return;

    const rootPath = typeof selected === 'string' ? selected : selected[0];
    if (!rootPath) return;

    const result = await connectFilesystem(rootPath);
    if (!result.ok) throw new Error(result.error);
  };

  const handleConnect = async (id: string) => {
    setError(null);
    setConnectingId(id);
    try {
      if (id === 'filesystem') {
        await handleConnectFilesystem();
      } else if (id === 'google' || id === 'github' || id === 'notion') {
        const result = await connectOAuthIntegration(id);
        if (!result.ok) throw new Error(result.error);
      } else {
        throw new Error(`${id} integration is not supported yet`);
      }
      await loadIntegrations();
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to connect ${id}`);
    } finally {
      setConnectingId(null);
    }
  };

  const handleDisconnect = async (id: string) => {
    setError(null);
    setConnectingId(id);
    try {
      const ok = await disconnectIntegration(id);
      if (!ok) throw new Error(`Failed to disconnect ${id}`);
      await loadIntegrations();
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to disconnect ${id}`);
    } finally {
      setConnectingId(null);
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
        <p style={styles.subtitle}>Connect external services and tools</p>
      </div>

      {!isAuthenticated && (
        <div style={styles.loginPrompt}>
          Please log in on the Profile page to manage OAuth integrations.
        </div>
      )}

      {error && <div style={styles.errorBox}>{error}</div>}

      <div style={styles.grid}>
        {integrations.map((integration) => (
          <div key={integration.id} style={styles.card}>
            <div style={styles.cardHeader}>
              <div style={styles.cardTitleRow}>
                <h3 style={styles.cardTitle}>
                  {integration.name}
                </h3>
                <div
                  style={{
                    ...styles.statusText,
                    color: integration.connected ? '#166534' : '#B42318',
                  }}
                >
                  {integration.connected ? 'Connected' : 'Not Connected'}
                </div>
              </div>
              <p style={styles.cardDescription}>{integration.description}</p>
            </div>

            <div style={styles.cardActions}>
              {integration.included ? (
                <div style={styles.includedBadge}>Included</div>
              ) : !integration.connected ? (
                <button
                  style={{
                    ...styles.connectButton,
                    ...((!isAuthenticated && integration.id !== 'filesystem') ||
                    connectingId === integration.id
                      ? styles.buttonDisabled
                      : {}),
                  }}
                  onClick={() => void handleConnect(integration.id)}
                  disabled={
                    (!isAuthenticated && integration.id !== 'filesystem') ||
                    connectingId === integration.id
                  }
                  title={
                    !isAuthenticated && integration.id !== 'filesystem'
                      ? 'Please log in first'
                      : undefined
                  }
                >
                  {connectingId === integration.id
                    ? 'Connecting...'
                    : integration.id === 'filesystem'
                    ? 'Choose Folder'
                    : 'Connect'}
                </button>
              ) : (
                <button
                  style={{
                    ...styles.disconnectButton,
                    ...(isAuthenticated || integration.id === 'filesystem'
                      ? {}
                      : styles.buttonDisabled),
                  }}
                  onClick={() => void handleDisconnect(integration.id)}
                  disabled={!isAuthenticated && integration.id !== 'filesystem'}
                >
                  {connectingId === integration.id ? 'Disconnecting...' : 'Disconnect'}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

    </div>
  );
};

const styles: { [key: string]: React.CSSProperties } = {
  container: {
    padding: '40px',
    maxWidth: '960px',
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
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(270px, 1fr))',
    gap: '14px',
    marginBottom: '28px',
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: '14px',
    padding: '20px',
    border: '1px solid #E8E4DC',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'space-between',
    minHeight: '150px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
    transition: 'box-shadow 0.15s ease, border-color 0.15s ease',
  },
  cardHeader: {
    marginBottom: '16px',
  },
  cardTitleRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '10px',
  },
  cardTitle: {
    fontSize: '0.95rem',
    fontWeight: '700',
    color: '#1A1A1A',
    margin: 0,
    letterSpacing: '-0.01em',
  },
  statusText: {
    fontSize: '0.74rem',
    fontWeight: '700',
    letterSpacing: '0.01em',
  },
  cardDescription: {
    fontSize: '0.825rem',
    color: '#5A5A5A',
    margin: 0,
    lineHeight: '1.5',
  },
  cardActions: {
    display: 'flex',
    gap: '8px',
  },
  connectButton: {
    flex: 1,
    padding: '9px 18px',
    backgroundColor: '#1A1A1A',
    border: 'none',
    borderRadius: '100px',
    color: '#FFFFFF',
    fontSize: '0.825rem',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
    fontFamily: 'inherit',
  },
  disconnectButton: {
    flex: 1,
    padding: '9px 18px',
    backgroundColor: 'transparent',
    border: '1px solid #E8E4DC',
    borderRadius: '100px',
    color: '#5A5A5A',
    fontSize: '0.825rem',
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
    fontFamily: 'inherit',
  },
  buttonDisabled: {
    opacity: 0.45,
    cursor: 'not-allowed',
  },
  includedBadge: {
    flex: 1,
    padding: '9px 18px',
    backgroundColor: 'rgba(193, 122, 95, 0.08)',
    border: '1px solid rgba(193, 122, 95, 0.25)',
    borderRadius: '100px',
    color: '#C17A5F',
    fontSize: '0.825rem',
    fontWeight: '600',
    textAlign: 'center',
  },
  loadingText: {
    color: '#9A9A96',
    fontSize: '0.9rem',
  },
  loginPrompt: {
    backgroundColor: 'rgba(193, 122, 95, 0.08)',
    border: '1px solid rgba(193, 122, 95, 0.25)',
    borderRadius: '10px',
    padding: '12px 16px',
    color: '#C17A5F',
    fontSize: '0.875rem',
    marginBottom: '20px',
    textAlign: 'center',
  },
  errorBox: {
    backgroundColor: 'rgba(239, 68, 68, 0.06)',
    border: '1px solid rgba(239, 68, 68, 0.22)',
    borderRadius: '10px',
    padding: '12px 16px',
    color: '#991b1b',
    fontSize: '0.85rem',
    marginBottom: '16px',
  },
};

export default MCPPage;
