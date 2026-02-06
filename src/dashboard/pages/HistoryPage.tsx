import React, { useState, useEffect } from 'react';

const BACKEND_URL = 'http://localhost:5001';

interface ActionHistoryItem {
  id: number;
  action_uuid: string;
  action_type: string;
  action_data: string | null;
  creation_timestamp: string;
  node_uuid: string | null;
  status: string;
  result: string | null;
  error_message: string | null;
  duration_ms: number | null;
}

const HistoryPage: React.FC = () => {
  const [actions, setActions] = useState<ActionHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${BACKEND_URL}/action_history?limit=100`);
      if (!response.ok) {
        throw new Error(`Failed to fetch: ${response.status}`);
      }
      const data = await response.json();
      setActions(data.history || []);
    } catch (err) {
      console.error('Failed to load actions history:', err);
      setError(err instanceof Error ? err.message : 'Failed to load history');
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

  const formatDuration = (ms: number | null): string => {
    if (ms === null || ms === undefined) return '-';
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  const parseJson = (data: string | null): any => {
    if (!data) return null;
    try {
      return JSON.parse(data);
    } catch {
      return data;
    }
  };

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'completed':
        return '#22c55e';
      case 'failed':
        return '#ef4444';
      case 'pending':
        return '#f59e0b';
      default:
        return '#71717a';
    }
  };

  const getStatusBgColor = (status: string): string => {
    switch (status) {
      case 'completed':
        return 'rgba(34, 197, 94, 0.1)';
      case 'failed':
        return 'rgba(239, 68, 68, 0.1)';
      case 'pending':
        return 'rgba(245, 158, 11, 0.1)';
      default:
        return 'rgba(113, 113, 122, 0.1)';
    }
  };

  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.loadingText}>Loading action history...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <h1 style={styles.title}>Actions History</h1>
        </div>
        <div style={styles.errorState}>
          <p style={styles.errorText}>{error}</p>
          <button style={styles.refreshButton} onClick={loadHistory}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h1 style={styles.title}>Actions History</h1>
        <p style={styles.subtitle}>
          View all actions executed by Covalent ({actions.length} actions)
        </p>
      </div>

      {actions.length > 0 ? (
        <div style={styles.actionsList}>
          {actions.map((action) => {
            const isExpanded = expandedId === action.id;
            const actionData = parseJson(action.action_data);
            const resultData = parseJson(action.result);

            return (
              <div 
                key={action.id} 
                style={styles.actionCard}
                onClick={() => setExpandedId(isExpanded ? null : action.id)}
              >
                {/* Header Row */}
                <div style={styles.actionHeader}>
                  <div style={styles.actionInfo}>
                    <span style={styles.actionType}>{action.action_type || 'Unknown Action'}</span>
                    <span 
                      style={{
                        ...styles.statusBadge,
                        color: getStatusColor(action.status),
                        backgroundColor: getStatusBgColor(action.status),
                      }}
                    >
                      {action.status}
                    </span>
                  </div>
                  <div style={styles.actionMeta}>
                    <span style={styles.duration}>{formatDuration(action.duration_ms)}</span>
                    <span style={styles.timestamp}>{formatTimestamp(action.creation_timestamp)}</span>
                  </div>
                </div>

                {/* Error Message (if failed) */}
                {action.status === 'failed' && action.error_message && (
                  <div style={styles.errorBox}>
                    <span style={styles.errorLabel}>Error:</span>
                    <span style={styles.errorMessage}>{action.error_message}</span>
                  </div>
                )}

                {/* Expanded Details */}
                {isExpanded && (
                  <div style={styles.expandedContent}>
                    {/* Action Data */}
                    {actionData && (
                      <div style={styles.detailSection}>
                        <h4 style={styles.detailTitle}>Action Data</h4>
                        <div style={styles.codeBlock}>
                          {typeof actionData === 'object' ? (
                            <pre style={styles.preFormatted}>
                              {JSON.stringify(actionData, null, 2)}
                            </pre>
                          ) : (
                            <span>{String(actionData)}</span>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Result */}
                    {resultData && (
                      <div style={styles.detailSection}>
                        <h4 style={styles.detailTitle}>Result</h4>
                        <div style={styles.codeBlock}>
                          {typeof resultData === 'object' ? (
                            <pre style={styles.preFormatted}>
                              {JSON.stringify(resultData, null, 2)}
                            </pre>
                          ) : (
                            <span>{String(resultData)}</span>
                          )}
                        </div>
                      </div>
                    )}

                    {/* IDs */}
                    <div style={styles.idRow}>
                      <div style={styles.idItem}>
                        <span style={styles.idLabel}>Action ID:</span>
                        <code style={styles.idValue}>{action.action_uuid}</code>
                      </div>
                      {action.node_uuid && (
                        <div style={styles.idItem}>
                          <span style={styles.idLabel}>Node ID:</span>
                          <code style={styles.idValue}>{action.node_uuid}</code>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Expand hint */}
                <div style={styles.expandHint}>
                  {isExpanded ? '▲ Click to collapse' : '▼ Click to expand'}
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
      </div>
    </div>
  );
};

const styles: { [key: string]: React.CSSProperties } = {
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
    flexDirection: 'column',
    gap: '12px',
    marginBottom: '24px',
  },
  actionCard: {
    backgroundColor: '#141414',
    borderRadius: '12px',
    padding: '16px 20px',
    border: '1px solid #27272a',
    cursor: 'pointer',
    transition: 'border-color 0.2s ease',
  },
  actionHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: '16px',
  },
  actionInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  actionType: {
    fontSize: '1rem',
    fontWeight: '500',
    color: '#ffffff',
  },
  statusBadge: {
    fontSize: '0.75rem',
    fontWeight: '600',
    padding: '4px 10px',
    borderRadius: '12px',
    textTransform: 'uppercase',
    letterSpacing: '0.02em',
  },
  actionMeta: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
  },
  duration: {
    fontSize: '0.85rem',
    fontWeight: '500',
    color: '#C5F467',
    fontFamily: 'monospace',
  },
  timestamp: {
    fontSize: '0.8rem',
    color: '#71717a',
  },
  errorBox: {
    marginTop: '12px',
    padding: '10px 14px',
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
    borderRadius: '8px',
    border: '1px solid rgba(239, 68, 68, 0.2)',
  },
  errorLabel: {
    fontSize: '0.8rem',
    fontWeight: '600',
    color: '#ef4444',
    marginRight: '8px',
  },
  errorMessage: {
    fontSize: '0.85rem',
    color: '#fca5a5',
    fontFamily: 'monospace',
  },
  expandedContent: {
    marginTop: '16px',
    paddingTop: '16px',
    borderTop: '1px solid #27272a',
  },
  detailSection: {
    marginBottom: '16px',
  },
  detailTitle: {
    fontSize: '0.8rem',
    fontWeight: '600',
    color: '#a1a1aa',
    margin: '0 0 8px 0',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  codeBlock: {
    backgroundColor: '#0a0a0a',
    borderRadius: '8px',
    padding: '12px 16px',
    border: '1px solid #27272a',
    overflow: 'auto',
    maxHeight: '200px',
  },
  preFormatted: {
    margin: 0,
    fontSize: '0.8rem',
    color: '#d4d4d8',
    fontFamily: 'monospace',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  },
  idRow: {
    display: 'flex',
    gap: '24px',
    flexWrap: 'wrap',
  },
  idItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  idLabel: {
    fontSize: '0.7rem',
    color: '#71717a',
    fontWeight: '500',
    textTransform: 'uppercase',
  },
  idValue: {
    fontSize: '0.75rem',
    color: '#a1a1aa',
    fontFamily: 'monospace',
    backgroundColor: '#0a0a0a',
    padding: '4px 8px',
    borderRadius: '4px',
  },
  expandHint: {
    marginTop: '12px',
    fontSize: '0.7rem',
    color: '#52525b',
    textAlign: 'center',
  },
  emptyState: {
    backgroundColor: '#141414',
    borderRadius: '12px',
    padding: '64px 32px',
    border: '1px solid #27272a',
    textAlign: 'center',
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
  errorState: {
    backgroundColor: '#141414',
    borderRadius: '12px',
    padding: '32px',
    border: '1px solid rgba(239, 68, 68, 0.3)',
    textAlign: 'center',
  },
  errorText: {
    color: '#ef4444',
    marginBottom: '16px',
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
};

export default HistoryPage;
