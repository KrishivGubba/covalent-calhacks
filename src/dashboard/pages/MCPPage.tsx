import React, { useState, useEffect } from 'react';

const BACKEND_URL = 'http://localhost:5001';

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

  useEffect(() => {
    loadIntegrations();
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

  const handleConnect = (id: string) => {
    console.log(`Connecting to ${id}`);
    alert(`${id} integration under construction`);
  };

  const handleDisconnect = (id: string) => {
    console.log(`Disconnecting from ${id}`);
    alert(`Disconnect under construction`);
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
                    ...(isAuthenticated ? {} : styles.buttonDisabled),
                  }}
                  onClick={() => handleConnect(integration.id)}
                  disabled={!isAuthenticated}
                  title={isAuthenticated ? undefined : 'Please log in first'}
                >
                  Connect
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
