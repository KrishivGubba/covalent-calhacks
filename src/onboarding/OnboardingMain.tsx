import React, { useEffect, useMemo, useState } from 'react';
import ReactDOM from 'react-dom/client';
import { invoke } from '@tauri-apps/api/core';
import { open } from '@tauri-apps/plugin-dialog';
import { isPermissionGranted, requestPermission } from '@tauri-apps/plugin-notification';
import {
  loadAuthStatus,
  startAuthLogin,
  type AuthStatus,
} from '../shared/authService';
import {
  areRequiredIntegrationsConnected,
  connectFilesystem,
  connectOAuthIntegration,
  disconnectIntegration,
  fetchIntegrationsStatus,
  getRequiredIntegrations,
  type IntegrationStatus,
  type RequiredIntegrationId,
  REQUIRED_INTEGRATION_IDS,
} from '../shared/integrationService';
import {
  getOnboardingProfile,
  saveOnboardingProfile,
  type OnboardingProfile,
} from '../shared/onboardingProfileService';
import './onboarding.css';

type StepId = 'sign-in' | 'permissions' | 'integrations' | 'profile' | 'finish';

type PermissionStatuses = {
  accessibility: boolean;
  screen_recording: boolean;
  notifications: boolean;
};

type ManualPermissionOverrides = {
  accessibility: boolean;
  screen_recording: boolean;
  notifications: boolean;
};

type OnboardingState = {
  completed: boolean;
  version: number;
  completed_at?: string | null;
};

type ProfileForm = {
  name: string;
  company_name: string;
  role: string;
  work_summary: string;
  key_projects_text: string;
  source_of_truth_text: string;
  usage_scope: 'work-only' | 'work-and-personal';
};

type StepDefinition = {
  id: StepId;
  title: string;
  hint: string;
};

const STEPS: StepDefinition[] = [
  { id: 'sign-in', title: 'Sign In', hint: 'Connect your account' },
  { id: 'permissions', title: 'Permissions', hint: 'Grant required access' },
  { id: 'integrations', title: 'Integrations', hint: 'Connect your tools' },
  { id: 'profile', title: 'Profile', hint: 'Tell us about your work' },
  { id: 'finish', title: 'Finish', hint: 'Review and complete setup' },
];

const EMPTY_PROFILE: ProfileForm = {
  name: '',
  company_name: '',
  role: '',
  work_summary: '',
  key_projects_text: '',
  source_of_truth_text: '',
  usage_scope: 'work-only',
};

const REQUIRED_INTEGRATION_LABELS: Record<RequiredIntegrationId, string> = {
  filesystem: 'Filesystem',
  google: 'Google Workspace',
  github: 'GitHub',
  notion: 'Notion',
};

function normalizeMultilineList(input: string): string[] {
  return input
    .split(/\n|,/g)
    .map((item) => item.trim())
    .filter(Boolean);
}

function toProfilePayload(form: ProfileForm): OnboardingProfile {
  return {
    name: form.name.trim(),
    company_name: form.company_name.trim(),
    role: form.role.trim(),
    work_summary: form.work_summary.trim(),
    key_projects: normalizeMultilineList(form.key_projects_text),
    source_of_truth: normalizeMultilineList(form.source_of_truth_text),
    usage_scope: form.usage_scope,
  };
}

function isProfileValid(form: ProfileForm): boolean {
  const payload = toProfilePayload(form);
  return Boolean(
    payload.name &&
      payload.company_name &&
      payload.role &&
      payload.work_summary &&
      payload.key_projects.length > 0 &&
      payload.source_of_truth.length > 0 &&
      payload.usage_scope,
  );
}

const OnboardingApp: React.FC = () => {
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [initialStepResolved, setInitialStepResolved] = useState(false);

  const [loadingInitial, setLoadingInitial] = useState(true);
  const [fatalError, setFatalError] = useState<string | null>(null);

  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  const [permissionStatuses, setPermissionStatuses] = useState<PermissionStatuses>({
    accessibility: false,
    screen_recording: false,
    notifications: false,
  });
  const [manualPermissionOverrides, setManualPermissionOverrides] =
    useState<ManualPermissionOverrides>({
      accessibility: false,
      screen_recording: false,
      notifications: false,
    });
  const [permissionsLoading, setPermissionsLoading] = useState(false);
  const [permissionBusy, setPermissionBusy] = useState<string | null>(null);
  const [permissionError, setPermissionError] = useState<string | null>(null);

  const [integrations, setIntegrations] = useState<IntegrationStatus[]>([]);
  const [integrationsLoading, setIntegrationsLoading] = useState(false);
  const [integrationBusy, setIntegrationBusy] = useState<string | null>(null);
  const [integrationError, setIntegrationError] = useState<string | null>(null);

  const [profileForm, setProfileForm] = useState<ProfileForm>(EMPTY_PROFILE);
  const [profileSaved, setProfileSaved] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileSavedAt, setProfileSavedAt] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);

  const [finishing, setFinishing] = useState(false);
  const [finishError, setFinishError] = useState<string | null>(null);

  const requiredIntegrations = useMemo(
    () => getRequiredIntegrations(integrations),
    [integrations],
  );
  const signInComplete = Boolean(authStatus?.authenticated);
  const effectivePermissionStatuses = {
    accessibility:
      permissionStatuses.accessibility || manualPermissionOverrides.accessibility,
    screen_recording:
      permissionStatuses.screen_recording || manualPermissionOverrides.screen_recording,
    notifications: permissionStatuses.notifications || manualPermissionOverrides.notifications,
  };
  const permissionsComplete =
    effectivePermissionStatuses.accessibility &&
    effectivePermissionStatuses.screen_recording &&
    effectivePermissionStatuses.notifications;
  const integrationsComplete = areRequiredIntegrationsConnected(integrations);
  const profileComplete = profileSaved;
  const allComplete =
    signInComplete && permissionsComplete && integrationsComplete && profileComplete;

  useEffect(() => {
    void invoke('notify_onboarding_change', { completed: false }).catch(() => undefined);
    void hydrate();
  }, []);

  useEffect(() => {
    const onFocus = () => {
      void refreshPermissionStatuses();
      void refreshIntegrations();
      void refreshAuthStatus();
    };
    window.addEventListener('focus', onFocus);
    return () => {
      window.removeEventListener('focus', onFocus);
    };
  }, []);

  const hydrate = async () => {
    setLoadingInitial(true);
    setFatalError(null);
    try {
      const [state] = await Promise.all([
        invoke<OnboardingState>('get_onboarding_state'),
        refreshAuthStatus(),
        refreshPermissionStatuses(),
        refreshIntegrations(),
        hydrateProfile(),
      ]);

      if (state.completed) {
        await invoke('set_onboarding_completed', { completed: true });
        await invoke('notify_onboarding_change', { completed: true });
      }
    } catch (e) {
      setFatalError(e instanceof Error ? e.message : 'Failed to load onboarding state');
    } finally {
      setLoadingInitial(false);
    }
  };

  const refreshAuthStatus = async () => {
    try {
      const status = await loadAuthStatus();
      setAuthStatus(status);
      await invoke('notify_auth_change', { authenticated: status.authenticated });
    } catch {
      setAuthStatus({ authenticated: false, user: null, message: 'Not connected' });
      await invoke('notify_auth_change', { authenticated: false });
    }
  };

  const refreshPermissionStatuses = async () => {
    setPermissionsLoading(true);
    try {
      const status = await invoke<PermissionStatuses>('get_permission_statuses');
      let notificationsGranted = status.notifications;
      try {
        const pluginGranted = await isPermissionGranted();
        if (pluginGranted !== notificationsGranted) {
          notificationsGranted = pluginGranted;
          await invoke('set_notification_permission_status', { granted: pluginGranted });
        }
      } catch {
        // keep stored status if plugin check fails
      }
      setPermissionStatuses({
        accessibility: status.accessibility,
        screen_recording: status.screen_recording,
        notifications: notificationsGranted,
      });
      setManualPermissionOverrides((prev) => ({
        accessibility: status.accessibility ? false : prev.accessibility,
        screen_recording: status.screen_recording ? false : prev.screen_recording,
        notifications: notificationsGranted ? false : prev.notifications,
      }));
      setPermissionError(null);
    } catch (e) {
      setPermissionError(
        e instanceof Error ? e.message : 'Failed to read permission statuses',
      );
    } finally {
      setPermissionsLoading(false);
    }
  };

  const refreshIntegrations = async () => {
    setIntegrationsLoading(true);
    try {
      const statuses = await fetchIntegrationsStatus();
      setIntegrations(statuses);
      setIntegrationError(null);
    } catch (e) {
      setIntegrationError(
        e instanceof Error ? e.message : 'Failed to fetch integrations',
      );
    } finally {
      setIntegrationsLoading(false);
    }
  };

  const hydrateProfile = async () => {
    try {
      const profile = await getOnboardingProfile();
      if (!profile) return;
      setProfileForm({
        name: profile.name ?? '',
        company_name: profile.company_name ?? '',
        role: profile.role ?? '',
        work_summary: profile.work_summary ?? '',
        key_projects_text: (profile.key_projects ?? []).join('\n'),
        source_of_truth_text: (profile.source_of_truth ?? []).join('\n'),
        usage_scope:
          profile.usage_scope === 'work-and-personal' ? 'work-and-personal' : 'work-only',
      });
      setProfileSaved(true);
      setProfileSavedAt(profile.saved_at ?? null);
    } catch {
      // do not block onboarding if profile load fails
    }
  };

  const getStepComplete = (id: StepId): boolean => {
    switch (id) {
      case 'sign-in':
        return signInComplete;
      case 'permissions':
        return permissionsComplete;
      case 'integrations':
        return integrationsComplete;
      case 'profile':
        return profileComplete;
      case 'finish':
        return allComplete;
    }
  };

  const firstIncompleteIndex = useMemo(() => {
    const idx = STEPS.findIndex((step) => !getStepComplete(step.id));
    return idx === -1 ? STEPS.length - 1 : idx;
  }, [signInComplete, permissionsComplete, integrationsComplete, profileComplete, allComplete]);

  useEffect(() => {
    if (loadingInitial || initialStepResolved) return;
    setCurrentStepIndex(firstIncompleteIndex);
    setInitialStepResolved(true);
  }, [loadingInitial, initialStepResolved, firstIncompleteIndex]);

  const canNavigateToStep = (index: number) => index <= firstIncompleteIndex;
  const currentStep = STEPS[currentStepIndex];
  const currentStepComplete = getStepComplete(currentStep.id);

  useEffect(() => {
    if (currentStep.id !== 'permissions') return;
    const timer = window.setInterval(() => {
      void refreshPermissionStatuses();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [currentStep.id]);

  const gotoStep = (index: number) => {
    if (!canNavigateToStep(index)) return;
    setCurrentStepIndex(index);
  };

  const nextStep = () => {
    if (!currentStepComplete) return;
    setCurrentStepIndex((prev) => Math.min(prev + 1, STEPS.length - 1));
  };

  const previousStep = () => {
    setCurrentStepIndex((prev) => Math.max(prev - 1, 0));
  };

  const handleSignIn = async () => {
    setAuthError(null);
    setAuthBusy(true);
    try {
      const result = await startAuthLogin();
      if (!result.ok) {
        setAuthError(result.error);
        return;
      }
      setAuthStatus(result.status);
      await invoke('notify_auth_change', { authenticated: true });
    } finally {
      setAuthBusy(false);
    }
  };

  const requestAccessibilityPermission = async () => {
    setPermissionError(null);
    setPermissionBusy('accessibility');
    try {
      const granted = await invoke<boolean>('request_accessibility_permission');
      if (!granted) {
        await invoke('open_permission_settings', { section: 'accessibility' });
      } else {
        setManualPermissionOverrides((prev) => ({ ...prev, accessibility: false }));
      }
    } catch (e) {
      setPermissionError(
        e instanceof Error ? e.message : 'Failed to request accessibility permission',
      );
    } finally {
      setPermissionBusy(null);
      await refreshPermissionStatuses();
    }
  };

  const requestScreenRecordingPermission = async () => {
    setPermissionError(null);
    setPermissionBusy('screen_recording');
    try {
      const granted = await invoke<boolean>('request_screen_recording_permission');
      if (!granted) {
        await invoke('open_permission_settings', { section: 'screen_recording' });
      } else {
        setManualPermissionOverrides((prev) => ({ ...prev, screen_recording: false }));
      }
    } catch (e) {
      setPermissionError(
        e instanceof Error ? e.message : 'Failed to request screen recording permission',
      );
    } finally {
      setPermissionBusy(null);
      await refreshPermissionStatuses();
    }
  };

  const requestNotificationsPermission = async () => {
    setPermissionError(null);
    setPermissionBusy('notifications');
    try {
      let granted = await isPermissionGranted();
      if (!granted) {
        const result = await requestPermission();
        granted = result === 'granted';
      }
      await invoke('set_notification_permission_status', { granted });
      if (granted) {
        setManualPermissionOverrides((prev) => ({ ...prev, notifications: false }));
      }
    } catch (e) {
      setPermissionError(
        e instanceof Error ? e.message : 'Failed to request notification permission',
      );
    } finally {
      setPermissionBusy(null);
      await refreshPermissionStatuses();
    }
  };

  const markPermissionAsEnabled = (permission: keyof ManualPermissionOverrides) => {
    setManualPermissionOverrides((prev) => ({ ...prev, [permission]: true }));
    setPermissionError(null);
  };

  const connectIntegration = async (id: RequiredIntegrationId) => {
    setIntegrationError(null);
    setIntegrationBusy(id);
    try {
      if (id === 'filesystem') {
        const selected = await open({
          directory: true,
          multiple: false,
          title: 'Choose a folder for Covalent to access',
        });
        if (!selected) return;
        const path = typeof selected === 'string' ? selected : selected[0];
        if (!path) return;
        const result = await connectFilesystem(path);
        if (!result.ok) {
          throw new Error(result.error);
        }
      } else {
        const result = await connectOAuthIntegration(id);
        if (!result.ok) {
          throw new Error(result.error);
        }
      }
      await refreshIntegrations();
    } catch (e) {
      setIntegrationError(e instanceof Error ? e.message : `Failed to connect ${id}`);
    } finally {
      setIntegrationBusy(null);
    }
  };

  const disconnectRequiredIntegration = async (id: RequiredIntegrationId) => {
    setIntegrationError(null);
    setIntegrationBusy(id);
    try {
      const ok = await disconnectIntegration(id);
      if (!ok) {
        throw new Error(`Failed to disconnect ${id}`);
      }
      await refreshIntegrations();
    } catch (e) {
      setIntegrationError(e instanceof Error ? e.message : `Failed to disconnect ${id}`);
    } finally {
      setIntegrationBusy(null);
    }
  };

  const updateProfile = <K extends keyof ProfileForm>(field: K, value: ProfileForm[K]) => {
    setProfileForm((prev) => ({ ...prev, [field]: value }));
    setProfileSaved(false);
    setProfileError(null);
  };

  const saveProfile = async () => {
    setProfileError(null);
    if (!isProfileValid(profileForm)) {
      setProfileError('Please complete all profile fields before saving.');
      return;
    }

    setProfileSaving(true);
    try {
      const saved = await saveOnboardingProfile(toProfilePayload(profileForm));
      setProfileSaved(true);
      setProfileSavedAt(saved.saved_at ?? null);
    } catch (e) {
      setProfileError(e instanceof Error ? e.message : 'Failed to save profile');
    } finally {
      setProfileSaving(false);
    }
  };

  const completeOnboarding = async () => {
    setFinishError(null);
    if (!allComplete) {
      setFinishError('Please complete all setup requirements before finishing.');
      return;
    }
    setFinishing(true);
    try {
      await invoke('notify_auth_change', { authenticated: true });
      await invoke('set_onboarding_completed', { completed: true });
      await invoke('notify_onboarding_change', { completed: true });
      await invoke('enable_context_collection_if_not_user_paused');
    } catch (e) {
      setFinishError(e instanceof Error ? e.message : 'Failed to complete onboarding');
      setFinishing(false);
      return;
    }
    setFinishing(false);
  };

  const renderSignInStep = () => (
    <div className="onb-step-body">
      <div className="onb-step-card">
        <div className="onb-step-card-header">
          <h2>Connect your Covalent account</h2>
          <span className={`onb-badge ${signInComplete ? 'ok' : 'warn'}`}>
            {signInComplete ? 'Connected' : 'Required'}
          </span>
        </div>
        <p>
          Covalent requires authentication before it can collect context or run integrations.
        </p>
        {authStatus?.user && (
          <p className="onb-muted">
            Signed in as <strong>{authStatus.user}</strong>
          </p>
        )}
        {authError && <div className="onb-error">{authError}</div>}
        <button className="onb-button primary" onClick={() => void handleSignIn()} disabled={authBusy}>
          {authBusy ? 'Signing in...' : signInComplete ? 'Reconnect' : 'Sign in via browser'}
        </button>
      </div>
    </div>
  );

  const renderPermissionsStep = () => (
    <div className="onb-step-body">
      <div className="onb-step-card">
        <div className="onb-step-card-header">
          <h2>Grant required permissions</h2>
          <span className={`onb-badge ${permissionsComplete ? 'ok' : 'warn'}`}>
            {permissionsComplete ? 'All granted' : 'Action needed'}
          </span>
        </div>
        <p>
          Accept each permission one by one so Covalent can stop re-prompting and operate
          reliably.
        </p>
        <div className="onb-permission-list">
          <div className="onb-row">
            <div>
              <strong>Accessibility</strong>
              <p>Needed to read active app context and trigger in-app assistance.</p>
            </div>
            <div className="onb-row-actions">
              <span
                className={`onb-badge ${
                  effectivePermissionStatuses.accessibility ? 'ok' : 'warn'
                }`}
              >
                {effectivePermissionStatuses.accessibility
                  ? manualPermissionOverrides.accessibility &&
                    !permissionStatuses.accessibility
                    ? 'Manual'
                    : 'Granted'
                  : 'Missing'}
              </span>
              <button
                className="onb-button secondary"
                disabled={
                  permissionBusy === 'accessibility' ||
                  effectivePermissionStatuses.accessibility
                }
                onClick={() => void requestAccessibilityPermission()}
              >
                {effectivePermissionStatuses.accessibility
                  ? 'Enabled'
                  : permissionBusy === 'accessibility'
                  ? 'Requesting...'
                  : 'Enable'}
              </button>
              {!effectivePermissionStatuses.accessibility && (
                <button
                  className="onb-button tiny ghost"
                  onClick={() => markPermissionAsEnabled('accessibility')}
                >
                  Already enabled
                </button>
              )}
            </div>
          </div>
          <div className="onb-row">
            <div>
              <strong>Screen recording</strong>
              <p>Needed to capture context snapshots for action suggestions.</p>
            </div>
            <div className="onb-row-actions">
              <span
                className={`onb-badge ${
                  effectivePermissionStatuses.screen_recording ? 'ok' : 'warn'
                }`}
              >
                {effectivePermissionStatuses.screen_recording
                  ? manualPermissionOverrides.screen_recording &&
                    !permissionStatuses.screen_recording
                    ? 'Manual'
                    : 'Granted'
                  : 'Missing'}
              </span>
              <button
                className="onb-button secondary"
                disabled={
                  permissionBusy === 'screen_recording' ||
                  effectivePermissionStatuses.screen_recording
                }
                onClick={() => void requestScreenRecordingPermission()}
              >
                {effectivePermissionStatuses.screen_recording
                  ? 'Enabled'
                  : permissionBusy === 'screen_recording'
                  ? 'Requesting...'
                  : 'Enable'}
              </button>
              {!effectivePermissionStatuses.screen_recording && (
                <button
                  className="onb-button tiny ghost"
                  onClick={() => markPermissionAsEnabled('screen_recording')}
                >
                  Already enabled
                </button>
              )}
            </div>
          </div>
          <div className="onb-row">
            <div>
              <strong>Notifications</strong>
              <p>Needed to deliver suggestions and action confirmations in real time.</p>
            </div>
            <div className="onb-row-actions">
              <span
                className={`onb-badge ${
                  effectivePermissionStatuses.notifications ? 'ok' : 'warn'
                }`}
              >
                {effectivePermissionStatuses.notifications
                  ? manualPermissionOverrides.notifications &&
                    !permissionStatuses.notifications
                    ? 'Manual'
                    : 'Granted'
                  : 'Missing'}
              </span>
              <button
                className="onb-button secondary"
                disabled={
                  permissionBusy === 'notifications' ||
                  effectivePermissionStatuses.notifications
                }
                onClick={() => void requestNotificationsPermission()}
              >
                {effectivePermissionStatuses.notifications
                  ? 'Enabled'
                  : permissionBusy === 'notifications'
                  ? 'Requesting...'
                  : 'Enable'}
              </button>
              {!effectivePermissionStatuses.notifications && (
                <button
                  className="onb-button tiny ghost"
                  onClick={() => markPermissionAsEnabled('notifications')}
                >
                  Already enabled
                </button>
              )}
            </div>
          </div>
        </div>
        <p className="onb-muted onb-help">
          If a permission is already granted in System Settings but still shows missing, use
          <strong> Already enabled</strong> to continue and we will keep re-checking in the
          background.
        </p>
        {permissionError && <div className="onb-error">{permissionError}</div>}
        <button
          className="onb-button ghost"
          onClick={() => void refreshPermissionStatuses()}
          disabled={permissionsLoading}
        >
          {permissionsLoading ? 'Refreshing...' : 'Refresh status'}
        </button>
      </div>
    </div>
  );

  const renderIntegrationsStep = () => (
    <div className="onb-step-body">
      <div className="onb-step-card">
        <div className="onb-step-card-header">
          <h2>Connect required integrations</h2>
          <span className={`onb-badge ${integrationsComplete ? 'ok' : 'warn'}`}>
            {integrationsComplete ? 'All connected' : '4 required'}
          </span>
        </div>
        <p>
          Connect all required integrations so Covalent can reason over your files and source of
          truth.
        </p>
        <div className="onb-grid">
          {REQUIRED_INTEGRATION_IDS.map((id) => {
            const item = requiredIntegrations[id];
            const connected = Boolean(item?.connected);
            const busy = integrationBusy === id;
            return (
              <div key={id} className="onb-integration-card">
                <div className="onb-integration-head">
                  <strong>{REQUIRED_INTEGRATION_LABELS[id]}</strong>
                  <span className={`onb-badge ${connected ? 'ok' : 'warn'}`}>
                    {connected ? 'Connected' : 'Missing'}
                  </span>
                </div>
                <p>{item?.description ?? 'Integration status unavailable. Retry below.'}</p>
                <div className="onb-row-actions">
                  {!connected ? (
                    <button
                      className="onb-button secondary"
                      disabled={busy}
                      onClick={() => void connectIntegration(id)}
                    >
                      {busy ? 'Connecting...' : id === 'filesystem' ? 'Choose folder' : 'Connect'}
                    </button>
                  ) : (
                    <button
                      className="onb-button ghost"
                      disabled={busy}
                      onClick={() => void disconnectRequiredIntegration(id)}
                    >
                      {busy ? 'Disconnecting...' : 'Disconnect'}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        {integrationError && <div className="onb-error">{integrationError}</div>}
        <button
          className="onb-button ghost"
          onClick={() => void refreshIntegrations()}
          disabled={integrationsLoading}
        >
          {integrationsLoading ? 'Refreshing...' : 'Refresh integrations'}
        </button>
      </div>
    </div>
  );

  const renderProfileStep = () => (
    <div className="onb-step-body">
      <div className="onb-step-card">
        <div className="onb-step-card-header">
          <h2>Set your work profile</h2>
          <span className={`onb-badge ${profileComplete ? 'ok' : 'warn'}`}>
            {profileComplete ? 'Saved' : 'Required'}
          </span>
        </div>
        <p>
          This profile is stored in your encrypted graph root node and used to generate better
          context and actions.
        </p>
        <div className="onb-form-grid">
          <label>
            <span>Name</span>
            <input
              value={profileForm.name}
              onChange={(e) => updateProfile('name', e.target.value)}
              placeholder="Your full name"
            />
          </label>
          <label>
            <span>Company name</span>
            <input
              value={profileForm.company_name}
              onChange={(e) => updateProfile('company_name', e.target.value)}
              placeholder="Acme Inc."
            />
          </label>
          <label>
            <span>Role</span>
            <input
              value={profileForm.role}
              onChange={(e) => updateProfile('role', e.target.value)}
              placeholder="Staff Product Engineer"
            />
          </label>
          <label>
            <span>Usage scope</span>
            <select
              value={profileForm.usage_scope}
              onChange={(e) =>
                updateProfile(
                  'usage_scope',
                  e.target.value === 'work-and-personal' ? 'work-and-personal' : 'work-only',
                )
              }
            >
              <option value="work-only">Work only</option>
              <option value="work-and-personal">Work + personal</option>
            </select>
          </label>
        </div>

        <label className="onb-textarea-label">
          <span>Work summary</span>
          <textarea
            value={profileForm.work_summary}
            onChange={(e) => updateProfile('work_summary', e.target.value)}
            placeholder="What you do day to day, your team, and your goals."
          />
        </label>

        <div className="onb-form-grid two-col">
          <label>
            <span>Key projects / PRDs (one per line)</span>
            <textarea
              value={profileForm.key_projects_text}
              onChange={(e) => updateProfile('key_projects_text', e.target.value)}
              placeholder={'Project Atlas PRD\nCheckout reliability initiative'}
            />
          </label>
          <label>
            <span>Sources of truth (one per line)</span>
            <textarea
              value={profileForm.source_of_truth_text}
              onChange={(e) => updateProfile('source_of_truth_text', e.target.value)}
              placeholder={'Notion Teamspace\nGitHub org/repo\nShared Drive docs'}
            />
          </label>
        </div>

        {profileError && <div className="onb-error">{profileError}</div>}
        {profileSavedAt && profileSaved && (
          <div className="onb-success">Profile saved at {new Date(profileSavedAt).toLocaleString()}.</div>
        )}

        <button className="onb-button primary" disabled={profileSaving} onClick={() => void saveProfile()}>
          {profileSaving ? 'Saving...' : 'Save profile'}
        </button>
      </div>
    </div>
  );

  const renderFinishStep = () => (
    <div className="onb-step-body">
      <div className="onb-step-card">
        <div className="onb-step-card-header">
          <h2>Finish setup</h2>
          <span className={`onb-badge ${allComplete ? 'ok' : 'warn'}`}>
            {allComplete ? 'Ready' : 'Incomplete'}
          </span>
        </div>
        <p>Review your onboarding checklist. Covalent only unlocks after every required item is complete.</p>

        <ul className="onb-checklist">
          <li className={signInComplete ? 'ok' : 'warn'}>
            <span>Sign in connected</span>
            <strong>{signInComplete ? 'Done' : 'Missing'}</strong>
          </li>
          <li className={permissionsComplete ? 'ok' : 'warn'}>
            <span>Accessibility, screen recording, notifications</span>
            <strong>{permissionsComplete ? 'Done' : 'Missing'}</strong>
          </li>
          <li className={integrationsComplete ? 'ok' : 'warn'}>
            <span>Filesystem, Google, GitHub, Notion integrations</span>
            <strong>{integrationsComplete ? 'Done' : 'Missing'}</strong>
          </li>
          <li className={profileComplete ? 'ok' : 'warn'}>
            <span>Profile saved to encrypted graph root</span>
            <strong>{profileComplete ? 'Done' : 'Missing'}</strong>
          </li>
        </ul>

        {finishError && <div className="onb-error">{finishError}</div>}

        <button
          className="onb-button primary large"
          disabled={!allComplete || finishing}
          onClick={() => void completeOnboarding()}
        >
          {finishing ? 'Finishing setup...' : 'Start using Covalent'}
        </button>
      </div>
    </div>
  );

  const renderCurrentStep = () => {
    switch (currentStep.id) {
      case 'sign-in':
        return renderSignInStep();
      case 'permissions':
        return renderPermissionsStep();
      case 'integrations':
        return renderIntegrationsStep();
      case 'profile':
        return renderProfileStep();
      case 'finish':
        return renderFinishStep();
    }
  };

  if (loadingInitial) {
    return (
      <div className="onb-shell loading">
        <div className="onb-loader-card">Preparing onboarding...</div>
      </div>
    );
  }

  if (fatalError) {
    return (
      <div className="onb-shell loading">
        <div className="onb-loader-card error">
          <h2>Could not start onboarding</h2>
          <p>{fatalError}</p>
          <button className="onb-button primary" onClick={() => void hydrate()}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="onb-shell">
      <header className="onb-stepper">
        <div className="onb-brand">
          <img src="/icon.png" alt="Covalent" />
          <span>Covalent Setup</span>
        </div>
        <div className="onb-stepper-track">
          {STEPS.map((step, index) => {
            const complete = getStepComplete(step.id);
            const active = index === currentStepIndex;
            const reachable = canNavigateToStep(index);
            return (
              <button
                key={step.id}
                className={`onb-step-chip ${complete ? 'ok' : ''} ${active ? 'active' : ''}`}
                disabled={!reachable}
                onClick={() => gotoStep(index)}
              >
                <span className="onb-chip-title">{step.title}</span>
                <span className="onb-chip-hint">{step.hint}</span>
              </button>
            );
          })}
        </div>
      </header>

      <main className="onb-main">
        <section className="onb-left" key={currentStep.id}>
          {renderCurrentStep()}
          <div className="onb-nav">
            <button
              className="onb-button ghost"
              onClick={previousStep}
              disabled={currentStepIndex === 0 || finishing}
            >
              Back
            </button>
            {currentStep.id !== 'finish' && (
              <button
                className="onb-button primary"
                onClick={nextStep}
                disabled={!currentStepComplete || currentStepIndex >= STEPS.length - 1}
              >
                Continue
              </button>
            )}
          </div>
        </section>

        <aside className="onb-hero">
          <div className="onb-hero-content">
            <span className="onb-hero-eyebrow">Setup progress</span>
            <h1>
              Fast setup,<br />
              full context.
            </h1>
            <p>
              Covalent starts strong once authentication, permissions, integrations, and your
              work profile are all in place.
            </p>

            <div className="onb-setup-summary">
              <div className="onb-summary-item">
                <strong>Account</strong>
                <span className={`onb-summary-item-status ${signInComplete ? 'ok' : 'pending'}`}>
                  {signInComplete ? 'Connected' : 'Pending'}
                </span>
              </div>
              <div className="onb-summary-item">
                <strong>Permissions</strong>
                <span className={`onb-summary-item-status ${permissionsComplete ? 'ok' : 'pending'}`}>
                  {permissionsComplete ? 'All granted' : '3 required'}
                </span>
              </div>
              <div className="onb-summary-item">
                <strong>Integrations</strong>
                <span className={`onb-summary-item-status ${integrationsComplete ? 'ok' : 'pending'}`}>
                  {REQUIRED_INTEGRATION_IDS.filter((id) => requiredIntegrations[id]?.connected).length}/4 connected
                </span>
              </div>
              <div className="onb-summary-item">
                <strong>Work profile</strong>
                <span className={`onb-summary-item-status ${profileComplete ? 'ok' : 'pending'}`}>
                  {profileComplete ? 'Saved' : 'Pending'}
                </span>
              </div>
            </div>
          </div>
        </aside>
      </main>
    </div>
  );
};

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <OnboardingApp />
  </React.StrictMode>,
);
