import React, { useState, useEffect, useCallback, useRef } from 'react';

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

type TabType = 'all' | 'completed' | 'failed';

const HistoryPage: React.FC = () => {
  const [actions, setActions] = useState<ActionHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('all');
  const isMountedRef = useRef(true);
  const retryCountRef = useRef(0);

  const loadHistory = useCallback(async (isRetry = false) => {
    if (!isMountedRef.current) return;
    
    if (!isRetry) {
      setLoading(true);
      retryCountRef.current = 0;
    }
    setError(null);
    
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000); // 10s timeout
      
      const response = await fetch(`${BACKEND_URL}/action_history?limit=100`, {
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      
      if (!isMountedRef.current) return;
      
      if (!response.ok) {
        throw new Error(`Failed to fetch: ${response.status}`);
      }
      const data = await response.json();
      setActions(data.history || []);
      setError(null);
    } catch (err) {
      if (!isMountedRef.current) return;
      
      console.error('Failed to load actions history:', err);
      
      // Auto-retry up to 3 times with increasing delay
      if (retryCountRef.current < 3) {
        retryCountRef.current += 1;
        const delay = retryCountRef.current * 1000; // 1s, 2s, 3s
        setTimeout(() => {
          if (isMountedRef.current) {
            loadHistory(true);
          }
        }, delay);
        return;
      }
      
      setError(err instanceof Error ? err.message : 'Failed to load history');
    } finally {
      if (isMountedRef.current && !retryCountRef.current) {
        setLoading(false);
      } else if (isMountedRef.current && retryCountRef.current >= 3) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    loadHistory();
    
    return () => {
      isMountedRef.current = false;
    };
  }, [loadHistory]);

  // Convert snake_case to Title Case (e.g., "notion_create_comment" -> "Notion Create Comment")
  const formatActionType = (actionType: string): string => {
    if (!actionType) return 'Unknown Action';
    return actionType
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
  };

  const formatTimestamp = (timestamp: string): string => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleString(undefined, {
        year: 'numeric',
        month: 'numeric',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
      });
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

  // Format action data in a clean, readable way
  const formatActionData = (actionData: any): React.ReactNode => {
    if (!actionData) return null;
    
    if (typeof actionData === 'string') {
      return <span style={styles.dataValue}>{actionData}</span>;
    }
    
    if (typeof actionData !== 'object') {
      return <span style={styles.dataValue}>{String(actionData)}</span>;
    }

    // Format object data as clean key-value pairs
    const entries = Object.entries(actionData);
    if (entries.length === 0) return null;

    return (
      <div style={styles.dataGrid}>
        {entries.map(([key, value]) => {
          // Format the key from snake_case to readable
          const formattedKey = key
            .split('_')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');
          
          // Format the value
          let displayValue: string;
          if (value === null || value === undefined) {
            displayValue = '-';
          } else if (typeof value === 'object') {
            displayValue = JSON.stringify(value, null, 2);
          } else {
            displayValue = String(value);
          }
          
          // Truncate long values
          const isTruncated = displayValue.length > 200;
          const truncatedValue = isTruncated 
            ? displayValue.substring(0, 200) + '...'
            : displayValue;

          return (
            <div key={key} style={styles.dataRow}>
              <span style={styles.dataKey}>{formattedKey}</span>
              <span style={styles.dataValue} title={isTruncated ? displayValue : undefined}>
                {truncatedValue}
              </span>
            </div>
          );
        })}
      </div>
    );
  };

  // Format the result as a user-friendly message
  const formatResultMessage = (status: string, result: string | null): string => {
    if (status === 'completed') {
      const resultData = parseJson(result);
      if (resultData && typeof resultData === 'object' && resultData.success === true) {
        return 'Action executed successfully.';
      }
      return 'Action completed.';
    } else if (status === 'failed') {
      return 'Action failed. Please try again. You can report this issue to the Covalent team for a better resolution.';
    } else if (status === 'pending') {
      return 'Action is pending execution.';
    }
    return 'Unknown status.';
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

  // Filter actions based on active tab
  const filteredActions = activeTab === 'failed' 
    ? actions.filter(action => action.status === 'failed')
    : activeTab === 'completed'
    ? actions.filter(action => action.status === 'completed')
    : actions;

  const completedCount = actions.filter(action => action.status === 'completed').length;
  const failedCount = actions.filter(action => action.status === 'failed').length;

  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.loadingContainer}>
          <div style={styles.spinner}></div>
          <div style={styles.loadingText}>Loading action history...</div>
        </div>
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
          <p style={styles.errorText}>Failed to load: {error}</p>
          <p style={styles.errorHint}>Make sure the Flask server is running on port 5001</p>
          <button style={styles.refreshButton} onClick={() => loadHistory()}>
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

      {/* Tab Navigation - Successful, Failed, All Actions */}
      <div style={styles.tabContainer}>
        <button
          style={{
            ...styles.tab,
            ...(activeTab === 'completed' ? styles.tabActive : {}),
          }}
          onClick={() => setActiveTab('completed')}
        >
          Successful ({completedCount})
        </button>
        <button
          style={{
            ...styles.tab,
            ...(activeTab === 'failed' ? styles.tabActiveFailed : {}),
          }}
          onClick={() => setActiveTab('failed')}
        >
          Failed ({failedCount})
        </button>
        <button
          style={{
            ...styles.tab,
            ...(activeTab === 'all' ? styles.tabActive : {}),
          }}
          onClick={() => setActiveTab('all')}
        >
          All Actions
        </button>
      </div>

      {filteredActions.length > 0 ? (
        <div style={styles.actionsList}>
          {filteredActions.map((action) => {
            const isExpanded = expandedId === action.id;
            const actionData = parseJson(action.action_data);

            return (
              <div 
                key={action.id} 
                style={styles.actionCard}
                onClick={() => setExpandedId(isExpanded ? null : action.id)}
              >
                {/* Header Row */}
                <div style={styles.actionHeader}>
                  <div style={styles.actionInfo}>
                    <span style={styles.actionType}>{formatActionType(action.action_type)}</span>
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
                    {/* Action Data - Clean format */}
                    {actionData && (
                      <div style={styles.detailSection}>
                        <h4 style={styles.detailTitle}>Action Details</h4>
                        <div style={styles.detailBox}>
                          {formatActionData(actionData)}
                        </div>
                      </div>
                    )}

                    {/* Result - as user-friendly message */}
                    <div style={styles.detailSection}>
                      <h4 style={styles.detailTitle}>Result</h4>
                      <div style={{
                        ...styles.resultMessage,
                        color: action.status === 'completed' ? '#22c55e' : 
                               action.status === 'failed' ? '#fca5a5' : '#f59e0b',
                      }}>
                        {formatResultMessage(action.status, action.result)}
                      </div>
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
          <h3 style={styles.emptyTitle}>
            {activeTab === 'failed' ? 'No Failed Actions' : 
             activeTab === 'completed' ? 'No Successful Actions' :
             'No Actions Yet'}
          </h3>
          <p style={styles.emptyText}>
            {activeTab === 'failed' 
              ? 'Great news! No actions have failed recently.'
              : activeTab === 'completed'
              ? 'No actions have completed successfully yet.'
              : 'No actions have been executed. Start using Covalent to see your action history here.'}
          </p>
        </div>
      )}

      <div style={styles.actionButtons}>
        <button style={styles.refreshButton} onClick={() => loadHistory()}>
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
    marginBottom: '24px',
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
  tabContainer: {
    display: 'flex',
    gap: '8px',
    marginBottom: '24px',
    borderBottom: '1px solid #27272a',
    paddingBottom: '12px',
  },
  tab: {
    padding: '10px 20px',
    backgroundColor: 'transparent',
    border: '1px solid #27272a',
    borderRadius: '8px',
    color: '#a1a1aa',
    fontSize: '0.85rem',
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  tabActive: {
    backgroundColor: 'rgba(197, 244, 103, 0.1)',
    borderColor: '#C5F467',
    color: '#C5F467',
  },
  tabActiveFailed: {
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
    borderColor: '#ef4444',
    color: '#ef4444',
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
  detailBox: {
    backgroundColor: '#0a0a0a',
    borderRadius: '8px',
    padding: '16px',
    border: '1px solid #27272a',
  },
  dataGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
  dataRow: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  dataKey: {
    fontSize: '0.75rem',
    fontWeight: '600',
    color: '#71717a',
    textTransform: 'uppercase',
    letterSpacing: '0.03em',
  },
  dataValue: {
    fontSize: '0.9rem',
    color: '#e4e4e7',
    lineHeight: '1.5',
    wordBreak: 'break-word',
  },
  resultMessage: {
    fontSize: '0.9rem',
    lineHeight: '1.5',
    padding: '12px 16px',
    backgroundColor: '#0a0a0a',
    borderRadius: '8px',
    border: '1px solid #27272a',
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
    marginBottom: '8px',
    fontSize: '1rem',
  },
  errorHint: {
    color: '#71717a',
    marginBottom: '16px',
    fontSize: '0.85rem',
  },
  loadingContainer: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '64px',
    gap: '16px',
  },
  spinner: {
    width: '32px',
    height: '32px',
    border: '3px solid #27272a',
    borderTopColor: '#C5F467',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
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

// Add keyframes for spinner animation
const styleSheet = document.createElement('style');
styleSheet.textContent = `
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
`;
if (!document.head.querySelector('style[data-history-page]')) {
  styleSheet.setAttribute('data-history-page', 'true');
  document.head.appendChild(styleSheet);
}

export default HistoryPage;
