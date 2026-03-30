import React, { useState, useEffect, useCallback, useRef } from 'react';
import { listen } from '@tauri-apps/api/event';

const FLASK_PORT = import.meta.env.VITE_FLASK_PORT || '15001';
const BACKEND_URL = `http://localhost:${FLASK_PORT}`;

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
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('all');
  const isMountedRef = useRef(true);
  const retryCountRef = useRef(0);
  const hasLoadedOnceRef = useRef(false);
  const mountTimeRef = useRef(Date.now());
  const isLoadingRef = useRef(false);

  const loadHistory = useCallback(async (isRetry = false, isBackgroundRefresh = false) => {
    if (!isMountedRef.current) return;

    if (!isRetry && isLoadingRef.current) return;

    if (!isRetry) {
      isLoadingRef.current = true;
      if (!hasLoadedOnceRef.current) {
        setLoading(true);
      } else if (isBackgroundRefresh) {
        setIsRefreshing(true);
      } else {
        setLoading(true);
      }
      retryCountRef.current = 0;
    }
    setError(null);

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000);

      const response = await fetch(`${BACKEND_URL}/action_history?limit=100`, {
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!isMountedRef.current) return;
      if (!response.ok) throw new Error(`Failed to fetch: ${response.status}`);

      const data = await response.json();
      setActions(data.history || []);
      setError(null);
      hasLoadedOnceRef.current = true;
    } catch (err) {
      if (!isMountedRef.current) return;

      if (retryCountRef.current < 3) {
        retryCountRef.current += 1;
        const delay = retryCountRef.current * 1000;
        setTimeout(() => {
          if (isMountedRef.current) loadHistory(true, isBackgroundRefresh);
        }, delay);
        return;
      }

      setError(err instanceof Error ? err.message : 'Failed to load history');
    } finally {
      if (isMountedRef.current && !retryCountRef.current) {
        setLoading(false);
        setIsRefreshing(false);
        isLoadingRef.current = false;
      } else if (isMountedRef.current && retryCountRef.current >= 3) {
        setLoading(false);
        setIsRefreshing(false);
        isLoadingRef.current = false;
      }
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    mountTimeRef.current = Date.now();
    loadHistory();

    return () => {
      isMountedRef.current = false;
      isLoadingRef.current = false;
    };
  }, [loadHistory]);

  useEffect(() => {
    const unlistenPromise = listen('action-completed', () => {
      const timeSinceMount = Date.now() - mountTimeRef.current;
      if (timeSinceMount < 1000) return;

      setTimeout(() => {
        if (isMountedRef.current) loadHistory(false, true);
      }, 500);
    });

    return () => {
      unlistenPromise.then(fn => fn());
    };
  }, [loadHistory]);

  const formatActionType = (actionType: string): string => {
    if (!actionType) return 'Unknown Action';
    return actionType
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
  };

  const formatTimestamp = (timestamp: string): string => {
    try {
      return new Date(timestamp).toLocaleString(undefined, {
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
    try { return JSON.parse(data); } catch { return data; }
  };

  const formatActionData = (actionData: any): React.ReactNode => {
    if (!actionData) return null;
    if (typeof actionData === 'string') return <span style={styles.dataValue}>{actionData}</span>;
    if (typeof actionData !== 'object') return <span style={styles.dataValue}>{String(actionData)}</span>;

    const entries = Object.entries(actionData);
    if (entries.length === 0) return null;

    return (
      <div style={styles.dataGrid}>
        {entries.map(([key, value]) => {
          const formattedKey = key
            .split('_')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');

          let displayValue: string;
          if (value === null || value === undefined) displayValue = '-';
          else if (typeof value === 'object') displayValue = JSON.stringify(value, null, 2);
          else displayValue = String(value);

          const isTruncated = displayValue.length > 200;
          const truncatedValue = isTruncated ? displayValue.substring(0, 200) + '...' : displayValue;

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

  const getStatusStyle = (status: string): React.CSSProperties => {
    switch (status) {
      case 'completed':
        return { color: '#166534', backgroundColor: 'rgba(34, 197, 94, 0.08)', border: '1px solid rgba(34, 197, 94, 0.22)' };
      case 'failed':
        return { color: '#991b1b', backgroundColor: 'rgba(239, 68, 68, 0.06)', border: '1px solid rgba(239, 68, 68, 0.22)' };
      case 'pending':
        return { color: '#92400e', backgroundColor: 'rgba(245, 158, 11, 0.08)', border: '1px solid rgba(245, 158, 11, 0.22)' };
      default:
        return { color: '#9A9A96', backgroundColor: '#F4F1EC', border: '1px solid #E8E4DC' };
    }
  };

  const getResultColor = (status: string): string => {
    switch (status) {
      case 'completed': return '#166534';
      case 'failed': return '#991b1b';
      case 'pending': return '#92400e';
      default: return '#9A9A96';
    }
  };

  const filteredActions = activeTab === 'failed'
    ? actions.filter(a => a.status === 'failed')
    : activeTab === 'completed'
    ? actions.filter(a => a.status === 'completed')
    : actions;

  const completedCount = actions.filter(a => a.status === 'completed').length;
  const failedCount = actions.filter(a => a.status === 'failed').length;

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
          <p style={styles.errorHint}>Make sure the server is running on port {FLASK_PORT}</p>
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
        <div style={styles.titleRow}>
          <h1 style={styles.title}>Actions History</h1>
          {isRefreshing && (
            <div style={styles.refreshingIndicator}>
              <div style={styles.refreshingSpinner}></div>
              <span>Refreshing...</span>
            </div>
          )}
        </div>
        <p style={styles.subtitle}>
          View all actions executed by Covalent ({actions.length} actions)
        </p>
      </div>

      <div style={styles.tabContainer}>
        {([
          { id: 'completed' as TabType, label: `Successful (${completedCount})` },
          { id: 'failed' as TabType, label: `Failed (${failedCount})` },
          { id: 'all' as TabType, label: 'All Actions' },
        ]).map(({ id, label }) => (
          <button
            key={id}
            style={{
              ...styles.tab,
              ...(activeTab === id
                ? id === 'failed'
                  ? styles.tabActiveFailed
                  : styles.tabActive
                : {}),
            }}
            onClick={() => setActiveTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {filteredActions.length > 0 ? (
        <div style={styles.actionsList}>
          {filteredActions.map((action) => {
            const isExpanded = expandedId === action.id;
            const actionData = parseJson(action.action_data);

            return (
              <div
                key={action.id}
                style={{
                  ...styles.actionCard,
                  ...(isExpanded ? styles.actionCardExpanded : {}),
                }}
                onClick={() => setExpandedId(isExpanded ? null : action.id)}
              >
                <div style={styles.actionHeader}>
                  <div style={styles.actionInfo}>
                    <span style={styles.actionType}>{formatActionType(action.action_type)}</span>
                    <span style={{ ...styles.statusBadge, ...getStatusStyle(action.status) }}>
                      {action.status}
                    </span>
                  </div>
                  <div style={styles.actionMeta}>
                    <span style={styles.duration}>{formatDuration(action.duration_ms)}</span>
                    <span style={styles.timestamp}>{formatTimestamp(action.creation_timestamp)}</span>
                  </div>
                </div>

                {action.status === 'failed' && action.error_message && (
                  <div style={styles.errorBox}>
                    <span style={styles.errorLabel}>Error:</span>
                    <span style={styles.errorMessage}>{action.error_message}</span>
                  </div>
                )}

                {isExpanded && (
                  <div style={styles.expandedContent}>
                    {actionData && (
                      <div style={styles.detailSection}>
                        <h4 style={styles.detailTitle}>Action Details</h4>
                        <div style={styles.detailBox}>
                          {formatActionData(actionData)}
                        </div>
                      </div>
                    )}

                    <div style={styles.detailSection}>
                      <h4 style={styles.detailTitle}>Result</h4>
                      <div style={{ ...styles.resultMessage, color: getResultColor(action.status) }}>
                        {formatResultMessage(action.status, action.result)}
                      </div>
                    </div>
                  </div>
                )}

                <div style={styles.expandHint}>
                  {isExpanded ? '▲ Collapse' : '▼ Expand'}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div style={styles.emptyState}>
          <h3 style={styles.emptyTitle}>
            {activeTab === 'failed' ? 'No Failed Actions' :
             activeTab === 'completed' ? 'No Successful Actions' : 'No Actions Yet'}
          </h3>
          <p style={styles.emptyText}>
            {activeTab === 'failed'
              ? 'Great news — no actions have failed recently.'
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
    maxWidth: '960px',
  },
  header: {
    marginBottom: '20px',
  },
  titleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '14px',
  },
  title: {
    fontSize: '1.6rem',
    fontWeight: '700',
    color: '#1A1A1A',
    margin: '0 0 6px 0',
    letterSpacing: '-0.02em',
  },
  refreshingIndicator: {
    display: 'flex',
    alignItems: 'center',
    gap: '7px',
    fontSize: '0.775rem',
    color: '#C17A5F',
    padding: '4px 12px',
    backgroundColor: 'rgba(193, 122, 95, 0.08)',
    border: '1px solid rgba(193, 122, 95, 0.25)',
    borderRadius: '100px',
    marginBottom: '6px',
  },
  refreshingSpinner: {
    width: '11px',
    height: '11px',
    border: '2px solid rgba(193, 122, 95, 0.3)',
    borderTopColor: '#C17A5F',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  subtitle: {
    fontSize: '0.875rem',
    color: '#5A5A5A',
    margin: 0,
  },
  tabContainer: {
    display: 'flex',
    gap: '6px',
    marginBottom: '20px',
    paddingBottom: '16px',
    borderBottom: '1px solid #E8E4DC',
  },
  tab: {
    padding: '8px 16px',
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
  tabActive: {
    backgroundColor: '#1A1A1A',
    borderColor: '#1A1A1A',
    color: '#FFFFFF',
  },
  tabActiveFailed: {
    backgroundColor: 'rgba(239, 68, 68, 0.06)',
    borderColor: 'rgba(239, 68, 68, 0.3)',
    color: '#991b1b',
  },
  actionsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    marginBottom: '20px',
  },
  actionCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: '12px',
    padding: '16px 20px',
    border: '1px solid #E8E4DC',
    cursor: 'pointer',
    transition: 'border-color 0.15s ease, box-shadow 0.15s ease',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
  },
  actionCardExpanded: {
    borderColor: '#D4CFC6',
    boxShadow: '0 4px 12px rgba(0,0,0,0.07)',
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
    gap: '10px',
  },
  actionType: {
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#1A1A1A',
  },
  statusBadge: {
    fontSize: '0.7rem',
    fontWeight: '700',
    padding: '3px 9px',
    borderRadius: '100px',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  },
  actionMeta: {
    display: 'flex',
    alignItems: 'center',
    gap: '14px',
    flexShrink: 0,
  },
  duration: {
    fontSize: '0.8rem',
    fontWeight: '600',
    color: '#C17A5F',
    fontFamily: 'monospace',
  },
  timestamp: {
    fontSize: '0.775rem',
    color: '#9A9A96',
  },
  errorBox: {
    marginTop: '10px',
    padding: '10px 14px',
    backgroundColor: 'rgba(239, 68, 68, 0.06)',
    borderRadius: '8px',
    border: '1px solid rgba(239, 68, 68, 0.18)',
  },
  errorLabel: {
    fontSize: '0.775rem',
    fontWeight: '700',
    color: '#991b1b',
    marginRight: '8px',
  },
  errorMessage: {
    fontSize: '0.825rem',
    color: '#991b1b',
    fontFamily: 'monospace',
  },
  expandedContent: {
    marginTop: '14px',
    paddingTop: '14px',
    borderTop: '1px solid #E8E4DC',
  },
  detailSection: {
    marginBottom: '14px',
  },
  detailTitle: {
    fontSize: '0.72rem',
    fontWeight: '700',
    color: '#9A9A96',
    margin: '0 0 8px 0',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
  },
  detailBox: {
    backgroundColor: '#F4F1EC',
    borderRadius: '8px',
    padding: '14px',
    border: '1px solid #E8E4DC',
  },
  dataGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
  },
  dataRow: {
    display: 'flex',
    flexDirection: 'column',
    gap: '3px',
  },
  dataKey: {
    fontSize: '0.7rem',
    fontWeight: '700',
    color: '#9A9A96',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  },
  dataValue: {
    fontSize: '0.875rem',
    color: '#1A1A1A',
    lineHeight: '1.5',
    wordBreak: 'break-word',
  },
  resultMessage: {
    fontSize: '0.875rem',
    lineHeight: '1.55',
    padding: '12px 16px',
    backgroundColor: '#F4F1EC',
    borderRadius: '8px',
    border: '1px solid #E8E4DC',
  },
  expandHint: {
    marginTop: '10px',
    fontSize: '0.68rem',
    color: '#D4CFC6',
    textAlign: 'center',
  },
  emptyState: {
    backgroundColor: '#FFFFFF',
    borderRadius: '14px',
    padding: '56px 32px',
    border: '1px solid #E8E4DC',
    textAlign: 'center',
    marginBottom: '20px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
  },
  emptyTitle: {
    fontSize: '1.1rem',
    fontWeight: '700',
    color: '#1A1A1A',
    marginBottom: '10px',
    marginTop: 0,
    letterSpacing: '-0.01em',
  },
  emptyText: {
    fontSize: '0.875rem',
    color: '#9A9A96',
    lineHeight: '1.6',
    margin: 0,
  },
  errorState: {
    backgroundColor: '#FFFFFF',
    borderRadius: '14px',
    padding: '32px',
    border: '1px solid rgba(239, 68, 68, 0.22)',
    textAlign: 'center',
  },
  errorText: {
    color: '#991b1b',
    marginBottom: '6px',
    fontSize: '0.9rem',
  },
  errorHint: {
    color: '#9A9A96',
    marginBottom: '16px',
    fontSize: '0.825rem',
  },
  loadingContainer: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '64px',
    gap: '14px',
  },
  spinner: {
    width: '28px',
    height: '28px',
    border: '3px solid #E8E4DC',
    borderTopColor: '#1A1A1A',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
  },
  loadingText: {
    color: '#9A9A96',
    fontSize: '0.9rem',
  },
  actionButtons: {
    display: 'flex',
    gap: '10px',
  },
  refreshButton: {
    padding: '9px 20px',
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
};

// Add keyframes for spinner
const styleSheet = document.createElement('style');
styleSheet.textContent = `@keyframes spin { to { transform: rotate(360deg); } }`;
if (!document.head.querySelector('style[data-history-page]')) {
  styleSheet.setAttribute('data-history-page', 'true');
  document.head.appendChild(styleSheet);
}

export default HistoryPage;
