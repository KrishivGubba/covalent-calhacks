import React, { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';

interface MCPIntegration {
  id: string;
  name: string;
  connected: boolean;
  description: string;
}

const MCPPage: React.FC = () => {
  const [integrations, setIntegrations] = useState<MCPIntegration[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadIntegrations();
  }, []);

  const loadIntegrations = async () => {
    try {
      const data = await invoke<MCPIntegration[]>('get_mcp_integrations');
      setIntegrations(data);
    } catch (error) {
      console.error('Failed to load MCP integrations:', error);
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

      <div style={styles.grid}>
        {integrations.map((integration) => (
          <div key={integration.id} style={styles.card}>
            <div style={styles.cardHeader}>
              <div style={styles.cardTitleRow}>
                <h3 style={styles.cardTitle}>{integration.name}</h3>
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
              {!integration.connected ? (
                <button
                  style={styles.connectButton}
                  onClick={() => handleConnect(integration.id)}
                >
                  Connect
                </button>
              ) : (
                <button
                  style={styles.disconnectButton}
                  onClick={() => handleDisconnect(integration.id)}
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
    color: '#FFFFFF',
    margin: '0 0 8px 0',
    letterSpacing: '-0.02em',
  },
  subtitle: {
    fontSize: '0.95rem',
    color: 'rgba(255, 255, 255, 0.5)',
    margin: 0,
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
    gap: '16px',
    marginBottom: '32px',
  },
  card: {
    backgroundColor: 'rgba(20, 20, 30, 0.6)',
    borderRadius: '12px',
    padding: '20px',
    border: '1px solid rgba(255, 255, 255, 0.06)',
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
    color: '#FFFFFF',
    margin: 0,
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
    backgroundColor: 'rgba(16, 185, 129, 0.15)',
    color: '#10B981',
    border: '1px solid rgba(16, 185, 129, 0.3)',
  },
  statusBadgeDisconnected: {
    backgroundColor: 'rgba(107, 114, 128, 0.15)',
    color: 'rgba(255, 255, 255, 0.5)',
    border: '1px solid rgba(107, 114, 128, 0.3)',
  },
  statusDot: {
    width: '6px',
    height: '6px',
    borderRadius: '50%',
  },
  cardDescription: {
    fontSize: '0.85rem',
    color: 'rgba(255, 255, 255, 0.5)',
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
    backgroundColor: '#6366F1',
    border: 'none',
    borderRadius: '8px',
    color: '#FFFFFF',
    fontSize: '0.85rem',
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  disconnectButton: {
    flex: 1,
    padding: '10px 18px',
    backgroundColor: 'transparent',
    border: '1px solid rgba(239, 68, 68, 0.4)',
    borderRadius: '8px',
    color: 'rgba(239, 68, 68, 0.9)',
    fontSize: '0.85rem',
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  loadingText: {
    color: 'rgba(255, 255, 255, 0.6)',
    fontSize: '0.95rem',
  },
  constructionNote: {
    backgroundColor: 'rgba(99, 102, 241, 0.1)',
    border: '1px solid rgba(99, 102, 241, 0.2)',
    borderRadius: '8px',
    padding: '12px 16px',
    color: 'rgba(255, 255, 255, 0.7)',
    fontSize: '0.85rem',
    textAlign: 'center' as const,
  },
};

export default MCPPage;
