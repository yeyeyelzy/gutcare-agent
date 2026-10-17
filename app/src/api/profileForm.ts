import type { PatientProfile, PatientProfilePatch } from './openapiTypes'

export interface ProfileDraft {
  nickname: string
  birthYear: string
  timezone: string
}

export type ProfileField = keyof ProfileDraft

export function profileDraftFrom(profile: PatientProfile): ProfileDraft {
  return {
    nickname: profile.nickname ?? '',
    birthYear: String(profile.birth_year),
    timezone: profile.timezone,
  }
}

/** Build an explicit-field patch. The patient id is deliberately not an input. */
export function buildProfilePatch(
  profile: PatientProfile,
  draft: ProfileDraft,
  explicitFields: readonly ProfileField[] = ['nickname', 'birthYear', 'timezone'],
): PatientProfilePatch | null {
  const patch: PatientProfilePatch = { profile_version: profile.profile_version }
  let changed = false

  const nickname = draft.nickname.trim() || null
  if (explicitFields.includes('nickname') && nickname !== profile.nickname) {
    patch.nickname = nickname
    changed = true
  }

  const birthYear = Number(draft.birthYear)
  if (explicitFields.includes('birthYear') && birthYear !== profile.birth_year) {
    patch.birth_year = birthYear
    changed = true
  }

  const timezone = draft.timezone.trim()
  if (explicitFields.includes('timezone') && timezone !== profile.timezone) {
    patch.timezone = timezone
    changed = true
  }

  return changed ? patch : null
}

export function validateProfileDraft(draft: ProfileDraft): ProfileField | null {
  const nickname = draft.nickname.trim()
  if ([...nickname].length > 64) return 'nickname'
  if (!/^\d{4}$/.test(draft.birthYear) || Number(draft.birthYear) < 1900 || Number(draft.birthYear) > 2100) return 'birthYear'
  if (!isIanaTimeZone(draft.timezone.trim())) return 'timezone'
  return null
}

function isIanaTimeZone(value: string): boolean {
  if (!value || value.length > 64) return false
  try {
    new Intl.DateTimeFormat('en', { timeZone: value }).format(0)
    return true
  } catch {
    return false
  }
}
