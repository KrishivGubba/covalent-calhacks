import React, { useCallback, useEffect, useState } from 'react';
import { listen } from '@tauri-apps/api/event';
import { loadAuthStatus } from '../../shared/authService';
import { BACKEND_URL } from '../../shared/backend';
import { formatSystemTimestamp } from '../../shared/dateTime';
import { getOnboardingProfile } from '../../shared/onboardingProfileService';

interface DashboardPageProps {
  onOpenHistory?: () => void;
  onOpenProfile?: () => void;
}

interface ActionHistoryItem {
  id: number;
  action_type: string;
  creation_timestamp: string;
  status: string;
  duration_ms: number | null;
}

function formatActionType(actionType: string): string {
  if (!actionType) return 'Unknown Action';
  return actionType
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

function formatTimestamp(timestamp: string): string {
  try {
    return formatSystemTimestamp(timestamp, {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });
  } catch {
    return timestamp;
  }
}

function formatDuration(ms: number | null): string {
  if (ms === null || ms === undefined) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function toDisplayName(rawName: string | null | undefined): string {
  if (!rawName) return 'there';
  const trimmed = rawName.trim();
  if (!trimmed) return 'there';
  const emailLocalPart = trimmed.includes('@') ? trimmed.split('@')[0] : trimmed;
  const firstChunk = emailLocalPart.split(/[.\s_-]+/)[0];
  if (!firstChunk) return 'there';
  return firstChunk.charAt(0).toUpperCase() + firstChunk.slice(1);
}

const DashboardPage: React.FC<DashboardPageProps> = ({ onOpenHistory, onOpenProfile }) => {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState('there');
  const [recentActions, setRecentActions] = useState<ActionHistoryItem[]>([]);

  const loadDashboardData = useCallback(async (backgroundRefresh = false) => {
    if (backgroundRefresh) setRefreshing(true);
    else setLoading(true);

    setError(null);

    try {
      const [profile, authStatus] = await Promise.all([
        getOnboardingProfile().catch(() => null),
        loadAuthStatus().catch(() => null),
      ]);

      const resolvedName = profile?.name || authStatus?.user || null;
      setDisplayName(toDisplayName(resolvedName));

      const response = await fetch(`${BACKEND_URL}/action_history?limit=6`);
      if (!response.ok) {
        throw new Error(`Failed to fetch action history: HTTP ${response.status}`);
      }

      const data = (await response.json()) as { history?: ActionHistoryItem[] };
      setRecentActions(data.history ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load dashboard');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboardData();
  }, [loadDashboardData]);

  useEffect(() => {
    const unlistenPromise = listen('action-completed', () => {
      void loadDashboardData(true);
    });

    return () => {
      unlistenPromise.then((fn) => fn());
    };
  }, [loadDashboardData]);

  const completedCount = recentActions.filter((action) => action.status === 'completed').length;
  const failedCount = recentActions.filter((action) => action.status === 'failed').length;

  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.loadingText}>Loading dashboard...</div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.heroCard}>
        <h1 style={styles.heroTitle}>Hi {displayName}, let&apos;s get working.</h1>
        <p style={styles.heroSubtitle}>
          Here&apos;s a quick view of your latest execution activity.
        </p>
        <div style={styles.heroActions}>
          <button style={styles.primaryButton} onClick={onOpenHistory}>
            View full history
          </button>
          <button style={styles.secondaryButton} onClick={onOpenProfile}>
            Edit profile
          </button>
        </div>
      </div>

      <div style={styles.statsRow}>
        <div style={styles.statCard}>
          <span style={styles.statLabel}>Recent Actions</span>
          <strong style={styles.statValue}>{recentActions.length}</strong>
        </div>
        <div style={styles.statCard}>
          <span style={styles.statLabel}>Successful</span>
          <strong style={styles.statValue}>{completedCount}</strong>
        </div>
        <div style={styles.statCard}>
          <span style={styles.statLabel}>Failed</span>
          <strong style={styles.statValue}>{failedCount}</strong>
        </div>
      </div>

      <div style={styles.sectionHeader}>
        <h2 style={styles.sectionTitle}>Recent Executions</h2>
        {refreshing && <span style={styles.refreshingLabel}>Refreshing...</span>}
      </div>

      {error && <div style={styles.errorBox}>{error}</div>}

      {recentActions.length > 0 ? (
        <div style={styles.list}>
          {recentActions.map((action) => (
            <div key={action.id} style={styles.listItem}>
              <div style={styles.listItemHead}>
                <strong style={styles.actionTitle}>{formatActionType(action.action_type)}</strong>
                <span
                  style={{
                    ...styles.statusBadge,
                    ...(action.status === 'completed'
                      ? styles.statusCompleted
                      : action.status === 'failed'
                      ? styles.statusFailed
                      : styles.statusPending),
                  }}
                >
                  {action.status}
                </span>
              </div>
              <div style={styles.metaRow}>
                <span>{formatTimestamp(action.creation_timestamp)}</span>
                <span>{formatDuration(action.duration_ms)}</span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div style={styles.emptyState}>
          No actions yet. Once Covalent executes actions, they will show up here.
        </div>
      )}
    </div>
  );
};

const styles: { [key: string]: React.CSSProperties } = {
  container: {
    padding: '40px',
    maxWidth: '940px',
  },
  loadingText: {
    color: '#9A9A96',
    fontSize: '0.9rem',
  },
  heroCard: {
    backgroundColor: '#FFFFFF',
    border: '1px solid #E8E4DC',
    borderRadius: '16px',
    padding: '28px',
    marginBottom: '20px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
  },
  heroTitle: {
    margin: 0,
    fontSize: '1.8rem',
    color: '#1A1A1A',
    letterSpacing: '-0.02em',
  },
  heroSubtitle: {
    margin: '10px 0 0 0',
    color: '#5A5A5A',
    fontSize: '0.95rem',
    lineHeight: '1.5',
  },
  heroActions: {
    display: 'flex',
    gap: '10px',
    marginTop: '18px',
  },
  primaryButton: {
    padding: '10px 18px',
    borderRadius: '100px',
    border: 'none',
    backgroundColor: '#1A1A1A',
    color: '#FFFFFF',
    fontWeight: '600',
    fontSize: '0.86rem',
    cursor: 'pointer',
    fontFamily: 'inherit',
  },
  secondaryButton: {
    padding: '10px 18px',
    borderRadius: '100px',
    border: '1px solid #E8E4DC',
    backgroundColor: '#FFFFFF',
    color: '#5A5A5A',
    fontWeight: '500',
    fontSize: '0.86rem',
    cursor: 'pointer',
    fontFamily: 'inherit',
  },
  statsRow: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
    gap: '12px',
    marginBottom: '24px',
  },
  statCard: {
    backgroundColor: '#FFFFFF',
    border: '1px solid #E8E4DC',
    borderRadius: '12px',
    padding: '14px 16px',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  statLabel: {
    color: '#7D7D78',
    fontSize: '0.8rem',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  statValue: {
    color: '#1A1A1A',
    fontSize: '1.2rem',
  },
  sectionHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '10px',
  },
  sectionTitle: {
    margin: 0,
    fontSize: '1.05rem',
    color: '#1A1A1A',
  },
  refreshingLabel: {
    color: '#9A9A96',
    fontSize: '0.8rem',
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
  list: {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
  },
  listItem: {
    backgroundColor: '#FFFFFF',
    border: '1px solid #E8E4DC',
    borderRadius: '12px',
    padding: '14px 16px',
  },
  listItemHead: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: '8px',
  },
  actionTitle: {
    fontSize: '0.92rem',
    color: '#1A1A1A',
  },
  statusBadge: {
    fontSize: '0.72rem',
    borderRadius: '999px',
    padding: '4px 8px',
    border: '1px solid transparent',
    textTransform: 'capitalize',
    fontWeight: '600',
  },
  statusCompleted: {
    color: '#166534',
    backgroundColor: 'rgba(34, 197, 94, 0.08)',
    borderColor: 'rgba(34, 197, 94, 0.22)',
  },
  statusFailed: {
    color: '#991b1b',
    backgroundColor: 'rgba(239, 68, 68, 0.06)',
    borderColor: 'rgba(239, 68, 68, 0.22)',
  },
  statusPending: {
    color: '#92400e',
    backgroundColor: 'rgba(245, 158, 11, 0.08)',
    borderColor: 'rgba(245, 158, 11, 0.22)',
  },
  metaRow: {
    marginTop: '10px',
    color: '#7D7D78',
    fontSize: '0.8rem',
    display: 'flex',
    justifyContent: 'space-between',
  },
  emptyState: {
    border: '1px dashed #D4CFC6',
    borderRadius: '12px',
    padding: '20px',
    color: '#7D7D78',
    fontSize: '0.88rem',
    backgroundColor: '#FFFFFF',
  },
};

export default DashboardPage;
