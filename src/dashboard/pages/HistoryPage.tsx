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
    color: '#FFFFFF',
    margin: '0 0 8px 0',
    letterSpacing: '-0.02em',
  },
  subtitle: {
    fontSize: '0.95rem',
    color: 'rgba(255, 255, 255, 0.5)',
    margin: 0,
  },
  actionsList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '12px',
    marginBottom: '24px',
  },
  actionCard: {
    backgroundColor: 'rgba(20, 20, 30, 0.6)',
    borderRadius: '12px',
    padding: '20px',
    border: '1px solid rgba(255, 255, 255, 0.06)',
  },
  actionHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '16px',
    paddingBottom: '12px',
    borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
  },
  actionType: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  actionTypeName: {
    fontSize: '1rem',
    fontWeight: '500',
    color: '#FFFFFF',
  },
  timestamp: {
    fontSize: '0.8rem',
    color: 'rgba(255, 255, 255, 0.4)',
  },
  actionBody: {
    marginBottom: '16px',
  },
  actionDataRaw: {
    padding: '12px',
    backgroundColor: 'rgba(15, 15, 25, 0.8)',
    borderRadius: '8px',
    color: 'rgba(255, 255, 255, 0.75)',
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
    backgroundColor: 'rgba(15, 15, 25, 0.6)',
    borderRadius: '6px',
  },
  dataKey: {
    fontWeight: '500',
    color: 'rgba(255, 255, 255, 0.6)',
    fontSize: '0.85rem',
  },
  dataValue: {
    color: 'rgba(255, 255, 255, 0.8)',
    fontSize: '0.85rem',
    fontFamily: 'monospace',
  },
  actionFooter: {
    display: 'flex',
    gap: '16px',
    paddingTop: '12px',
    borderTop: '1px solid rgba(255, 255, 255, 0.05)',
  },
  uuid: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  uuidLabel: {
    fontSize: '0.7rem',
    color: 'rgba(255, 255, 255, 0.4)',
    fontWeight: '500',
    textTransform: 'uppercase' as const,
  },
  uuidValue: {
    fontSize: '0.75rem',
    color: 'rgba(255, 255, 255, 0.6)',
    fontFamily: 'monospace',
    backgroundColor: 'rgba(15, 15, 25, 0.6)',
    padding: '2px 8px',
    borderRadius: '4px',
  },
  emptyState: {
    backgroundColor: 'rgba(20, 20, 30, 0.6)',
    borderRadius: '12px',
    padding: '64px 32px',
    border: '1px solid rgba(255, 255, 255, 0.06)',
    textAlign: 'center' as const,
    marginBottom: '24px',
  },
  emptyTitle: {
    fontSize: '1.25rem',
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: '12px',
  },
  emptyText: {
    fontSize: '0.9rem',
    color: 'rgba(255, 255, 255, 0.4)',
    lineHeight: '1.6',
  },
  loadingText: {
    color: 'rgba(255, 255, 255, 0.6)',
    fontSize: '0.95rem',
  },
  actionButtons: {
    display: 'flex',
    gap: '12px',
  },
  refreshButton: {
    padding: '10px 20px',
    backgroundColor: '#6366F1',
    border: 'none',
    borderRadius: '8px',
    color: '#FFFFFF',
    fontSize: '0.85rem',
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  exportButton: {
    padding: '10px 20px',
    backgroundColor: 'transparent',
    border: '1px solid rgba(255, 255, 255, 0.2)',
    borderRadius: '8px',
    color: '#FFFFFF',
    fontSize: '0.85rem',
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
};

export default HistoryPage;
