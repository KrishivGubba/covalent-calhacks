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
    icon: '📁',
  },
  {
    id: 'github',
    name: 'GitHub',
    connected: false,
    description: 'Access repositories, issues, and pull requests',
    icon: '🐙',
  },
  {
    id: 'perplexity',
    name: 'Perplexity Search',
    connected: true,
    description: 'AI-powered web search',
    icon: '🔍',
    included: true,
  },
  {
    id: 'notion',
    name: 'Notion',
    connected: false,
    description: 'Access Notion workspaces and pages',
    icon: '📝',
  },
  {
    id: 'google',
    name: 'Google Workspace',
    connected: false,
    description: 'Calendar, Drive, Mail',
    icon: '🔷',
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
    if (!selected) {
      return;
    }

    const rootPath = typeof selected === 'string' ? selected : selected[0];
    if (!rootPath) {
      return;
    }

    const result = await connectFilesystem(rootPath);
    if (!result.ok) {
      throw new Error(result.error);
    }
  };

  const handleConnect = async (id: string) => {
    setError(null);
    setConnectingId(id);
    try {
      if (id === 'filesystem') {
        await handleConnectFilesystem();
      } else if (id === 'google' || id === 'github' || id === 'notion') {
        const result = await connectOAuthIntegration(id);
        if (!result.ok) {
          throw new Error(result.error);
        }
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
      if (!ok) {
        throw new Error(`Failed to disconnect ${id}`);
      }
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
                  <div
                    style={{
                      ...styles.statusDot,
                      backgroundColor: integration.connected ? '#10B981' : '#6B7280',
                    }}
                  />
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
                  title={
                    !isAuthenticated && integration.id !== 'filesystem'
                      ? 'Please log in first'
                      : undefined
                  }
                >
                  {connectingId === integration.id ? 'Disconnecting...' : 'Disconnect'}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <div style={styles.constructionNote}>Under Construction</div>
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
  errorBox: {
    backgroundColor: 'rgba(239, 68, 68, 0.08)',
    border: '1px solid rgba(239, 68, 68, 0.3)',
    borderRadius: '8px',
    padding: '12px 16px',
    color: '#ef4444',
    fontSize: '0.85rem',
    marginBottom: '16px',
  },
};

export default MCPPage;
