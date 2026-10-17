import { describe, expect, it } from 'vitest'
import { buildProfilePatch, profileDraftFrom, validateProfileDraft } from '../src/api/profileForm'
import type { PatientProfile } from '../src/api/openapiTypes'

const profile: PatientProfile = {
  id: 'fixture-profile-id', nickname: 'Mina', birth_year: 1990, timezone: 'Asia/Shanghai', profile_version: 4,
}

describe('本人资料表单映射', () => {
  it('creates a patch with profile_version and only an explicitly changed nullable nickname', () => {
    const draft = profileDraftFrom(profile)
    draft.nickname = '   '
    expect(buildProfilePatch(profile, draft)).toEqual({ profile_version: 4, nickname: null })
  })

  it('adds only changed birth year and timezone fields and never emits identity fields', () => {
    const draft = profileDraftFrom(profile)
    draft.birthYear = '1988'
    draft.timezone = 'America/Vancouver'
    expect(buildProfilePatch(profile, draft)).toEqual({ profile_version: 4, birth_year: 1988, timezone: 'America/Vancouver' })
  })

  it('does not overwrite fields the patient did not explicitly edit after a conflict reload', () => {
    const draft = profileDraftFrom(profile)
    draft.nickname = 'New nickname'
    expect(buildProfilePatch(profile, draft, ['nickname'])).toEqual({ profile_version: 4, nickname: 'New nickname' })
  })

  it('returns no patch when the draft matches the latest profile', () => {
    expect(buildProfilePatch(profile, profileDraftFrom(profile))).toBeNull()
  })

  it('validates year range, nickname length and IANA timezone locally', () => {
    const draft = profileDraftFrom(profile)
    draft.birthYear = '1899'
    expect(validateProfileDraft(draft)).toBe('birthYear')
    draft.birthYear = '1990'
    draft.timezone = 'Not/A_Zone'
    expect(validateProfileDraft(draft)).toBe('timezone')
    draft.timezone = 'Asia/Shanghai'
    draft.nickname = 'x'.repeat(65)
    expect(validateProfileDraft(draft)).toBe('nickname')
  })
})
