import React, { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';

const SettingsPage: React.FC = () => {
  const [excludedApps, setExcludedApps] = useState<string[]>([]);
  const [newApp, setNewApp] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadExcludedApps();
  }, []);

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
    color: '#FFFFFF',
    margin: '0 0 8px 0',
    letterSpacing: '-0.02em',
  },
  subtitle: {
    fontSize: '0.95rem',
    color: 'rgba(255, 255, 255, 0.5)',
    margin: 0,
  },
  section: {
    marginBottom: '32px',
  },
  sectionTitle: {
    fontSize: '1.15rem',
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: '8px',
    letterSpacing: '-0.01em',
  },
  sectionDescription: {
    fontSize: '0.9rem',
    color: 'rgba(255, 255, 255, 0.5)',
    marginBottom: '24px',
    lineHeight: '1.6',
  },
  card: {
    backgroundColor: 'rgba(20, 20, 30, 0.6)',
    borderRadius: '12px',
    padding: '24px',
    border: '1px solid rgba(255, 255, 255, 0.06)',
    marginBottom: '24px',
  },
  cardTitle: {
    fontSize: '1rem',
    fontWeight: '500',
    color: '#FFFFFF',
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
    backgroundColor: 'rgba(15, 15, 25, 0.8)',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    borderRadius: '8px',
    color: '#FFFFFF',
    fontSize: '0.9rem',
    outline: 'none',
  },
  addButton: {
    padding: '10px 20px',
    backgroundColor: '#6366F1',
    border: 'none',
    borderRadius: '8px',
    color: '#FFFFFF',
    fontSize: '0.9rem',
    fontWeight: '500',
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
    backgroundColor: 'rgba(30, 30, 45, 0.5)',
    borderRadius: '8px',
    border: '1px solid rgba(255, 255, 255, 0.05)',
  },
  appName: {
    color: 'rgba(255, 255, 255, 0.85)',
    fontSize: '0.9rem',
  },
  removeButton: {
    padding: '6px 12px',
    backgroundColor: 'transparent',
    border: '1px solid rgba(239, 68, 68, 0.4)',
    borderRadius: '6px',
    color: 'rgba(239, 68, 68, 0.9)',
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
    color: 'rgba(255, 255, 255, 0.4)',
    fontSize: '0.85rem',
  },
  savingIndicator: {
    marginTop: '16px',
    padding: '8px 16px',
    backgroundColor: 'rgba(99, 102, 241, 0.15)',
    borderRadius: '8px',
    color: 'rgba(255, 255, 255, 0.7)',
    fontSize: '0.8rem',
    textAlign: 'center' as const,
  },
  quickAddSection: {
    marginTop: '28px',
  },
  quickAddTitle: {
    fontSize: '0.95rem',
    fontWeight: '500',
    color: 'rgba(255, 255, 255, 0.8)',
    marginBottom: '16px',
  },
  quickAddGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
    gap: '10px',
  },
  quickAddButton: {
    padding: '10px 14px',
    backgroundColor: 'rgba(30, 30, 45, 0.5)',
    border: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: '8px',
    color: 'rgba(255, 255, 255, 0.7)',
    fontSize: '0.85rem',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  quickAddButtonDisabled: {
    opacity: 0.3,
    cursor: 'not-allowed',
  },
  loadingText: {
    color: 'rgba(255, 255, 255, 0.6)',
    fontSize: '0.95rem',
  },
};

export default SettingsPage;
