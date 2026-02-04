import React, { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';

interface ActionHistoryItem {
  action_uuid: string;
  action_type: string;
  action_data: string;
  creation_timestamp: string;
  node_uuid: string;
}

const HistoryPage: React.FC = () => {
  const [actions, setActions] = useState<ActionHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    try {
      const data = await invoke<ActionHistoryItem[]>('get_actions_history');
      setActions(data);
    } catch (error) {
      console.error('Failed to load actions history:', error);
    } finally {
      setLoading(false);
    }
  };

  const formatTimestamp = (timestamp: string): string => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleString();
    } catch {
      return timestamp;
    }
  };

  const parseActionData = (data: string): any => {
    try {
      return JSON.parse(data);
    } catch {
      return { raw: data };
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
        <h1 style={styles.title}>Actions History</h1>
        <p style={styles.subtitle}>
          View all actions executed by Covalent
        </p>
      </div>

      {actions.length > 0 ? (
        <div style={styles.actionsList}>
          {actions.map((action) => {
            const actionData = parseActionData(action.action_data);
            return (
              <div key={action.action_uuid} style={styles.actionCard}>
                <div style={styles.actionHeader}>
                  <div style={styles.actionType}>
                    <span style={styles.actionTypeName}>{action.action_type || 'Action'}</span>
                  </div>
                  <div style={styles.timestamp}>
                    {formatTimestamp(action.creation_timestamp)}
                  </div>
                </div>

                <div style={styles.actionBody}>
                  {actionData.raw ? (
                    <div style={styles.actionDataRaw}>{actionData.raw}</div>
                  ) : (
                    <div style={styles.actionDataJson}>
                      {Object.entries(actionData).map(([key, value]) => (
                        <div key={key} style={styles.dataRow}>
                          <span style={styles.dataKey}>{key}:</span>
                          <span style={styles.dataValue}>
                            {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div style={styles.actionFooter}>
                  <div style={styles.uuid}>
                    <span style={styles.uuidLabel}>Action ID:</span>
                    <code style={styles.uuidValue}>{action.action_uuid.slice(0, 16)}...</code>
                  </div>
                  <div style={styles.uuid}>
                    <span style={styles.uuidLabel}>Node:</span>
                    <code style={styles.uuidValue}>{action.node_uuid.slice(0, 16)}...</code>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div style={styles.emptyState}>
          <h3 style={styles.emptyTitle}>No Actions Yet</h3>
          <p style={styles.emptyText}>
            No actions have been executed. Start using Covalent to see your action history here.
          </p>
        </div>
      )}

      <div style={styles.actionButtons}>
        <button style={styles.refreshButton} onClick={loadHistory}>
          Refresh
        </button>
        {actions.length > 0 && (
          <button
            style={styles.exportButton}
            onClick={() => {
              console.log('Export clicked');
              alert('Export under construction');
            }}
          >
            Export History
          </button>
        )}
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
  actionsList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '12px',
    marginBottom: '24px',
  },
  actionCard: {
    backgroundColor: '#141414',
    borderRadius: '12px',
    padding: '20px',
    border: '1px solid #27272a',
  },
  actionHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '16px',
    paddingBottom: '12px',
    borderBottom: '1px solid #27272a',
  },
  actionType: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  actionTypeName: {
    fontSize: '1rem',
    fontWeight: '500',
    color: '#ffffff',
  },
  timestamp: {
    fontSize: '0.8rem',
    color: '#71717a',
  },
  actionBody: {
    marginBottom: '16px',
  },
  actionDataRaw: {
    padding: '12px',
    backgroundColor: '#111111',
    borderRadius: '8px',
    color: '#a1a1aa',
    fontSize: '0.85rem',
    fontFamily: 'monospace',
    whiteSpace: 'pre-wrap' as const,
  },
  actionDataJson: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '8px',
  },
  dataRow: {
    display: 'flex',
    gap: '8px',
    padding: '8px 12px',
    backgroundColor: '#111111',
    borderRadius: '6px',
  },
  dataKey: {
    fontWeight: '500',
    color: '#a1a1aa',
    fontSize: '0.85rem',
  },
  dataValue: {
    color: '#ffffff',
    fontSize: '0.85rem',
    fontFamily: 'monospace',
  },
  actionFooter: {
    display: 'flex',
    gap: '16px',
    paddingTop: '12px',
    borderTop: '1px solid #27272a',
  },
  uuid: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  uuidLabel: {
    fontSize: '0.7rem',
    color: '#71717a',
    fontWeight: '500',
    textTransform: 'uppercase' as const,
  },
  uuidValue: {
    fontSize: '0.75rem',
    color: '#a1a1aa',
    fontFamily: 'monospace',
    backgroundColor: '#111111',
    padding: '2px 8px',
    borderRadius: '4px',
  },
  emptyState: {
    backgroundColor: '#141414',
    borderRadius: '12px',
    padding: '64px 32px',
    border: '1px solid #27272a',
    textAlign: 'center' as const,
    marginBottom: '24px',
  },
  emptyTitle: {
    fontSize: '1.25rem',
    fontWeight: '600',
    color: '#ffffff',
    marginBottom: '12px',
  },
  emptyText: {
    fontSize: '0.9rem',
    color: '#71717a',
    lineHeight: '1.6',
  },
  loadingText: {
    color: '#a1a1aa',
    fontSize: '0.95rem',
  },
  actionButtons: {
    display: 'flex',
    gap: '12px',
  },
  refreshButton: {
    padding: '10px 20px',
    backgroundColor: '#C5F467',
    border: 'none',
    borderRadius: '8px',
    color: '#0a0a0a',
    fontSize: '0.85rem',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  exportButton: {
    padding: '10px 20px',
    backgroundColor: 'transparent',
    border: '1px solid #27272a',
    borderRadius: '8px',
    color: '#ffffff',
    fontSize: '0.85rem',
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
};

export default HistoryPage;
