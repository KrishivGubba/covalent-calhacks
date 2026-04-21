import React, { useEffect, useMemo, useState } from 'react';
import { open } from '@tauri-apps/plugin-dialog';
import {
  connectFilesystem,
  connectOAuthIntegration,
  disconnectIntegration,
  fetchIntegrationsStatus,
  fetchJiraConfig,
  fetchLargeContextSyncStatus,
  listJiraProjects,
  runLargeContextIntegrationSync,
  updateLargeContextIntegrationConfig,
  updateJiraConfig,
  type LargeContextIntegrationStatus,
  type LargeContextSyncStatusResponse,
  type IntegrationStatus,
  type JiraConfigResponse,
  type JiraProject,
} from '../../shared/integrationService';
import { formatSystemTimestamp, getSystemTimeZone } from '../../shared/dateTime';

interface MCPPageProps {
  isAuthenticated: boolean;
}

type SyncDraft = {
  enabled: boolean;
  intervalMinutes: number;
};

const SYNC_INTERVAL_OPTIONS = [
  { label: '30 min', value: 30 },
  { label: '1 hour', value: 60 },
  { label: '2 hours', value: 120 },
  { label: '6 hours', value: 360 },
  { label: '12 hours', value: 720 },
  { label: '24 hours', value: 1440 },
];

const FAST_STATUS_POLL_MS = 1500;
const IDLE_STATUS_POLL_MS = 10000;

const FALLBACK_INTEGRATIONS: IntegrationStatus[] = [
  {
    id: 'filesystem',
    name: 'Filesystem',
    connected: false,
    description: 'Choose a folder to access local files and directories',
  },
  {
    id: 'github',
    name: 'GitHub',
    connected: false,
    description: 'Access repositories, issues, and pull requests',
  },
  {
    id: 'perplexity',
    name: 'Perplexity Search',
    connected: true,
    description: 'AI-powered web search',
    included: true,
  },
  {
    id: 'notion',
    name: 'Notion',
    connected: false,
    description: 'Access Notion workspaces and pages',
  },
  {
    id: 'google',
    name: 'Google Workspace',
    connected: false,
    description: 'Docs, Drive, Mail, Calendar',
  },
  {
    id: 'jira',
    name: 'Jira',
    connected: false,
    description: 'Access Jira projects, tickets, and workflows',
    configurable: true,
    configured: false,
    needs_configuration: false,
  },
];

const MCPPage: React.FC<MCPPageProps> = ({ isAuthenticated }) => {
  const [integrations, setIntegrations] = useState<IntegrationStatus[]>([]);
  const [largeContextStatus, setLargeContextStatus] = useState<LargeContextSyncStatusResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [connectingId, setConnectingId] = useState<string | null>(null);
  const [activeConfigId, setActiveConfigId] = useState<string | null>(null);
  const [syncTrayOpenId, setSyncTrayOpenId] = useState<string | null>(null);
  const [syncStartingId, setSyncStartingId] = useState<string | null>(null);
  const [syncSavingId, setSyncSavingId] = useState<string | null>(null);
  const [syncDrafts, setSyncDrafts] = useState<Record<string, SyncDraft>>({});
  const [jiraConfig, setJiraConfig] = useState<JiraConfigResponse | null>(null);
  const [jiraProjects, setJiraProjects] = useState<JiraProject[]>([]);
  const [jiraCloudId, setJiraCloudId] = useState('');
  const [jiraProjectKeys, setJiraProjectKeys] = useState<string[]>([]);
  const [jiraBusy, setJiraBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadPageData({ showLoader: true });
  }, []);

  const integrationSyncMap = useMemo(() => {
    const entries = (largeContextStatus?.integrations || []).map((integrationStatus) => [
      integrationStatus.integration_id,
      integrationStatus,
    ]);
    return Object.fromEntries(entries) as Record<string, LargeContextIntegrationStatus>;
  }, [largeContextStatus]);

  const anySyncRunning = useMemo(
    () => (largeContextStatus?.integrations || []).some((integrationStatus) => integrationStatus.status === 'running'),
    [largeContextStatus],
  );

  useEffect(() => {
    if (loading) return undefined;
    const timeout = window.setTimeout(() => {
      void loadPageData({ silent: true });
    }, anySyncRunning || syncStartingId ? FAST_STATUS_POLL_MS : IDLE_STATUS_POLL_MS);

    return () => window.clearTimeout(timeout);
  }, [anySyncRunning, largeContextStatus, loading, syncStartingId]);

  const loadPageData = async ({
    showLoader = false,
    silent = false,
  }: {
    showLoader?: boolean;
    silent?: boolean;
  } = {}) => {
    if (showLoader) {
      setLoading(true);
    }
    if (!silent) {
      setError(null);
    }
    try {
      const [statuses, syncStatus] = await Promise.all([
        fetchIntegrationsStatus(),
        fetchLargeContextSyncStatus(),
      ]);
      setIntegrations(statuses);
      setLargeContextStatus(syncStatus);
    } catch (e) {
      setIntegrations(FALLBACK_INTEGRATIONS);
      if (!silent) {
        setError(e instanceof Error ? e.message : 'Failed to fetch integrations');
      }
    } finally {
      if (showLoader) {
        setLoading(false);
      }
    }
  };

  const handleConnectFilesystem = async () => {
    const selected = await open({
      directory: true,
      multiple: false,
      title: 'Choose a folder for Covalent to access',
    });
    if (!selected) return;

    const rootPath = typeof selected === 'string' ? selected : selected[0];
    if (!rootPath) return;

    const result = await connectFilesystem(rootPath);
    if (!result.ok) throw new Error(result.error);
  };

  const loadJiraProjectsForCloudId = async (
    cloudId: string,
    selectedKeys: string[] = jiraProjectKeys,
  ) => {
    setJiraBusy(true);
    try {
      const projects = await listJiraProjects(cloudId);
      const validKeys = new Set(projects.map((project) => project.key));
      setJiraProjects(projects);
      setJiraProjectKeys(selectedKeys.filter((key) => validKeys.has(key)));
    } finally {
      setJiraBusy(false);
    }
  };

  const openJiraConfiguration = async () => {
    setError(null);
    setActiveConfigId('jira');
    setJiraBusy(true);
    try {
      const config = await fetchJiraConfig();
      const accessibleResources = config.config.accessible_resources || [];
      const initialCloudId =
        config.config.cloud_id || accessibleResources[0]?.cloud_id || '';
      setJiraConfig(config);
      setJiraCloudId(initialCloudId);
      setJiraProjectKeys(config.config.project_keys || []);
      if (initialCloudId) {
        await loadJiraProjectsForCloudId(initialCloudId, config.config.project_keys || []);
      } else {
        setJiraProjects([]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load Jira configuration');
    } finally {
      setJiraBusy(false);
    }
  };

  const handleConnect = async (id: string) => {
    setError(null);
    setConnectingId(id);
    try {
      if (id === 'filesystem') {
        await handleConnectFilesystem();
      } else if (id === 'google' || id === 'github' || id === 'notion' || id === 'jira') {
        const result = await connectOAuthIntegration(id);
        if (!result.ok) throw new Error(result.error);
        if (id === 'jira') {
          await openJiraConfiguration();
        }
      } else {
        throw new Error(`${id} integration is not supported yet`);
      }
      await loadPageData();
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to connect ${id}`);
    } finally {
      setConnectingId(null);
    }
  };

  const handleDisconnect = async (id: string) => {
    setError(null);
    setConnectingId(id);
    try {
      const ok = await disconnectIntegration(id);
      if (!ok) throw new Error(`Failed to disconnect ${id}`);
      if (id === 'jira') {
        setActiveConfigId(null);
        setJiraConfig(null);
        setJiraProjects([]);
        setJiraCloudId('');
        setJiraProjectKeys([]);
      }
      await loadPageData();
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to disconnect ${id}`);
    } finally {
      setConnectingId(null);
    }
  };

  const toggleJiraProjectKey = (projectKey: string) => {
    setJiraProjectKeys((prev) =>
      prev.includes(projectKey) ? prev.filter((key) => key !== projectKey) : [...prev, projectKey],
    );
  };

  const saveJiraConfiguration = async () => {
    if (!jiraCloudId) {
      setError('Select a Jira site before saving configuration.');
      return;
    }
    if (jiraProjectKeys.length === 0) {
      setError('Select at least one Jira project before saving configuration.');
      return;
    }

    setError(null);
    setJiraBusy(true);
    try {
      const config = await updateJiraConfig(jiraCloudId, jiraProjectKeys);
      setJiraConfig(config);
      await loadPageData();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save Jira configuration');
    } finally {
      setJiraBusy(false);
    }
  };

  const ensureSyncDraft = (integrationStatus: LargeContextIntegrationStatus) => {
    setSyncDrafts((prev) => {
      if (prev[integrationStatus.integration_id]) {
        return prev;
      }
      return {
        ...prev,
        [integrationStatus.integration_id]: {
          enabled: integrationStatus.enabled,
          intervalMinutes: integrationStatus.interval_minutes,
        },
      };
    });
  };

  const toggleSyncTray = (integrationStatus: LargeContextIntegrationStatus) => {
    ensureSyncDraft(integrationStatus);
    setSyncTrayOpenId((prev) =>
      prev === integrationStatus.integration_id ? null : integrationStatus.integration_id,
    );
  };

  const updateSyncDraft = (
    integrationId: string,
    partial: Partial<SyncDraft>,
  ) => {
    setSyncDrafts((prev) => ({
      ...prev,
      [integrationId]: {
        enabled: prev[integrationId]?.enabled ?? true,
        intervalMinutes: prev[integrationId]?.intervalMinutes ?? 60,
        ...partial,
      },
    }));
  };

  const saveSyncSettings = async (integrationStatus: LargeContextIntegrationStatus) => {
    const draft = syncDrafts[integrationStatus.integration_id] || {
      enabled: integrationStatus.enabled,
      intervalMinutes: integrationStatus.interval_minutes,
    };
    setError(null);
    setSyncSavingId(integrationStatus.integration_id);
    try {
      await updateLargeContextIntegrationConfig(
        integrationStatus.integration_id,
        draft.enabled,
        draft.intervalMinutes,
      );
      await loadPageData({ silent: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save sync settings');
    } finally {
      setSyncSavingId(null);
    }
  };

  const startManualSync = async (integrationStatus: LargeContextIntegrationStatus) => {
    setError(null);
    setSyncStartingId(integrationStatus.integration_id);
    try {
      const runPromise = runLargeContextIntegrationSync(integrationStatus.integration_id);
      await loadPageData({ silent: true });
      const result = await runPromise;
      if (!result.ok) {
        throw new Error(result.error);
      }
      await loadPageData({ silent: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start large context sync');
    } finally {
      setSyncStartingId(null);
    }
  };

  const renderLargeContextControls = (integration: IntegrationStatus) => {
    const integrationStatus = integrationSyncMap[integration.id];
    if (!integrationStatus) {
      return null;
    }
    const draft = syncDrafts[integrationStatus.integration_id] || {
      enabled: integrationStatus.enabled,
      intervalMinutes: integrationStatus.interval_minutes,
    };
    const trayOpen = syncTrayOpenId === integrationStatus.integration_id;
    const syncRunning =
      integrationStatus.status === 'running' || syncStartingId === integrationStatus.integration_id;
    const controlsDisabled =
      !integration.connected || connectingId === integration.id || syncSavingId === integrationStatus.integration_id;

    return (
      <div
        style={{
          ...styles.syncPanel,
          ...(integration.connected ? {} : styles.syncPanelDisabled),
        }}
      >
        <div style={styles.syncHeader}>
          <div>
            <div style={styles.syncTitle}>Large Context Sync</div>
            <div style={styles.syncSubtitle}>
              {integration.connected
                ? `Last sync on ${
                    integrationStatus.last_success_at
                      ? formatSystemTimestamp(integrationStatus.last_success_at, {
                          timeZoneName: 'short',
                        })
                      : 'Not synced yet'
                  }`
                : 'Connect this integration to enable large context sync'}
            </div>
            {integration.connected && integrationStatus.next_run_at && (
              <div style={styles.syncHint}>
                Next sync {formatSystemTimestamp(integrationStatus.next_run_at, { timeZoneName: 'short' })}
              </div>
            )}
          </div>
          <div
            style={{
              ...styles.syncStatusBadge,
              ...(syncRunning ? styles.syncStatusRunning : styles.syncStatusIdle),
            }}
          >
            {syncRunning ? (
              <>
                <span className="app-spinner" style={styles.spinner} />
                Syncing
              </>
            ) : (
              integrationStatus.enabled ? 'Auto-sync on' : 'Auto-sync off'
            )}
          </div>
        </div>

        {integration.connected && integrationStatus.last_error && integrationStatus.status === 'error' && (
          <div style={styles.syncErrorText}>{integrationStatus.last_error}</div>
        )}

        <div style={styles.syncActionRow}>
          <button
            style={{
              ...styles.syncButton,
              ...(syncRunning || controlsDisabled ? styles.buttonDisabled : {}),
            }}
            onClick={() => void startManualSync(integrationStatus)}
            disabled={syncRunning || controlsDisabled}
          >
            {syncRunning ? 'Syncing...' : 'Sync'}
          </button>
          <button
            style={{
              ...styles.syncTrayButton,
              ...(syncSavingId === integrationStatus.integration_id ? styles.buttonDisabled : {}),
            }}
            onClick={() => toggleSyncTray(integrationStatus)}
            disabled={syncSavingId === integrationStatus.integration_id}
          >
            {trayOpen ? 'Hide Settings' : 'Settings'}
          </button>
        </div>

        {trayOpen && (
          <div style={styles.syncTray}>
            <label style={styles.syncToggleRow}>
              <span style={styles.syncControlLabel}>Auto-sync</span>
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={(event) =>
                  updateSyncDraft(integrationStatus.integration_id, {
                    enabled: event.target.checked,
                  })
                }
                disabled={controlsDisabled}
              />
            </label>
            <label style={styles.syncField}>
              <span style={styles.syncControlLabel}>Cadence</span>
              <select
                style={styles.select}
                value={draft.intervalMinutes}
                onChange={(event) =>
                  updateSyncDraft(integrationStatus.integration_id, {
                    intervalMinutes: Number(event.target.value),
                  })
                }
                disabled={controlsDisabled}
              >
                {SYNC_INTERVAL_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <div style={styles.syncTrayFooter}>
              <span style={styles.syncTimeZoneText}>Times shown in {getSystemTimeZone()}</span>
              <button
                style={{
                  ...styles.configureButton,
                  ...(controlsDisabled ? styles.buttonDisabled : {}),
                }}
                onClick={() => void saveSyncSettings(integrationStatus)}
                disabled={controlsDisabled}
              >
                {syncSavingId === integrationStatus.integration_id ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderIntegrationMeta = (integration: IntegrationStatus) => {
    if (integration.id !== 'jira' || !integration.connected) {
      return null;
    }
    const siteName = integration.configuration?.site_name;
    const projectCount = integration.configuration?.project_count ?? 0;
    return (
      <div style={styles.metaList}>
        <div style={styles.metaRow}>
          <span style={styles.metaLabel}>Site</span>
          <span style={styles.metaValue}>{siteName || 'Not selected'}</span>
        </div>
        <div style={styles.metaRow}>
          <span style={styles.metaLabel}>Projects</span>
          <span style={styles.metaValue}>
            {integration.needs_configuration ? 'Configuration required' : `${projectCount} selected`}
          </span>
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.loadingText}>Loading...</div>
      </div>
    );
  }

  const jiraAccessibleResources = jiraConfig?.config.accessible_resources || [];
  const showingJiraConfiguration = activeConfigId === 'jira';

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h1 style={styles.title}>Integrations</h1>
        <p style={styles.subtitle}>Connect external services and tools</p>
      </div>

      {!isAuthenticated && (
        <div style={styles.loginPrompt}>
          Please log in on the Profile page to manage OAuth integrations.
        </div>
      )}

      {error && <div style={styles.errorBox}>{error}</div>}

      {!showingJiraConfiguration ? (
        <div style={styles.grid}>
          {integrations.map((integration) => (
            <div key={integration.id} style={styles.card}>
              <div style={styles.cardHeader}>
                <div style={styles.cardTitleRow}>
                  <h3 style={styles.cardTitle}>{integration.name}</h3>
                  <div
                    style={{
                      ...styles.statusText,
                      color: integration.connected ? '#166534' : '#B42318',
                    }}
                  >
                    {integration.connected ? 'Connected' : 'Not Connected'}
                  </div>
                </div>
                <p style={styles.cardDescription}>{integration.description}</p>
                {renderIntegrationMeta(integration)}
                {renderLargeContextControls(integration)}
              </div>

              <div style={styles.cardActions}>
                {integration.included ? (
                  <div style={styles.includedBadge}>Included</div>
                ) : !integration.connected ? (
                  <button
                    style={{
                      ...styles.connectButton,
                      ...((!isAuthenticated && integration.id !== 'filesystem') ||
                      connectingId === integration.id
                        ? styles.buttonDisabled
                        : {}),
                    }}
                    onClick={() => void handleConnect(integration.id)}
                    disabled={
                      (!isAuthenticated && integration.id !== 'filesystem') ||
                      connectingId === integration.id
                    }
                    title={
                      !isAuthenticated && integration.id !== 'filesystem'
                        ? 'Please log in first'
                        : undefined
                    }
                  >
                    {connectingId === integration.id
                      ? 'Connecting...'
                      : integration.id === 'filesystem'
                      ? 'Choose Folder'
                      : 'Connect'}
                  </button>
                ) : (
                  <>
                    {integration.configurable && (
                      <button
                        style={{
                          ...styles.configureButton,
                          ...(jiraBusy ? styles.buttonDisabled : {}),
                        }}
                        onClick={() => void openJiraConfiguration()}
                        disabled={jiraBusy}
                      >
                        Configure
                      </button>
                    )}
                    <button
                      style={{
                        ...styles.disconnectButton,
                        ...(isAuthenticated || integration.id === 'filesystem'
                          ? {}
                          : styles.buttonDisabled),
                      }}
                      onClick={() => void handleDisconnect(integration.id)}
                      disabled={!isAuthenticated && integration.id !== 'filesystem'}
                    >
                      {connectingId === integration.id ? 'Disconnecting...' : 'Disconnect'}
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div style={styles.configPanel}>
          <div style={styles.configHeader}>
            <div>
              <h2 style={styles.configTitle}>Configure Jira Context</h2>
              <p style={styles.configSubtitle}>
                Select the Jira site and project allowlist used for MCP actions and large context
                sync.
              </p>
            </div>
            <button
              style={styles.backButton}
              onClick={() => setActiveConfigId(null)}
              disabled={jiraBusy}
            >
              Back
            </button>
          </div>

          <div style={styles.configGroup}>
            <label style={styles.configLabel} htmlFor="jira-site-select">
              Jira Site
            </label>
            <select
              id="jira-site-select"
              style={styles.select}
              value={jiraCloudId}
              onChange={(event) => {
                const nextCloudId = event.target.value;
                setJiraCloudId(nextCloudId);
                void loadJiraProjectsForCloudId(nextCloudId, []);
              }}
              disabled={jiraBusy}
            >
              <option value="">Choose a Jira site</option>
              {jiraAccessibleResources.map((resource) => (
                <option key={resource.cloud_id} value={resource.cloud_id}>
                  {resource.site_name}
                </option>
              ))}
            </select>
          </div>

          <div style={styles.configGroup}>
            <div style={styles.projectHeader}>
              <div>
                <div style={styles.configLabel}>Projects</div>
                <div style={styles.projectHint}>
                  These projects will drive Jira.md snapshots and the live context graph.
                </div>
              </div>
              <div style={styles.selectionCount}>{jiraProjectKeys.length} selected</div>
            </div>

            <div style={styles.projectList}>
              {jiraProjects.length === 0 ? (
                <div style={styles.projectEmpty}>
                  {jiraCloudId
                    ? jiraBusy
                      ? 'Loading projects...'
                      : 'No Jira projects found for this site.'
                    : 'Choose a Jira site to load projects.'}
                </div>
              ) : (
                jiraProjects.map((project) => {
                  const checked = jiraProjectKeys.includes(project.key);
                  return (
                    <label key={project.id || project.key} style={styles.projectRow}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleJiraProjectKey(project.key)}
                        disabled={jiraBusy}
                      />
                      <div style={styles.projectText}>
                        <span style={styles.projectName}>{project.name}</span>
                        <span style={styles.projectKey}>{project.key}</span>
                      </div>
                    </label>
                  );
                })
              )}
            </div>
          </div>

          <div style={styles.configActions}>
            <button
              style={{
                ...styles.connectButton,
                ...(jiraBusy ? styles.buttonDisabled : {}),
              }}
              onClick={() => void saveJiraConfiguration()}
              disabled={jiraBusy}
            >
              {jiraBusy ? 'Saving...' : 'Save Jira Configuration'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

const styles: { [key: string]: React.CSSProperties } = {
  container: {
    padding: '40px',
    maxWidth: '1040px',
  },
  header: {
    marginBottom: '28px',
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
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(270px, 1fr))',
    gap: '14px',
    marginBottom: '28px',
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: '14px',
    padding: '20px',
    border: '1px solid #E8E4DC',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'space-between',
    minHeight: '188px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
    transition: 'box-shadow 0.15s ease, border-color 0.15s ease',
  },
  cardHeader: {
    marginBottom: '16px',
  },
  cardTitleRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '10px',
  },
  cardTitle: {
    fontSize: '0.95rem',
    fontWeight: '700',
    color: '#1A1A1A',
    margin: 0,
    letterSpacing: '-0.01em',
  },
  statusText: {
    fontSize: '0.74rem',
    fontWeight: '700',
    letterSpacing: '0.01em',
  },
  cardDescription: {
    fontSize: '0.825rem',
    color: '#5A5A5A',
    margin: 0,
    lineHeight: '1.5',
  },
  cardActions: {
    display: 'flex',
    gap: '8px',
  },
  connectButton: {
    flex: 1,
    padding: '9px 18px',
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
  configureButton: {
    flex: 1,
    padding: '9px 18px',
    backgroundColor: '#F6F2EA',
    border: '1px solid #E8E4DC',
    borderRadius: '100px',
    color: '#1A1A1A',
    fontSize: '0.825rem',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
    fontFamily: 'inherit',
  },
  disconnectButton: {
    flex: 1,
    padding: '9px 18px',
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
  buttonDisabled: {
    opacity: 0.45,
    cursor: 'not-allowed',
  },
  includedBadge: {
    flex: 1,
    padding: '9px 18px',
    backgroundColor: 'rgba(193, 122, 95, 0.08)',
    border: '1px solid rgba(193, 122, 95, 0.25)',
    borderRadius: '100px',
    color: '#C17A5F',
    fontSize: '0.825rem',
    fontWeight: '600',
    textAlign: 'center',
  },
  loadingText: {
    color: '#9A9A96',
    fontSize: '0.9rem',
  },
  loginPrompt: {
    backgroundColor: 'rgba(193, 122, 95, 0.08)',
    border: '1px solid rgba(193, 122, 95, 0.25)',
    borderRadius: '10px',
    padding: '12px 16px',
    color: '#C17A5F',
    fontSize: '0.875rem',
    marginBottom: '20px',
    textAlign: 'center',
  },
  errorBox: {
    backgroundColor: 'rgba(239, 68, 68, 0.06)',
    border: '1px solid rgba(239, 68, 68, 0.22)',
    borderRadius: '10px',
    padding: '12px 16px',
    color: '#991b1b',
    fontSize: '0.85rem',
    marginBottom: '16px',
  },
  metaList: {
    display: 'grid',
    gap: '6px',
    marginTop: '12px',
  },
  metaRow: {
    display: 'flex',
    justifyContent: 'space-between',
    gap: '12px',
    fontSize: '0.78rem',
  },
  metaLabel: {
    color: '#7A746B',
    fontWeight: 600,
  },
  metaValue: {
    color: '#312B24',
    textAlign: 'right',
  },
  configPanel: {
    backgroundColor: '#FFFFFF',
    borderRadius: '18px',
    border: '1px solid #E8E4DC',
    boxShadow: '0 4px 18px rgba(17, 17, 17, 0.05)',
    padding: '24px',
  },
  configHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: '20px',
    gap: '16px',
  },
  configTitle: {
    margin: 0,
    fontSize: '1.05rem',
    color: '#1A1A1A',
  },
  configSubtitle: {
    margin: '6px 0 0 0',
    fontSize: '0.88rem',
    color: '#5A5A5A',
    lineHeight: 1.5,
  },
  backButton: {
    padding: '9px 16px',
    backgroundColor: 'transparent',
    border: '1px solid #D8D1C7',
    borderRadius: '999px',
    color: '#4B4338',
    fontSize: '0.82rem',
    fontWeight: 600,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    fontFamily: 'inherit',
  },
  configGroup: {
    marginBottom: '18px',
  },
  configLabel: {
    display: 'block',
    fontSize: '0.82rem',
    fontWeight: 700,
    color: '#1A1A1A',
    marginBottom: '8px',
  },
  select: {
    width: '100%',
    padding: '12px 14px',
    borderRadius: '12px',
    border: '1px solid #D8D1C7',
    backgroundColor: '#FCFAF6',
    color: '#1A1A1A',
    fontSize: '0.9rem',
  },
  projectHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '10px',
    gap: '14px',
  },
  projectHint: {
    fontSize: '0.78rem',
    color: '#7A746B',
    marginTop: '4px',
  },
  selectionCount: {
    fontSize: '0.78rem',
    color: '#7A746B',
    fontWeight: 700,
    whiteSpace: 'nowrap',
  },
  projectList: {
    border: '1px solid #E8E4DC',
    borderRadius: '14px',
    backgroundColor: '#FCFAF6',
    maxHeight: '320px',
    overflowY: 'auto',
  },
  projectEmpty: {
    padding: '18px',
    fontSize: '0.84rem',
    color: '#7A746B',
  },
  projectRow: {
    display: 'flex',
    gap: '12px',
    alignItems: 'flex-start',
    padding: '14px 16px',
    borderBottom: '1px solid #EEE7DD',
    cursor: 'pointer',
  },
  projectText: {
    display: 'grid',
    gap: '2px',
  },
  projectName: {
    fontSize: '0.88rem',
    color: '#1A1A1A',
    fontWeight: 600,
  },
  projectKey: {
    fontSize: '0.77rem',
    color: '#7A746B',
    letterSpacing: '0.02em',
  },
  configActions: {
    display: 'flex',
    justifyContent: 'flex-end',
  },
};

export default MCPPage;
