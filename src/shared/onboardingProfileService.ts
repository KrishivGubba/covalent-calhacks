import { BACKEND_URL } from './backend';

export interface OnboardingProfile {
  name: string;
  company_name: string;
  role: string;
  work_summary: string;
  key_projects: string[];
  source_of_truth: string[];
  usage_scope: string;
  saved_at?: string;
}

export async function getOnboardingProfile(): Promise<OnboardingProfile | null> {
  const response = await fetch(`${BACKEND_URL}/onboarding/profile`);
  if (!response.ok) {
    throw new Error(`Failed to fetch onboarding profile: HTTP ${response.status}`);
  }
  const data = await response.json();
  return data.profile || null;
}

export async function saveOnboardingProfile(profile: OnboardingProfile): Promise<OnboardingProfile> {
  const response = await fetch(`${BACKEND_URL}/onboarding/profile`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    throw new Error(data.detail || data.error || 'Failed to save onboarding profile');
  }
  return data.profile as OnboardingProfile;
}
