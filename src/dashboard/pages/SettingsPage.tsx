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
      console.log('✅ Saved excluded apps');
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
                {tabCompletionEnabled ? 'Active — predictions will appear as you type' : 'Inactive — no predictions will be generated'}
              </div>
            </div>
            <button
              onClick={handleTabCompletionToggle}
              disabled={tabCompletionLoading}
              style={{
                ...styles.toggleTrack,
                backgroundColor: tabCompletionEnabled ? '#C5F467' : '#27272a',
                opacity: tabCompletionLoading ? 0.6 : 1,
                cursor: tabCompletionLoading ? 'not-allowed' : 'pointer',
              }}
              aria-label={tabCompletionEnabled ? 'Disable tab autocomplete' : 'Enable tab autocomplete'}
            >
              <div
                style={{
                  ...styles.toggleThumb,
                  transform: tabCompletionEnabled ? 'translateX(22px)' : 'translateX(2px)',
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
              style={styles.addButton}
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
            <div style={styles.savingIndicator}>
              Saving...
            </div>
          )}
        </div>

        <div style={styles.quickAddSection}>
          <h3 style={styles.quickAddTitle}>Quick Add Common Apps</h3>
          <div style={styles.quickAddGrid}>
            {commonApps.map((app) => (
              <button
                key={app}
                onClick={() => handleQuickAdd(app)}
                disabled={excludedApps.includes(app)}
                style={{
                  ...styles.quickAddButton,
                  ...(excludedApps.includes(app) ? styles.quickAddButtonDisabled : {}),
                }}
              >
                {app}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

const styles = {
  container: {
    padding: '40px',
    maxWidth: '900px',
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
  section: {
    marginBottom: '32px',
  },
  sectionTitle: {
    fontSize: '1.15rem',
    fontWeight: '600',
    color: '#ffffff',
    marginBottom: '8px',
    letterSpacing: '-0.01em',
  },
  sectionDescription: {
    fontSize: '0.9rem',
    color: '#a1a1aa',
    marginBottom: '24px',
    lineHeight: '1.6',
  },
  card: {
    backgroundColor: '#141414',
    borderRadius: '12px',
    padding: '24px',
    border: '1px solid #27272a',
    marginBottom: '24px',
  },
  cardTitle: {
    fontSize: '1rem',
    fontWeight: '500',
    color: '#ffffff',
    marginBottom: '20px',
  },
  inputGroup: {
    display: 'flex',
    gap: '12px',
    marginBottom: '24px',
  },
  input: {
    flex: 1,
    padding: '10px 14px',
    backgroundColor: '#111111',
    border: '1px solid #27272a',
    borderRadius: '8px',
    color: '#ffffff',
    fontSize: '0.9rem',
    outline: 'none',
  },
  addButton: {
    padding: '10px 20px',
    backgroundColor: '#C5F467',
    border: 'none',
    borderRadius: '8px',
    color: '#0a0a0a',
    fontSize: '0.9rem',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  appList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '8px',
  },
  appItem: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 16px',
    backgroundColor: '#1a1a1a',
    borderRadius: '8px',
    border: '1px solid #27272a',
  },
  appName: {
    color: '#ffffff',
    fontSize: '0.9rem',
  },
  removeButton: {
    padding: '6px 12px',
    backgroundColor: 'transparent',
    border: '1px solid #27272a',
    borderRadius: '6px',
    color: '#a1a1aa',
    fontSize: '0.8rem',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    fontWeight: '500',
  },
  emptyState: {
    padding: '32px',
    textAlign: 'center' as const,
  },
  emptyText: {
    color: '#71717a',
    fontSize: '0.85rem',
  },
  savingIndicator: {
    marginTop: '16px',
    padding: '8px 16px',
    backgroundColor: 'rgba(197, 244, 103, 0.1)',
    borderRadius: '8px',
    color: '#a1a1aa',
    fontSize: '0.8rem',
    textAlign: 'center' as const,
  },
  quickAddSection: {
    marginTop: '28px',
  },
  quickAddTitle: {
    fontSize: '0.95rem',
    fontWeight: '500',
    color: '#ffffff',
    marginBottom: '16px',
  },
  quickAddGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
    gap: '10px',
  },
  quickAddButton: {
    padding: '10px 14px',
    backgroundColor: '#1a1a1a',
    border: '1px solid #27272a',
    borderRadius: '8px',
    color: '#a1a1aa',
    fontSize: '0.85rem',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  quickAddButtonDisabled: {
    opacity: 0.3,
    cursor: 'not-allowed',
  },
  loadingText: {
    color: '#a1a1aa',
    fontSize: '0.95rem',
  },
  toggleRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '16px',
  },
  toggleLabel: {
    fontSize: '0.95rem',
    fontWeight: '500' as const,
    color: '#ffffff',
    marginBottom: '4px',
  },
  toggleDescription: {
    fontSize: '0.85rem',
    color: '#71717a',
    lineHeight: '1.5',
  },
  toggleTrack: {
    flexShrink: 0,
    width: '48px',
    height: '28px',
    borderRadius: '14px',
    border: 'none',
    padding: 0,
    position: 'relative' as const,
    transition: 'background-color 0.2s ease',
  },
  toggleThumb: {
    position: 'absolute' as const,
    top: '3px',
    width: '22px',
    height: '22px',
    borderRadius: '50%',
    backgroundColor: '#ffffff',
    boxShadow: '0 1px 4px rgba(0,0,0,0.3)',
    transition: 'transform 0.2s ease',
  },
};

export default SettingsPage;
