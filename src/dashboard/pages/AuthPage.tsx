import React, { useEffect, useState } from 'react';
import { getVersion } from '@tauri-apps/api/app';
import {
  loadAuthStatus,
  logoutAuth,
  startAuthLogin,
  type AuthStatus,
} from '../../shared/authService';
import {
  getOnboardingProfile,
  saveOnboardingProfile,
  type OnboardingProfile,
} from '../../shared/onboardingProfileService';

interface AuthPageProps {
  onAuthChange: (authenticated: boolean) => void;
}

type EditableProfileForm = {
  name: string;
  company_name: string;
  role: string;
  work_summary: string;
  key_projects_text: string;
  source_of_truth_text: string;
  usage_scope: 'work-only' | 'work-and-personal';
};

const EMPTY_EDITABLE_PROFILE: EditableProfileForm = {
  name: '',
  company_name: '',
  role: '',
  work_summary: '',
  key_projects_text: '',
  source_of_truth_text: '',
  usage_scope: 'work-only',
};

function normalizeMultilineList(input: string): string[] {
  return input
    .split(/\n|,/g)
    .map((item) => item.trim())
    .filter(Boolean);
}

function toEditableProfileForm(profile: OnboardingProfile | null): EditableProfileForm {
  if (!profile) return EMPTY_EDITABLE_PROFILE;
  return {
    name: profile.name ?? '',
    company_name: profile.company_name ?? '',
    role: profile.role ?? '',
    work_summary: profile.work_summary ?? '',
    key_projects_text: (profile.key_projects ?? []).join('\n'),
    source_of_truth_text: (profile.source_of_truth ?? []).join('\n'),
    usage_scope:
      profile.usage_scope === 'work-and-personal' ? 'work-and-personal' : 'work-only',
  };
}

function toOnboardingPayload(form: EditableProfileForm): OnboardingProfile {
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

function validateProfileForm(form: EditableProfileForm): string | null {
  const payload = toOnboardingPayload(form);
  if (
    !payload.name ||
    !payload.company_name ||
    !payload.role ||
    !payload.work_summary ||
    !payload.usage_scope
  ) {
    return 'Please complete all profile fields before saving.';
  }
  if (payload.key_projects.length === 0) {
    return 'Add at least one key project.';
  }
  if (payload.source_of_truth.length === 0) {
    return 'Add at least one source of truth.';
  }
  return null;
}

function formatUsageScope(value: string): string {
  return value === 'work-and-personal' ? 'Work + personal' : 'Work only';
}

const AuthPage: React.FC<AuthPageProps> = ({ onAuthChange }) => {
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [appVersion, setAppVersion] = useState<string>('');
  const [profile, setProfile] = useState<OnboardingProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileSavedAt, setProfileSavedAt] = useState<string | null>(null);
  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileForm, setProfileForm] = useState<EditableProfileForm>(EMPTY_EDITABLE_PROFILE);
  const [profileFormError, setProfileFormError] = useState<string | null>(null);

  useEffect(() => {
    void hydrate();
    void hydrateOnboardingProfile();
    getVersion().then(setAppVersion).catch(() => setAppVersion(''));
  }, []);

  const hydrate = async () => {
    setLoading(true);
    try {
      const status = await loadAuthStatus();
      setAuthStatus(status);
      onAuthChange(status.authenticated);
    } catch {
      setAuthStatus({
        authenticated: false,
        user: null,
        message: 'Failed to load auth status',
      });
      onAuthChange(false);
    } finally {
      setLoading(false);
    }
  };

  const hydrateOnboardingProfile = async () => {
    setProfileLoading(true);
    setProfileError(null);
    try {
      const profileResult = await getOnboardingProfile();
      setProfile(profileResult);
      setProfileSavedAt(profileResult?.saved_at ?? null);
    } catch (e) {
      setProfileError(e instanceof Error ? e.message : 'Failed to load onboarding profile');
    } finally {
      setProfileLoading(false);
    }
  };

  const handleLogin = async () => {
    setAuthError(null);
    setPolling(true);

    const result = await startAuthLogin();
    setPolling(false);

    if (!result.ok) {
      setAuthError(result.error);
      return;
    }

    setAuthStatus(result.status);
    onAuthChange(true);
  };

  const handleLogout = async () => {
    await logoutAuth();
    const status: AuthStatus = {
      authenticated: false,
      user: null,
      message: 'Logged out',
    };
    setAuthStatus(status);
    setAuthError(null);
    onAuthChange(false);
  };

  const openProfileEditor = () => {
    setProfileForm(toEditableProfileForm(profile));
    setProfileFormError(null);
    setIsEditingProfile(true);
  };

  const updateProfileField = <K extends keyof EditableProfileForm>(
    key: K,
    value: EditableProfileForm[K],
  ) => {
    setProfileForm((prev) => ({ ...prev, [key]: value }));
    setProfileFormError(null);
  };

  const handleSaveProfile = async () => {
    const validationError = validateProfileForm(profileForm);
    if (validationError) {
      setProfileFormError(validationError);
      return;
    }

    setProfileSaving(true);
    setProfileFormError(null);
    try {
      const saved = await saveOnboardingProfile(toOnboardingPayload(profileForm));
      setProfile(saved);
      setProfileSavedAt(saved.saved_at ?? null);
      setProfileError(null);
      setIsEditingProfile(false);
    } catch (e) {
      setProfileFormError(e instanceof Error ? e.message : 'Failed to save onboarding profile');
    } finally {
      setProfileSaving(false);
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
        <h1 style={styles.title}>Profile</h1>
        <p style={styles.subtitle}>Manage your Covalent account</p>
      </div>

      <div style={styles.card}>
        <div style={styles.statusSection}>
          <div style={styles.statusHeader}>
            <div
              style={{
                ...styles.statusDot,
                backgroundColor: authStatus?.authenticated ? '#22c55e' : '#D4CFC6',
              }}
            />
            <span style={styles.statusText}>
              {authStatus?.authenticated ? 'Connected' : 'Not Connected'}
            </span>
          </div>

          {authStatus?.user && (
            <div style={styles.userInfo}>
              <span style={styles.userLabel}>Account</span>
              <span style={styles.userName}>{authStatus.user}</span>
            </div>
          )}

          {authError && <div style={styles.errorBox}>{authError}</div>}

          {polling && (
            <div style={styles.messageBox}>
              Waiting for you to sign in. You can close this after logging in from the browser.
            </div>
          )}

          {authStatus?.message && !authError && !polling && (
            <div style={styles.messageBox}>{authStatus.message}</div>
          )}
        </div>

        <div style={styles.actions}>
          {!authStatus?.authenticated ? (
            <button
              style={{ ...styles.primaryButton, opacity: polling ? 0.6 : 1, cursor: polling ? 'not-allowed' : 'pointer' }}
              onClick={handleLogin}
              disabled={polling}
            >
              {polling ? 'Signing in...' : 'Connect Account'}
            </button>
          ) : (
            <button style={styles.secondaryButton} onClick={handleLogout}>
              Disconnect
            </button>
          )}
        </div>
      </div>

      <div style={styles.card}>
        <div style={styles.profileHeaderRow}>
          <div>
            <h2 style={styles.sectionTitle}>Work Profile</h2>
            <p style={styles.sectionSubtitle}>
              Review and edit the details captured during onboarding.
            </p>
          </div>
          <button
            style={{
              ...styles.secondaryButton,
              opacity: profileLoading ? 0.6 : 1,
              cursor: profileLoading ? 'not-allowed' : 'pointer',
            }}
            disabled={profileLoading}
            onClick={openProfileEditor}
          >
            {profile ? 'Edit details' : 'Add details'}
          </button>
        </div>

        {profileLoading && <div style={styles.loadingText}>Loading profile...</div>}

        {!profileLoading && profileError && (
          <div style={styles.errorBox}>
            {profileError}
            <div style={styles.inlineActionRow}>
              <button style={styles.linkButton} onClick={() => void hydrateOnboardingProfile()}>
                Retry
              </button>
            </div>
          </div>
        )}

        {!profileLoading && !profileError && !profile && (
          <div style={styles.messageBox}>
            No onboarding profile found yet. Add your details to personalize Covalent.
          </div>
        )}

        {!profileLoading && !profileError && profile && (
          <div style={styles.profileDetails}>
            <div style={styles.detailGrid}>
              <div style={styles.detailItem}>
                <span style={styles.detailLabel}>Name</span>
                <span style={styles.detailValue}>{profile.name}</span>
              </div>
              <div style={styles.detailItem}>
                <span style={styles.detailLabel}>Company</span>
                <span style={styles.detailValue}>{profile.company_name}</span>
              </div>
              <div style={styles.detailItem}>
                <span style={styles.detailLabel}>Role</span>
                <span style={styles.detailValue}>{profile.role}</span>
              </div>
              <div style={styles.detailItem}>
                <span style={styles.detailLabel}>Usage Scope</span>
                <span style={styles.detailValue}>{formatUsageScope(profile.usage_scope)}</span>
              </div>
            </div>

            <div style={styles.longField}>
              <span style={styles.detailLabel}>Work Summary</span>
              <p style={styles.longFieldText}>{profile.work_summary}</p>
            </div>

            <div style={styles.longField}>
              <span style={styles.detailLabel}>Key Projects</span>
              <p style={styles.longFieldText}>{(profile.key_projects ?? []).join(', ')}</p>
            </div>

            <div style={styles.longField}>
              <span style={styles.detailLabel}>Sources of Truth</span>
              <p style={styles.longFieldText}>{(profile.source_of_truth ?? []).join(', ')}</p>
            </div>

            {profileSavedAt && (
              <div style={styles.savedAtText}>
                Last updated {new Date(profileSavedAt).toLocaleString()}
              </div>
            )}
          </div>
        )}
      </div>

      {isEditingProfile && (
        <div
          style={styles.modalOverlay}
          onClick={(event) => {
            if (event.target === event.currentTarget && !profileSaving) {
              setIsEditingProfile(false);
            }
          }}
        >
          <div style={styles.modalCard}>
            <h3 style={styles.modalTitle}>Edit onboarding details</h3>
            <p style={styles.modalSubtitle}>
              Update your work context so Covalent can stay aligned.
            </p>

            <div style={styles.formGrid}>
              <label style={styles.fieldLabel}>
                <span>Name</span>
                <input
                  value={profileForm.name}
                  onChange={(e) => updateProfileField('name', e.target.value)}
                  style={styles.input}
                  placeholder="Your full name"
                />
              </label>
              <label style={styles.fieldLabel}>
                <span>Company</span>
                <input
                  value={profileForm.company_name}
                  onChange={(e) => updateProfileField('company_name', e.target.value)}
                  style={styles.input}
                  placeholder="Acme Inc."
                />
              </label>
              <label style={styles.fieldLabel}>
                <span>Role</span>
                <input
                  value={profileForm.role}
                  onChange={(e) => updateProfileField('role', e.target.value)}
                  style={styles.input}
                  placeholder="Staff Product Engineer"
                />
              </label>
              <label style={styles.fieldLabel}>
                <span>Usage scope</span>
                <select
                  value={profileForm.usage_scope}
                  onChange={(e) =>
                    updateProfileField(
                      'usage_scope',
                      e.target.value === 'work-and-personal'
                        ? 'work-and-personal'
                        : 'work-only',
                    )
                  }
                  style={styles.input}
                >
                  <option value="work-only">Work only</option>
                  <option value="work-and-personal">Work + personal</option>
                </select>
              </label>
            </div>

            <label style={styles.fieldLabel}>
              <span>Work summary</span>
              <textarea
                value={profileForm.work_summary}
                onChange={(e) => updateProfileField('work_summary', e.target.value)}
                style={styles.textarea}
                placeholder="What you do day to day, your team, and your goals."
              />
            </label>

            <div style={styles.formGrid}>
              <label style={styles.fieldLabel}>
                <span>Key projects (one per line)</span>
                <textarea
                  value={profileForm.key_projects_text}
                  onChange={(e) => updateProfileField('key_projects_text', e.target.value)}
                  style={styles.textarea}
                  placeholder={'Project Atlas PRD\nCheckout reliability initiative'}
                />
              </label>
              <label style={styles.fieldLabel}>
                <span>Sources of truth (one per line)</span>
                <textarea
                  value={profileForm.source_of_truth_text}
                  onChange={(e) => updateProfileField('source_of_truth_text', e.target.value)}
                  style={styles.textarea}
                  placeholder={'Notion Teamspace\nGitHub org/repo\nShared Drive docs'}
                />
              </label>
            </div>

            {profileFormError && <div style={styles.errorBox}>{profileFormError}</div>}

            <div style={styles.modalActions}>
              <button
                style={styles.secondaryButton}
                onClick={() => setIsEditingProfile(false)}
                disabled={profileSaving}
              >
                Cancel
              </button>
              <button
                style={{
                  ...styles.primaryButton,
                  opacity: profileSaving ? 0.7 : 1,
                  cursor: profileSaving ? 'not-allowed' : 'pointer',
                }}
                onClick={() => void handleSaveProfile()}
                disabled={profileSaving}
              >
                {profileSaving ? 'Saving...' : 'Save changes'}
              </button>
            </div>
          </div>
        </div>
      )}

      {appVersion && <div style={styles.versionText}>v{appVersion}</div>}
    </div>
  );
};

const styles: { [key: string]: React.CSSProperties } = {
  container: {
    padding: '40px',
    maxWidth: '700px',
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
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: '14px',
    padding: '24px',
    border: '1px solid #E8E4DC',
    marginBottom: '20px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
  },
  statusSection: {
    marginBottom: '24px',
  },
  statusHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    marginBottom: '14px',
  },
  statusDot: {
    width: '9px',
    height: '9px',
    borderRadius: '50%',
    flexShrink: 0,
  },
  statusText: {
    fontSize: '1rem',
    fontWeight: '600',
    color: '#1A1A1A',
  },
  userInfo: {
    display: 'flex',
    gap: '10px',
    alignItems: 'center',
    marginBottom: '12px',
    padding: '10px 14px',
    backgroundColor: '#FAFAF8',
    borderRadius: '10px',
    border: '1px solid #E8E4DC',
  },
  userLabel: {
    color: '#9A9A96',
    fontSize: '0.825rem',
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  userName: {
    color: '#1A1A1A',
    fontWeight: '500',
    fontSize: '0.875rem',
  },
  messageBox: {
    backgroundColor: 'rgba(193, 122, 95, 0.08)',
    border: '1px solid rgba(193, 122, 95, 0.25)',
    borderRadius: '10px',
    padding: '12px 16px',
    color: '#5A5A5A',
    fontSize: '0.85rem',
    lineHeight: '1.55',
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
  actions: {
    display: 'flex',
    gap: '10px',
    marginTop: '4px',
  },
  primaryButton: {
    padding: '11px 24px',
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
  secondaryButton: {
    padding: '11px 24px',
    backgroundColor: 'transparent',
    border: '1px solid #E8E4DC',
    borderRadius: '100px',
    color: '#5A5A5A',
    fontSize: '0.875rem',
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
    fontFamily: 'inherit',
  },
  linkButton: {
    border: 'none',
    backgroundColor: 'transparent',
    color: '#1A1A1A',
    padding: 0,
    marginTop: '8px',
    cursor: 'pointer',
    fontWeight: '600',
    fontSize: '0.8rem',
    fontFamily: 'inherit',
  },
  profileHeaderRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: '12px',
    marginBottom: '14px',
  },
  sectionTitle: {
    margin: 0,
    color: '#1A1A1A',
    fontSize: '1.05rem',
    fontWeight: '700',
  },
  sectionSubtitle: {
    margin: '6px 0 0 0',
    color: '#5A5A5A',
    fontSize: '0.86rem',
  },
  profileDetails: {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
  detailGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
    gap: '10px',
  },
  detailItem: {
    border: '1px solid #E8E4DC',
    borderRadius: '10px',
    backgroundColor: '#FAFAF8',
    padding: '10px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  detailLabel: {
    color: '#9A9A96',
    fontSize: '0.73rem',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    fontWeight: '600',
  },
  detailValue: {
    color: '#1A1A1A',
    fontSize: '0.88rem',
    fontWeight: '500',
    lineHeight: '1.4',
  },
  longField: {
    border: '1px solid #E8E4DC',
    borderRadius: '10px',
    backgroundColor: '#FAFAF8',
    padding: '10px 12px',
  },
  longFieldText: {
    color: '#1A1A1A',
    fontSize: '0.86rem',
    margin: '6px 0 0 0',
    lineHeight: '1.5',
    whiteSpace: 'pre-wrap',
  },
  savedAtText: {
    color: '#9A9A96',
    fontSize: '0.78rem',
  },
  inlineActionRow: {
    display: 'flex',
    gap: '8px',
  },
  modalOverlay: {
    position: 'fixed',
    inset: 0,
    backgroundColor: 'rgba(26, 26, 26, 0.28)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '20px',
    zIndex: 50,
  },
  modalCard: {
    width: 'min(760px, 100%)',
    maxHeight: '88vh',
    overflowY: 'auto',
    backgroundColor: '#FFFFFF',
    borderRadius: '14px',
    border: '1px solid #E8E4DC',
    boxShadow: '0 12px 32px rgba(0,0,0,0.15)',
    padding: '22px',
  },
  modalTitle: {
    margin: 0,
    fontSize: '1.15rem',
    color: '#1A1A1A',
    fontWeight: '700',
  },
  modalSubtitle: {
    margin: '6px 0 14px 0',
    color: '#5A5A5A',
    fontSize: '0.86rem',
  },
  formGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
    gap: '10px',
    marginBottom: '10px',
  },
  fieldLabel: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    fontSize: '0.8rem',
    color: '#5A5A5A',
    fontWeight: '600',
  },
  input: {
    border: '1px solid #E8E4DC',
    borderRadius: '9px',
    padding: '10px 11px',
    fontSize: '0.86rem',
    color: '#1A1A1A',
    backgroundColor: '#FFFFFF',
    fontFamily: 'inherit',
  },
  textarea: {
    minHeight: '86px',
    resize: 'vertical',
    border: '1px solid #E8E4DC',
    borderRadius: '9px',
    padding: '10px 11px',
    fontSize: '0.86rem',
    color: '#1A1A1A',
    backgroundColor: '#FFFFFF',
    fontFamily: 'inherit',
    lineHeight: '1.45',
  },
  modalActions: {
    marginTop: '14px',
    display: 'flex',
    justifyContent: 'flex-end',
    gap: '10px',
  },
  loadingText: {
    color: '#9A9A96',
    fontSize: '0.9rem',
  },
  versionText: {
    position: 'fixed',
    bottom: '16px',
    right: '24px',
    color: '#D4CFC6',
    fontSize: '0.72rem',
    fontWeight: '500',
  },
};

export default AuthPage;
