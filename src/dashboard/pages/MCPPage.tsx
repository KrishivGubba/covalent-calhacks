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
  type IntegrationStatus,
  type JiraConfigResponse,
  type JiraProject,
  type LargeContextIntegrationStatus,
  type LargeContextSyncStatusResponse,
} from '../../shared/integrationService';
import { formatSystemTimestamp, getSystemTimeZone } from '../../shared/dateTime';

interface MCPPageProps {
  isAuthenticated: boolean;
}

type SyncDraft = {
  enabled: boolean;
  intervalMinutes: number;
};

type SettingsModalState = {
  mode: 'single' | 'all';
  integrationId: string;
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

function SyncLaunchIcon({ active = false }: { active?: boolean }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      style={active ? { opacity: 1 } : undefined}
    >
      <path
        d="M20 7.5V4m0 0h-3.5M20 4l-3 3A8 8 0 1 0 20 12"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="15.6" cy="15.6" r="4.1" stroke="currentColor" strokeWidth="1.6" />
      <path
        d="M15.6 13.8v2.1l1.35.95"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function formatSyncTimestamp(value?: string | null, fallback = 'Not synced yet') {
  if (!value) {
    return fallback;
  }
  return formatSystemTimestamp(value, { timeZoneName: 'short' });
}

function getConnectionLabel(integration: IntegrationStatus) {
  if (integration.included) {
    return 'Included';
  }
  return integration.connected ? 'Connected' : 'Not connected';
}

function getSyncStatusLabel(
  integration: IntegrationStatus,
  syncStatus?: LargeContextIntegrationStatus,
  syncRunning = false,
) {
  if (integration.included) {
    return 'Built in';
  }
  if (syncRunning) {
    return 'Syncing';
  }
  if (!integration.connected) {
    return 'Disconnected';
  }
  if (!syncStatus) {
    return 'Unavailable';
  }
  return syncStatus.enabled ? 'Automatic sync on' : 'Automatic sync off';
}

const MCPPage: React.FC<MCPPageProps> = ({ isAuthenticated }) => {
  const [integrations, setIntegrations] = useState<IntegrationStatus[]>([]);
  const [largeContextStatus, setLargeContextStatus] = useState<LargeContextSyncStatusResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [connectingId, setConnectingId] = useState<string | null>(null);
  const [settingsModal, setSettingsModal] = useState<SettingsModalState | null>(null);
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

  const integrationList = integrations.length > 0 ? integrations : FALLBACK_INTEGRATIONS;

  const integrationSyncMap = useMemo(() => {
    const entries = (largeContextStatus?.integrations || []).map((integrationStatus) => [
      integrationStatus.integration_id,
      integrationStatus,
    ]);
    return Object.fromEntries(entries) as Record<string, LargeContextIntegrationStatus>;
  }, [largeContextStatus]);

  const anySyncRunning = useMemo(
    () =>
      (largeContextStatus?.integrations || []).some(
        (integrationStatus) => integrationStatus.status === 'running',
      ),
    [largeContextStatus],
  );

  const selectedIntegration = settingsModal
    ? integrationList.find((integration) => integration.id === settingsModal.integrationId) || null
    : null;

  useEffect(() => {
    if (loading) return undefined;
    const timeout = window.setTimeout(() => {
      void loadPageData({ silent: true });
    }, anySyncRunning || syncStartingId ? FAST_STATUS_POLL_MS : IDLE_STATUS_POLL_MS);

    return () => window.clearTimeout(timeout);
  }, [anySyncRunning, largeContextStatus, loading, syncStartingId]);

  useEffect(() => {
    if (!settingsModal) {
      return;
    }
    const integrationStatus = integrationSyncMap[settingsModal.integrationId];
    if (integrationStatus) {
      ensureSyncDraft(integrationStatus);
    }
    if (settingsModal.integrationId === 'jira') {
      void ensureJiraConfigLoaded();
    }
  }, [settingsModal, integrationSyncMap]);

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

  const ensureJiraConfigLoaded = async () => {
    const jiraIntegration = integrationList.find((integration) => integration.id === 'jira');
    if (!jiraIntegration?.connected) {
      setJiraConfig(null);
      setJiraProjects([]);
      setJiraCloudId('');
      setJiraProjectKeys([]);
      return;
    }

    setJiraBusy(true);
    try {
      const config = await fetchJiraConfig();
      const accessibleResources = config.config.accessible_resources || [];
      const initialCloudId = config.config.cloud_id || accessibleResources[0]?.cloud_id || '';
      setJiraConfig(config);
      setJiraCloudId(initialCloudId);
      setJiraProjectKeys(config.config.project_keys || []);
      if (initialCloudId) {
        await loadJiraProjectsForCloudId(initialCloudId, config.config.project_keys || []);
      } else {
        setJiraProjects([]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load Jira settings');
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
      } else {
        throw new Error(`${id} integration is not supported yet`);
      }

      await loadPageData();

      if (id === 'jira') {
        await ensureJiraConfigLoaded();
      }
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
      setError('Select a Jira site before saving settings.');
      return;
    }
    if (jiraProjectKeys.length === 0) {
      setError('Select at least one Jira project before saving settings.');
      return;
    }

    setError(null);
    setJiraBusy(true);
    try {
      const config = await updateJiraConfig(jiraCloudId, jiraProjectKeys);
      setJiraConfig(config);
      await loadPageData();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save Jira settings');
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

  const updateSyncDraft = (integrationId: string, partial: Partial<SyncDraft>) => {
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
      setError(e instanceof Error ? e.message : 'Failed to start sync');
    } finally {
      setSyncStartingId(null);
    }
  };

  const openSettingsModal = (mode: 'single' | 'all', integrationId: string) => {
    setSettingsModal({ mode, integrationId });
  };

  const openAllSettings = () => {
    openSettingsModal('all', selectedIntegration?.id || integrationList[0]?.id || 'filesystem');
  };

  const renderCard = (integration: IntegrationStatus) => {
    const integrationStatus = integrationSyncMap[integration.id];
    const syncRunning =
      integrationStatus?.status === 'running' || syncStartingId === integration.id;
    const connectionLabel = getConnectionLabel(integration);
    const lastSync = integrationStatus
      ? formatSyncTimestamp(
          integrationStatus.last_success_at,
          integration.connected ? 'Not synced yet' : 'Connect to sync',
        )
      : integration.included
      ? 'Not applicable'
      : integration.connected
      ? 'Unavailable'
      : 'Connect to sync';
    const nextSync = integrationStatus?.next_run_at
      ? formatSyncTimestamp(integrationStatus.next_run_at, 'Not scheduled')
      : integration.included
      ? 'Not applicable'
      : !integration.connected
      ? 'Connect to schedule'
      : integrationStatus?.enabled
      ? 'Not scheduled'
      : 'Automatic sync off';

    return (
      <div key={integration.id} style={styles.card}>
        <div style={styles.cardTopRow}>
          <div style={styles.cardHeadingBlock}>
            <h3 style={styles.cardTitle}>{integration.name}</h3>
            <p style={styles.cardDescription}>{integration.description}</p>
          </div>

          <button
            style={{
              ...styles.syncLauncherButton,
              ...(syncRunning ? styles.syncLauncherButtonActive : {}),
            }}
            onClick={() => openSettingsModal('single', integration.id)}
            aria-label={`Open ${integration.name} sync controls`}
            title={`${integration.name} sync and settings`}
          >
            <SyncLaunchIcon active={syncRunning} />
          </button>
        </div>

        <div
          style={{
            ...styles.statusBadge,
            ...(integration.connected || integration.included
              ? styles.statusBadgeConnected
              : styles.statusBadgeDisconnected),
          }}
        >
          {connectionLabel}
        </div>

        <div style={styles.statGrid}>
          <div style={styles.statCard}>
            <div style={styles.statLabel}>Last sync</div>
            <div style={styles.statValue}>{lastSync}</div>
          </div>
          <div style={styles.statCard}>
            <div style={styles.statLabel}>Next scheduled</div>
            <div style={styles.statValue}>{nextSync}</div>
          </div>
        </div>

        <div style={styles.cardFooter}>
          <div style={styles.cardFooterLabel}>
            {getSyncStatusLabel(integration, integrationStatus, syncRunning)}
          </div>

          {!integration.included && !integration.connected && (
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
            >
              {connectingId === integration.id
                ? 'Connecting...'
                : integration.id === 'filesystem'
                ? 'Choose Folder'
                : 'Connect'}
            </button>
          )}
        </div>

        {integrationStatus?.last_error && integrationStatus.status === 'error' && (
          <div style={styles.cardErrorText}>{integrationStatus.last_error}</div>
        )}
      </div>
    );
  };

  const renderConnectionSection = (integration: IntegrationStatus) => {
    if (integration.included) {
      return (
        <div style={styles.settingsSection}>
          <div style={styles.settingsSectionHeader}>
            <div>
              <h4 style={styles.settingsSectionTitle}>Connection</h4>
              <p style={styles.settingsSectionText}>
                This integration is built into the product and does not need to be connected.
              </p>
            </div>
          </div>
        </div>
      );
    }

    const requiresLogin = !isAuthenticated && integration.id !== 'filesystem';

    return (
      <div style={styles.settingsSection}>
        <div style={styles.settingsSectionHeader}>
          <div>
            <h4 style={styles.settingsSectionTitle}>Connection</h4>
            <p style={styles.settingsSectionText}>
              {integration.connected
                ? 'This integration is active and available to Covalent.'
                : 'Connect this integration to enable sync and tool access.'}
            </p>
          </div>
        </div>

        <div style={styles.inlineActionRow}>
          {!integration.connected ? (
            <button
              style={{
                ...styles.primaryButton,
                ...(requiresLogin || connectingId === integration.id ? styles.buttonDisabled : {}),
              }}
              onClick={() => void handleConnect(integration.id)}
              disabled={requiresLogin || connectingId === integration.id}
            >
              {connectingId === integration.id
                ? 'Connecting...'
                : integration.id === 'filesystem'
                ? 'Choose Folder'
                : 'Connect'}
            </button>
          ) : (
            <button
              style={{
                ...styles.secondaryButton,
                ...(connectingId === integration.id ? styles.buttonDisabled : {}),
              }}
              onClick={() => void handleDisconnect(integration.id)}
              disabled={connectingId === integration.id}
            >
              {connectingId === integration.id ? 'Disconnecting...' : 'Disconnect'}
            </button>
          )}
        </div>
      </div>
    );
  };

  const renderSyncSection = (integration: IntegrationStatus) => {
    const integrationStatus = integrationSyncMap[integration.id];
    const syncRunning =
      integrationStatus?.status === 'running' || syncStartingId === integration.id;

    if (!integrationStatus) {
      return (
        <div style={styles.settingsSection}>
          <div style={styles.settingsSectionHeader}>
            <div>
              <h4 style={styles.settingsSectionTitle}>Sync</h4>
              <p style={styles.settingsSectionText}>
                {integration.included
                  ? 'No scheduled sync is needed for this built-in integration.'
                  : 'Sync controls are not available for this integration yet.'}
              </p>
            </div>
          </div>
        </div>
      );
    }

    const draft = syncDrafts[integrationStatus.integration_id] || {
      enabled: integrationStatus.enabled,
      intervalMinutes: integrationStatus.interval_minutes,
    };
    const controlsDisabled =
      !integration.connected ||
      connectingId === integration.id ||
      syncSavingId === integrationStatus.integration_id;

    return (
      <div style={styles.settingsSection}>
        <div style={styles.settingsSectionHeader}>
          <div>
            <h4 style={styles.settingsSectionTitle}>Sync</h4>
            <p style={styles.settingsSectionText}>
              Control manual refreshes and the automatic sync schedule for this integration.
            </p>
          </div>

          <button
            style={{
              ...styles.primaryButton,
              ...(syncRunning || !integration.connected ? styles.buttonDisabled : {}),
            }}
            onClick={() => void startManualSync(integrationStatus)}
            disabled={syncRunning || !integration.connected}
          >
            {syncRunning ? 'Syncing...' : 'Sync now'}
          </button>
        </div>

        <div style={styles.settingsStatsGrid}>
          <div style={styles.settingsStat}>
            <span style={styles.settingsStatLabel}>Last sync</span>
            <span style={styles.settingsStatValue}>
              {formatSyncTimestamp(
                integrationStatus.last_success_at,
                integration.connected ? 'Not synced yet' : 'Connect to sync',
              )}
            </span>
          </div>
          <div style={styles.settingsStat}>
            <span style={styles.settingsStatLabel}>Next scheduled</span>
            <span style={styles.settingsStatValue}>
              {integrationStatus.next_run_at
                ? formatSyncTimestamp(integrationStatus.next_run_at, 'Not scheduled')
                : draft.enabled
                ? 'Not scheduled'
                : 'Automatic sync off'}
            </span>
          </div>
          <div style={styles.settingsStat}>
            <span style={styles.settingsStatLabel}>Status</span>
            <span style={styles.settingsStatValue}>
              {getSyncStatusLabel(integration, integrationStatus, syncRunning)}
            </span>
          </div>
        </div>

        {integrationStatus.last_error && integrationStatus.status === 'error' && (
          <div style={styles.syncErrorText}>{integrationStatus.last_error}</div>
        )}

        <div style={styles.settingsFormGrid}>
          <label style={styles.toggleRow}>
            <span style={styles.fieldLabel}>Automatic sync</span>
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

          <label style={styles.fieldBlock}>
            <span style={styles.fieldLabel}>Refresh every</span>
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
        </div>

        <div style={styles.sectionFooter}>
          <span style={styles.helperText}>Times shown in {getSystemTimeZone()}</span>
          <button
            style={{
              ...styles.secondaryButton,
              ...(controlsDisabled ? styles.buttonDisabled : {}),
            }}
            onClick={() => void saveSyncSettings(integrationStatus)}
            disabled={controlsDisabled}
          >
            {syncSavingId === integrationStatus.integration_id ? 'Saving...' : 'Save schedule'}
          </button>
        </div>
      </div>
    );
  };

  const renderJiraSection = (integration: IntegrationStatus) => {
    if (integration.id !== 'jira') {
      return null;
    }

    if (!integration.connected) {
      return (
        <div style={styles.settingsSection}>
          <div style={styles.settingsSectionHeader}>
            <div>
              <h4 style={styles.settingsSectionTitle}>Jira access</h4>
              <p style={styles.settingsSectionText}>
                Connect Jira first, then choose the site and projects Covalent can sync.
              </p>
            </div>
          </div>
        </div>
      );
    }

    const jiraAccessibleResources = jiraConfig?.config.accessible_resources || [];

    return (
      <div style={styles.settingsSection}>
        <div style={styles.settingsSectionHeader}>
          <div>
            <h4 style={styles.settingsSectionTitle}>Jira access</h4>
            <p style={styles.settingsSectionText}>
              Choose which Jira site and projects Covalent should use for sync and live context.
            </p>
          </div>
        </div>

        <div style={styles.fieldBlock}>
          <span style={styles.fieldLabel}>Jira site</span>
          <select
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

        <div style={styles.fieldBlock}>
          <div style={styles.projectsHeader}>
            <div>
              <div style={styles.fieldLabel}>Projects</div>
              <div style={styles.helperText}>
                These projects define the Jira issues that appear in context sync.
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

        <div style={styles.sectionFooter}>
          <span style={styles.helperText}>
            {integration.needs_configuration
              ? 'Jira still needs a site and project selection.'
              : 'Use settings to keep Jira scoped to the right work.'}
          </span>
          <button
            style={{
              ...styles.secondaryButton,
              ...(jiraBusy ? styles.buttonDisabled : {}),
            }}
            onClick={() => void saveJiraConfiguration()}
            disabled={jiraBusy}
          >
            {jiraBusy ? 'Saving...' : 'Save Jira settings'}
          </button>
        </div>
      </div>
    );
  };

  const renderSettingsPanel = (integration: IntegrationStatus) => {
    const integrationStatus = integrationSyncMap[integration.id];
    const syncRunning =
      integrationStatus?.status === 'running' || syncStartingId === integration.id;

    return (
      <div style={styles.settingsPanel}>
        <div style={styles.settingsHero}>
          <div style={styles.settingsHeroText}>
            <div
              style={{
                ...styles.statusBadge,
                ...(integration.connected || integration.included
                  ? styles.statusBadgeConnected
                  : styles.statusBadgeDisconnected),
              }}
            >
              {getConnectionLabel(integration)}
            </div>
            <h3 style={styles.settingsTitle}>{integration.name}</h3>
            <p style={styles.settingsSubtitle}>{integration.description}</p>
          </div>

          <div style={styles.settingsHeroButtonCluster}>
            {integrationStatus && (
              <button
                style={{
                  ...styles.primaryButton,
                  ...(syncRunning || !integration.connected ? styles.buttonDisabled : {}),
                }}
                onClick={() => void startManualSync(integrationStatus)}
                disabled={syncRunning || !integration.connected}
              >
                {syncRunning ? 'Syncing...' : 'Sync now'}
              </button>
            )}
          </div>
        </div>

        {renderConnectionSection(integration)}
        {renderSyncSection(integration)}
        {renderJiraSection(integration)}
      </div>
    );
  };

  const renderSettingsModal = () => {
    if (!settingsModal || !selectedIntegration) {
      return null;
    }

    const modalTitle =
      settingsModal.mode === 'all' ? 'Integration settings' : `${selectedIntegration.name}`;
    const modalSubtitle =
      settingsModal.mode === 'all'
        ? 'Manage connections, sync schedules, and integration-specific setup in one place.'
        : 'Sync controls and integration settings';

    return (
      <div style={styles.modalOverlay} onClick={() => setSettingsModal(null)}>
        <div
          style={{
            ...styles.modalShell,
            ...(settingsModal.mode === 'all' ? styles.modalShellWide : styles.modalShellSingle),
          }}
          onClick={(event) => event.stopPropagation()}
        >
          <div style={styles.modalHeader}>
            <div>
              <h2 style={styles.modalTitle}>{modalTitle}</h2>
              <p style={styles.modalSubtitle}>{modalSubtitle}</p>
            </div>

            <button style={styles.modalCloseButton} onClick={() => setSettingsModal(null)}>
              Close
            </button>
          </div>

          {settingsModal.mode === 'all' ? (
            <div style={styles.modalContentLayout}>
              <div style={styles.modalSidebar}>
                {integrationList.map((integration) => (
                  <button
                    key={integration.id}
                    style={{
                      ...styles.sidebarItem,
                      ...(integration.id === settingsModal.integrationId
                        ? styles.sidebarItemActive
                        : {}),
                    }}
                    onClick={() =>
                      setSettingsModal((prev) =>
                        prev ? { ...prev, integrationId: integration.id } : prev,
                      )
                    }
                  >
                    <span style={styles.sidebarItemName}>{integration.name}</span>
                    <span style={styles.sidebarItemMeta}>{getConnectionLabel(integration)}</span>
                  </button>
                ))}
              </div>

              <div style={styles.modalPanel}>{renderSettingsPanel(selectedIntegration)}</div>
            </div>
          ) : (
            <div style={styles.modalPanel}>{renderSettingsPanel(selectedIntegration)}</div>
          )}
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

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>Integrations</h1>
          <p style={styles.subtitle}>Connect tools, review sync status, and manage settings.</p>
        </div>

        <button style={styles.pageSettingsButton} onClick={openAllSettings}>
          All settings
        </button>
      </div>

      {!isAuthenticated && (
        <div style={styles.loginPrompt}>
          Please log in on the Profile page to manage OAuth integrations.
        </div>
      )}

      {error && <div style={styles.errorBox}>{error}</div>}

      <div style={styles.grid}>{integrationList.map((integration) => renderCard(integration))}</div>

      {renderSettingsModal()}
    </div>
  );
};

const styles: { [key: string]: React.CSSProperties } = {
  container: {
    padding: '40px',
    maxWidth: '1120px',
  },
  header: {
    marginBottom: '28px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: '16px',
    flexWrap: 'wrap',
  },
  title: {
    fontSize: '1.75rem',
    fontWeight: 700,
    color: '#1A1A1A',
    margin: '0 0 6px 0',
    letterSpacing: '-0.03em',
  },
  subtitle: {
    fontSize: '0.95rem',
    color: '#5A5A5A',
    margin: 0,
    lineHeight: 1.5,
  },
  pageSettingsButton: {
    padding: '10px 16px',
    backgroundColor: '#FFFFFF',
    border: '1px solid #D8D1C7',
    borderRadius: '999px',
    color: '#2F2A24',
    fontSize: '0.86rem',
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: 'inherit',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
    gap: '16px',
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: '18px',
    padding: '20px',
    border: '1px solid #E8E4DC',
    display: 'grid',
    gap: '16px',
    boxShadow: '0 4px 18px rgba(17, 17, 17, 0.05)',
  },
  cardTopRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: '14px',
  },
  cardHeadingBlock: {
    minWidth: 0,
  },
  cardTitle: {
    fontSize: '1.05rem',
    fontWeight: 700,
    color: '#1A1A1A',
    margin: 0,
    letterSpacing: '-0.02em',
  },
  cardDescription: {
    fontSize: '0.84rem',
    color: '#5A5A5A',
    margin: '6px 0 0 0',
    lineHeight: 1.5,
  },
  syncLauncherButton: {
    width: '42px',
    height: '42px',
    borderRadius: '999px',
    border: '1px solid #D8D1C7',
    backgroundColor: '#FAF7F2',
    color: '#4B4338',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    flexShrink: 0,
  },
  syncLauncherButtonActive: {
    backgroundColor: '#F1E8DA',
    color: '#1A1A1A',
  },
  statusBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    padding: '7px 12px',
    borderRadius: '999px',
    fontSize: '0.76rem',
    fontWeight: 700,
    width: 'fit-content',
  },
  statusBadgeConnected: {
    backgroundColor: 'rgba(22, 101, 52, 0.08)',
    border: '1px solid rgba(22, 101, 52, 0.16)',
    color: '#166534',
  },
  statusBadgeDisconnected: {
    backgroundColor: 'rgba(180, 35, 24, 0.08)',
    border: '1px solid rgba(180, 35, 24, 0.14)',
    color: '#B42318',
  },
  statGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
    gap: '10px',
  },
  statCard: {
    borderRadius: '14px',
    backgroundColor: '#FCFAF6',
    border: '1px solid #EEE7DD',
    padding: '12px',
    display: 'grid',
    gap: '6px',
  },
  statLabel: {
    fontSize: '0.74rem',
    fontWeight: 700,
    color: '#7A746B',
    letterSpacing: '0.01em',
    textTransform: 'uppercase',
  },
  statValue: {
    fontSize: '0.83rem',
    lineHeight: 1.45,
    color: '#1A1A1A',
  },
  cardFooter: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: '12px',
    flexWrap: 'wrap',
  },
  cardFooterLabel: {
    fontSize: '0.82rem',
    color: '#5A5A5A',
    fontWeight: 600,
  },
  connectButton: {
    padding: '9px 16px',
    backgroundColor: '#1A1A1A',
    border: 'none',
    borderRadius: '999px',
    color: '#FFFFFF',
    fontSize: '0.82rem',
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: 'inherit',
  },
  primaryButton: {
    padding: '10px 16px',
    backgroundColor: '#1A1A1A',
    border: 'none',
    borderRadius: '999px',
    color: '#FFFFFF',
    fontSize: '0.84rem',
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: 'inherit',
  },
  secondaryButton: {
    padding: '10px 16px',
    backgroundColor: '#FFFFFF',
    border: '1px solid #D8D1C7',
    borderRadius: '999px',
    color: '#2F2A24',
    fontSize: '0.84rem',
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: 'inherit',
  },
  buttonDisabled: {
    opacity: 0.45,
    cursor: 'not-allowed',
  },
  cardErrorText: {
    fontSize: '0.76rem',
    lineHeight: 1.45,
    color: '#991b1b',
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
  modalOverlay: {
    position: 'fixed',
    inset: 0,
    backgroundColor: 'rgba(17, 17, 17, 0.24)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '24px',
    zIndex: 1000,
    backdropFilter: 'blur(10px)',
    WebkitBackdropFilter: 'blur(10px)',
  },
  modalShell: {
    width: '100%',
    backgroundColor: 'rgba(255, 255, 255, 0.96)',
    border: '1px solid rgba(232, 228, 220, 0.85)',
    borderRadius: '24px',
    boxShadow: '0 24px 80px rgba(17, 17, 17, 0.16)',
    maxHeight: 'min(88vh, 960px)',
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
  },
  modalShellSingle: {
    maxWidth: '760px',
  },
  modalShellWide: {
    maxWidth: '1080px',
  },
  modalHeader: {
    padding: '24px 24px 18px 24px',
    borderBottom: '1px solid #EEE7DD',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: '16px',
    flexWrap: 'wrap',
  },
  modalTitle: {
    margin: 0,
    fontSize: '1.2rem',
    fontWeight: 700,
    color: '#1A1A1A',
    letterSpacing: '-0.02em',
  },
  modalSubtitle: {
    margin: '6px 0 0 0',
    fontSize: '0.9rem',
    color: '#5A5A5A',
    lineHeight: 1.5,
  },
  modalCloseButton: {
    padding: '10px 16px',
    backgroundColor: '#FFFFFF',
    border: '1px solid #D8D1C7',
    borderRadius: '999px',
    color: '#2F2A24',
    fontSize: '0.84rem',
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: 'inherit',
  },
  modalContentLayout: {
    display: 'flex',
    gap: '0',
    minHeight: 0,
    flex: 1,
    flexWrap: 'wrap',
  },
  modalSidebar: {
    width: '240px',
    minWidth: '240px',
    borderRight: '1px solid #EEE7DD',
    padding: '16px',
    display: 'grid',
    gap: '10px',
    alignContent: 'start',
    backgroundColor: '#FBF8F3',
  },
  sidebarItem: {
    padding: '12px 14px',
    borderRadius: '14px',
    border: '1px solid transparent',
    backgroundColor: 'transparent',
    color: '#2F2A24',
    cursor: 'pointer',
    textAlign: 'left',
    display: 'grid',
    gap: '4px',
    fontFamily: 'inherit',
  },
  sidebarItemActive: {
    backgroundColor: '#FFFFFF',
    border: '1px solid #E8E4DC',
    boxShadow: '0 4px 16px rgba(17, 17, 17, 0.04)',
  },
  sidebarItemName: {
    fontSize: '0.88rem',
    fontWeight: 700,
  },
  sidebarItemMeta: {
    fontSize: '0.76rem',
    color: '#6F685D',
  },
  modalPanel: {
    flex: 1,
    minWidth: '320px',
    overflowY: 'auto',
    padding: '24px',
  },
  settingsPanel: {
    display: 'grid',
    gap: '18px',
  },
  settingsHero: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: '16px',
    flexWrap: 'wrap',
  },
  settingsHeroText: {
    minWidth: 0,
  },
  settingsTitle: {
    margin: '10px 0 0 0',
    fontSize: '1.15rem',
    fontWeight: 700,
    color: '#1A1A1A',
    letterSpacing: '-0.02em',
  },
  settingsSubtitle: {
    margin: '6px 0 0 0',
    fontSize: '0.9rem',
    color: '#5A5A5A',
    lineHeight: 1.5,
    maxWidth: '60ch',
  },
  settingsHeroButtonCluster: {
    display: 'flex',
    gap: '10px',
    flexWrap: 'wrap',
  },
  settingsSection: {
    border: '1px solid #E8E4DC',
    borderRadius: '18px',
    backgroundColor: '#FCFAF6',
    padding: '18px',
    display: 'grid',
    gap: '16px',
  },
  settingsSectionHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: '14px',
    flexWrap: 'wrap',
  },
  settingsSectionTitle: {
    margin: 0,
    fontSize: '0.92rem',
    fontWeight: 700,
    color: '#1A1A1A',
  },
  settingsSectionText: {
    margin: '6px 0 0 0',
    fontSize: '0.84rem',
    color: '#5A5A5A',
    lineHeight: 1.5,
    maxWidth: '64ch',
  },
  inlineActionRow: {
    display: 'flex',
    gap: '10px',
    flexWrap: 'wrap',
  },
  settingsStatsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
    gap: '10px',
  },
  settingsStat: {
    backgroundColor: '#FFFFFF',
    borderRadius: '14px',
    border: '1px solid #EEE7DD',
    padding: '12px',
    display: 'grid',
    gap: '6px',
  },
  settingsStatLabel: {
    fontSize: '0.74rem',
    fontWeight: 700,
    letterSpacing: '0.01em',
    textTransform: 'uppercase',
    color: '#7A746B',
  },
  settingsStatValue: {
    fontSize: '0.84rem',
    lineHeight: 1.45,
    color: '#1A1A1A',
  },
  settingsFormGrid: {
    display: 'grid',
    gap: '14px',
  },
  toggleRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: '12px',
    borderRadius: '14px',
    backgroundColor: '#FFFFFF',
    border: '1px solid #EEE7DD',
    padding: '12px 14px',
  },
  fieldBlock: {
    display: 'grid',
    gap: '8px',
  },
  fieldLabel: {
    fontSize: '0.8rem',
    fontWeight: 700,
    color: '#1A1A1A',
  },
  helperText: {
    fontSize: '0.78rem',
    color: '#7A746B',
    lineHeight: 1.45,
  },
  select: {
    width: '100%',
    padding: '12px 14px',
    borderRadius: '12px',
    border: '1px solid #D8D1C7',
    backgroundColor: '#FFFFFF',
    color: '#1A1A1A',
    fontSize: '0.9rem',
    fontFamily: 'inherit',
  },
  sectionFooter: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: '14px',
    flexWrap: 'wrap',
  },
  syncErrorText: {
    fontSize: '0.78rem',
    color: '#991b1b',
    lineHeight: 1.45,
  },
  projectsHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: '16px',
    flexWrap: 'wrap',
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
    backgroundColor: '#FFFFFF',
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
};

export default MCPPage;
