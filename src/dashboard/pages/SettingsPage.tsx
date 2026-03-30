import React, { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';

const SettingsPage: React.FC = () => {
  const [excludedApps, setExcludedApps] = useState<string[]>([]);
  const [newApp, setNewApp] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [tabCompletionEnabled, setTabCompletionEnabled] = useState(false);
  const [tabCompletionLoading, setTabCompletionLoading] = useState(false);

  useEffect(() => {
    loadExcludedApps();
    loadTabCompletionStatus();
  }, []);

  const loadTabCompletionStatus = async () => {
    try {
      const status = await invoke<boolean>('get_tab_completion_status');
      setTabCompletionEnabled(status);
    } catch (error) {
      console.error('Failed to get tab completion status:', error);
    }
  };

  const handleTabCompletionToggle = async () => {
    setTabCompletionLoading(true);
    try {
      const newState = await invoke<boolean>('toggle_tab_completion');
      setTabCompletionEnabled(newState);
    } catch (error) {
      console.error('Failed to toggle tab completion:', error);
    } finally {
      setTabCompletionLoading(false);
    }
  };

  const loadExcludedApps = async () => {
    try {
      const apps = await invoke<string[]>('get_excluded_apps');
      setExcludedApps(apps);
    } catch (error) {
      console.error('Failed to load excluded apps:', error);
    } finally {
      setLoading(false);
    }
  };

  const saveExcludedApps = async (apps: string[]) => {
    setSaving(true);
    try {
      await invoke('set_excluded_apps', { apps });
    } catch (error) {
      console.error('Failed to save excluded apps:', error);
    } finally {
      setSaving(false);
    }
  };

  const handleAddApp = () => {
    if (newApp.trim() && !excludedApps.includes(newApp.trim())) {
      const updated = [...excludedApps, newApp.trim()];
      setExcludedApps(updated);
      saveExcludedApps(updated);
      setNewApp('');
    }
  };

  const handleRemoveApp = (app: string) => {
    const updated = excludedApps.filter((a) => a !== app);
    setExcludedApps(updated);
    saveExcludedApps(updated);
  };

  const commonApps = [
    'Passwords',
    'Keychain Access',
    'Mail',
    'Messages',
    'Calendar',
    'Contacts',
    'Notes',
    'Reminders',
    '1Password',
    'Bitwarden',
  ];

  const handleQuickAdd = (app: string) => {
    if (!excludedApps.includes(app)) {
      const updated = [...excludedApps, app];
      setExcludedApps(updated);
      saveExcludedApps(updated);
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
        <h1 style={styles.title}>Settings</h1>
        <p style={styles.subtitle}>Configure privacy and monitoring preferences</p>
      </div>

      <div style={styles.section}>
        <h2 style={styles.sectionTitle}>Tab Autocomplete</h2>
        <p style={styles.sectionDescription}>
          Enable inline text predictions as you type. When enabled, Covalent will suggest completions based on your current context.
        </p>
        <div style={styles.card}>
          <div style={styles.toggleRow}>
            <div>
              <div style={styles.toggleLabel}>Tab Autocomplete</div>
              <div style={styles.toggleDescription}>
                {tabCompletionEnabled
                  ? 'Active — predictions will appear as you type'
                  : 'Inactive — no predictions will be generated'}
              </div>
            </div>
            <button
              onClick={handleTabCompletionToggle}
              disabled={tabCompletionLoading}
              style={{
                ...styles.toggleTrack,
                backgroundColor: tabCompletionEnabled ? '#1A1A1A' : '#D4CFC6',
                opacity: tabCompletionLoading ? 0.6 : 1,
                cursor: tabCompletionLoading ? 'not-allowed' : 'pointer',
              }}
              aria-label={tabCompletionEnabled ? 'Disable tab autocomplete' : 'Enable tab autocomplete'}
            >
              <div
                style={{
                  ...styles.toggleThumb,
                  transform: tabCompletionEnabled ? 'translateX(20px)' : 'translateX(2px)',
                }}
              />
            </button>
          </div>
        </div>
      </div>

      <div style={styles.section}>
        <h2 style={styles.sectionTitle}>Privacy Settings</h2>
        <p style={styles.sectionDescription}>
          Exclude specific applications from being monitored by Covalent. These apps will not be analyzed
          for context or action suggestions.
        </p>

        <div style={styles.card}>
          <h3 style={styles.cardTitle}>Excluded Applications</h3>

          <div style={styles.inputGroup}>
            <input
              type="text"
              value={newApp}
              onChange={(e) => setNewApp(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleAddApp()}
              placeholder="Enter app name (e.g., Chrome, Slack)"
              style={styles.input}
            />
            <button
              onClick={handleAddApp}
              disabled={!newApp.trim()}
              style={{
                ...styles.addButton,
                opacity: !newApp.trim() ? 0.45 : 1,
                cursor: !newApp.trim() ? 'not-allowed' : 'pointer',
              }}
            >
              Add
            </button>
          </div>

          {excludedApps.length > 0 ? (
            <div style={styles.appList}>
              {excludedApps.map((app) => (
                <div key={app} style={styles.appItem}>
                  <span style={styles.appName}>{app}</span>
                  <button
                    onClick={() => handleRemoveApp(app)}
                    style={styles.removeButton}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.backgroundColor = '#EDE9E2';
                      e.currentTarget.style.color = '#1A1A1A';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.backgroundColor = 'transparent';
                      e.currentTarget.style.color = '#9A9A96';
                    }}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div style={styles.emptyState}>
              <p style={styles.emptyText}>No excluded apps. All applications are being monitored.</p>
            </div>
          )}

          {saving && (
            <div style={styles.savingIndicator}>Saving...</div>
          )}
        </div>

        <div style={styles.quickAddSection}>
          <h3 style={styles.quickAddTitle}>Quick Add Common Apps</h3>
          <div style={styles.quickAddGrid}>
            {commonApps.map((app) => {
              const added = excludedApps.includes(app);
              return (
                <button
                  key={app}
                  onClick={() => handleQuickAdd(app)}
                  disabled={added}
                  style={{
                    ...styles.quickAddButton,
                    ...(added ? styles.quickAddButtonDisabled : {}),
                  }}
                  onMouseEnter={(e) => {
                    if (!added) {
                      e.currentTarget.style.backgroundColor = '#EDE9E2';
                      e.currentTarget.style.borderColor = '#D4CFC6';
                      e.currentTarget.style.color = '#1A1A1A';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!added) {
                      e.currentTarget.style.backgroundColor = '#FAFAF8';
                      e.currentTarget.style.borderColor = '#E8E4DC';
                      e.currentTarget.style.color = '#5A5A5A';
                    }
                  }}
                >
                  {app}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};

const styles: { [key: string]: React.CSSProperties } = {
  container: {
    padding: '40px',
    maxWidth: '860px',
  },
  header: {
    marginBottom: '32px',
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
    lineHeight: '1.5',
  },
  section: {
    marginBottom: '36px',
  },
  sectionTitle: {
    fontSize: '1rem',
    fontWeight: '700',
    color: '#1A1A1A',
    marginBottom: '6px',
    letterSpacing: '-0.01em',
  },
  sectionDescription: {
    fontSize: '0.875rem',
    color: '#5A5A5A',
    marginBottom: '16px',
    lineHeight: '1.6',
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: '14px',
    padding: '22px',
    border: '1px solid #E8E4DC',
    marginBottom: '16px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
  },
  cardTitle: {
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#1A1A1A',
    marginBottom: '16px',
    marginTop: 0,
  },
  inputGroup: {
    display: 'flex',
    gap: '10px',
    marginBottom: '20px',
  },
  input: {
    flex: 1,
    padding: '10px 14px',
    backgroundColor: '#F4F1EC',
    border: '1px solid #E8E4DC',
    borderRadius: '100px',
    color: '#1A1A1A',
    fontSize: '0.875rem',
    outline: 'none',
    fontFamily: 'inherit',
    transition: 'border-color 0.15s ease',
  },
  addButton: {
    padding: '10px 20px',
    backgroundColor: '#1A1A1A',
    border: 'none',
    borderRadius: '100px',
    color: '#FFFFFF',
    fontSize: '0.875rem',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
    fontFamily: 'inherit',
  },
  appList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  appItem: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 14px',
    backgroundColor: '#FAFAF8',
    borderRadius: '10px',
    border: '1px solid #E8E4DC',
  },
  appName: {
    color: '#1A1A1A',
    fontSize: '0.875rem',
    fontWeight: '500',
  },
  removeButton: {
    padding: '4px 10px',
    backgroundColor: 'transparent',
    border: '1px solid #E8E4DC',
    borderRadius: '100px',
    color: '#9A9A96',
    fontSize: '0.75rem',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
    fontWeight: '600',
    fontFamily: 'inherit',
  },
  emptyState: {
    padding: '28px',
    textAlign: 'center',
  },
  emptyText: {
    color: '#9A9A96',
    fontSize: '0.85rem',
    margin: 0,
  },
  savingIndicator: {
    marginTop: '12px',
    padding: '8px 16px',
    backgroundColor: '#F4F1EC',
    borderRadius: '100px',
    color: '#9A9A96',
    fontSize: '0.8rem',
    textAlign: 'center',
    display: 'inline-block',
  },
  quickAddSection: {
    marginTop: '24px',
  },
  quickAddTitle: {
    fontSize: '0.72rem',
    fontWeight: '700',
    color: '#9A9A96',
    marginBottom: '12px',
    marginTop: 0,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.06em',
  },
  quickAddGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))',
    gap: '8px',
  },
  quickAddButton: {
    padding: '9px 14px',
    backgroundColor: '#FAFAF8',
    border: '1px solid #E8E4DC',
    borderRadius: '100px',
    color: '#5A5A5A',
    fontSize: '0.825rem',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
    fontFamily: 'inherit',
    fontWeight: '500',
  },
  quickAddButtonDisabled: {
    opacity: 0.35,
    cursor: 'not-allowed',
  },
  loadingText: {
    color: '#9A9A96',
    fontSize: '0.9rem',
  },
  toggleRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '16px',
  },
  toggleLabel: {
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#1A1A1A',
    marginBottom: '3px',
  },
  toggleDescription: {
    fontSize: '0.825rem',
    color: '#9A9A96',
    lineHeight: '1.5',
  },
  toggleTrack: {
    flexShrink: 0,
    width: '44px',
    height: '26px',
    borderRadius: '13px',
    border: 'none',
    padding: 0,
    position: 'relative',
    transition: 'background-color 0.2s ease',
  },
  toggleThumb: {
    position: 'absolute',
    top: '3px',
    width: '20px',
    height: '20px',
    borderRadius: '50%',
    backgroundColor: '#FFFFFF',
    boxShadow: '0 1px 4px rgba(0,0,0,0.2)',
    transition: 'transform 0.2s ease',
  },
};

export default SettingsPage;
