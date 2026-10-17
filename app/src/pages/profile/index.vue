<template>
  <scroll-view class="profile-scroll" scroll-y :show-scrollbar="false">
    <view class="profile-page" data-testid="profile-page">
      <view class="topbar">
        <button class="back" aria-label="返回今日" data-testid="profile-back" @click="router?.reLaunch('today')">‹</button>
        <text class="topbar-title">个人资料</text>
        <view class="topbar-spacer" />
      </view>

      <view v-if="loadingProfile" class="loading-card" role="status" aria-live="polite" data-testid="profile-loading">
        <view class="loading-dot" /><text>正在安全载入本人资料…</text>
      </view>
      <view v-else-if="!ready" class="load-error-card">
        <InlineProblem :error="pageError" fallback="暂时无法载入本人资料，请重试。" test-id="profile-load-error" />
        <GcButton label="重试载入资料" variant="secondary" test-id="profile-retry" @click="loadProfile" />
      </view>

      <template v-else>
        <view class="intro">
          <text class="eyebrow">MY ACCOUNT</text>
          <text class="title">管理个人资料</text>
          <text class="subtitle">资料仅用于你的账户体验。此处不显示或修改账户标识。</text>
        </view>

        <view class="profile-card">
          <view class="identity-row">
            <view class="avatar" aria-hidden="true">{{ displayInitial }}</view>
            <view class="identity-copy">
              <text class="identity-name">{{ displayName }}</text>
              <text class="identity-caption">本人账户资料</text>
            </view>
          </view>
          <view class="divider" />

          <GcField id="profile-nickname" v-model="draft.nickname" label="昵称" placeholder="选填" :maxlength="64" test-id="profile-nickname" />
          <GcField id="profile-birth-year" v-model="draft.birthYear" label="出生年份" type="number" placeholder="例如 1990" :maxlength="4" required test-id="profile-birth-year" />
          <GcField id="profile-timezone" v-model="draft.timezone" label="时区" placeholder="例如 Asia/Shanghai" :maxlength="64" required test-id="profile-timezone" />

          <view class="version-note"><text class="version-mark" aria-hidden="true">✓</text><text>保存时会使用当前资料版本，避免覆盖其他设备上的更新。</text></view>
          <InlineProblem :error="pageError" fallback="资料暂时无法保存，请重试。" test-id="profile-error" />

          <view v-if="conflictNeedsReload" class="conflict-card" role="status" data-testid="profile-conflict">
            <text class="conflict-title">资料已在其他位置更新</text>
            <text class="conflict-copy">为避免覆盖最新资料，请先重新载入。载入后核对本次修改，再明确确认是否继续保存。</text>
            <GcButton label="重新载入最新资料" variant="secondary" :busy="loadingLatest" :disabled="loadingLatest" test-id="profile-conflict-reload" @click="reloadLatest" />
          </view>

          <view v-if="conflictReview" class="conflict-review" data-testid="profile-conflict-review">
            <text class="review-title">请核对后确认</text>
            <text class="review-copy">最新资料已载入。确认后只提交你修改的字段，并使用新资料版本。</text>
            <view v-for="item in conflictReviewItems" :key="item.label" class="review-row">
              <text class="review-label">{{ item.label }}</text>
              <text class="review-value">当前：{{ item.current }} → 本次修改：{{ item.proposed }}</text>
            </view>
            <GcButton label="确认仍要应用本次修改" :busy="saving" :disabled="saving" test-id="profile-conflict-confirm" @click="save(true)" />
            <GcButton label="放弃本次修改" variant="quiet" :disabled="saving" test-id="profile-conflict-cancel" @click="discardConflict" />
          </view>

          <GcButton v-if="!conflictReview" label="保存资料" :busy="saving" :disabled="saving || !hasChanges" test-id="profile-save" @click="save(false)" />
        </view>

        <view class="account-card">
          <view class="account-copy"><text class="account-title">账户安全</text><text class="account-description">退出后会清除本机内存会话并尝试删除安全存储中的刷新凭据。</text></view>
          <GcButton label="退出登录" variant="secondary" :busy="loggingOut" :disabled="loggingOut || saving" test-id="profile-logout" @click="confirmLogout" />
        </view>
      </template>
    </view>
  </scroll-view>
</template>

<script setup lang="ts">
import { computed, inject, reactive, ref } from 'vue'
import { onBackPress, onLoad } from '@dcloudio/uni-app'
import { AppError } from '../../api/errors'
import { buildProfilePatch, profileDraftFrom, validateProfileDraft } from '../../api/profileForm'
import type { ProfileDraft } from '../../api/profileForm'
import { appRouterKey, profileApiKey, requestClientKey } from '../../api/context'
import { presentAuthProblem } from '../../api/authUiState'
import { sessionServiceKey } from '../../api/context'
import GcButton from '../../components/GcButton.vue'
import GcField from '../../components/GcField.vue'
import InlineProblem from '../../components/InlineProblem.vue'
import { useAuthStore } from '../../stores/auth'
import type { PatientProfile } from '../../api/openapiTypes'

const auth = useAuthStore()
const router = inject(appRouterKey)
const profileApi = inject(profileApiKey)
const requestClient = inject(requestClientKey)
const session = inject(sessionServiceKey)
const ready = ref(false)
const loadingProfile = ref(true)
const saving = ref(false)
const loadingLatest = ref(false)
const loggingOut = ref(false)
const logoutPromptOpen = ref(false)
const pageError = ref<unknown>(null)
const conflictNeedsReload = ref(false)
const conflictReview = ref(false)
const confirmedProfile = ref<PatientProfile | null>(null)
const draft = reactive<ProfileDraft>({ nickname: '', birthYear: '', timezone: '' })

const initialDraft = ref<ProfileDraft | null>(null)
const dirtyFields = computed(() => {
  if (!initialDraft.value) return []
  return (['nickname', 'birthYear', 'timezone'] as const).filter((field) => draft[field] !== initialDraft.value?.[field])
})
const hasChanges = computed(() => dirtyFields.value.length > 0)
const conflictReviewItems = computed(() => {
  const profile = confirmedProfile.value
  if (!profile) return []
  return dirtyFields.value.map((field) => ({
    label: field === 'nickname' ? '昵称' : field === 'birthYear' ? '出生年份' : '时区',
    current: field === 'nickname' ? profile.nickname || '未设置' : field === 'birthYear' ? String(profile.birth_year) : profile.timezone,
    proposed: field === 'nickname' ? draft.nickname.trim() || '清空' : field === 'birthYear' ? draft.birthYear : draft.timezone.trim(),
  }))
})
const displayName = computed(() => draft.nickname.trim() || 'GutCare 用户')
const displayInitial = computed(() => displayName.value.slice(0, 1))

onLoad(() => { void loadProfile() })
onBackPress(() => { router?.reLaunch('today'); return true })

async function loadProfile() {
  if (!profileApi) return
  ready.value = false
  loadingProfile.value = true
  pageError.value = null
  try {
    const profile = await profileApi.getMyProfile()
    setConfirmedProfile(profile)
    ready.value = true
  } catch (error) {
    if (isNotFound(error)) {
      await showProfileIntegrityError(error)
      return
    }
    pageError.value = error
  } finally {
    loadingProfile.value = false
  }
}

async function save(afterConflictReview: boolean) {
  if (!profileApi || !confirmedProfile.value || saving.value) return
  pageError.value = null
  const invalid = validateProfileDraft(draft)
  if (invalid) {
    pageError.value = new AppError('protocol', fieldError(invalid))
    return
  }
  const patch = buildProfilePatch(confirmedProfile.value, draft, dirtyFields.value)
  if (!patch) {
    conflictNeedsReload.value = false
    conflictReview.value = false
    uni.showToast({ title: '资料没有变化', icon: 'none' })
    return
  }
  if (afterConflictReview && !conflictReview.value) return

  saving.value = true
  try {
    const updated = await profileApi.updateMyProfile(patch)
    auth.acceptProfile(updated)
    setConfirmedProfile(updated)
    conflictNeedsReload.value = false
    conflictReview.value = false
    uni.showToast({ title: '资料已保存', icon: 'success' })
  } catch (error) {
    if (isNotFound(error)) {
      await showProfileIntegrityError(error)
      return
    }
    if (error instanceof AppError && error.status === 409) {
      conflictNeedsReload.value = true
      conflictReview.value = false
      pageError.value = null
      return
    }
    pageError.value = error
  } finally {
    saving.value = false
  }
}

async function reloadLatest() {
  if (!profileApi || loadingLatest.value) return
  loadingLatest.value = true
  pageError.value = null
  try {
    const latest = await profileApi.getMyProfile()
    confirmedProfile.value = latest
    auth.acceptProfile(latest)
    conflictNeedsReload.value = false
    conflictReview.value = true
  } catch (error) {
    if (isNotFound(error)) {
      await showProfileIntegrityError(error)
      return
    }
    pageError.value = error
  } finally {
    loadingLatest.value = false
  }
}

function discardConflict() {
  conflictNeedsReload.value = false
  conflictReview.value = false
  if (confirmedProfile.value) setConfirmedProfile(confirmedProfile.value)
}

async function showProfileIntegrityError(error: unknown) {
  const requestId = error instanceof AppError ? error.requestId ?? error.problem?.request_id ?? null : null
  await requestClient?.clearStoredSession()
  auth.failProfileLoad(requestId)
  router?.showProfileIntegrityError()
}

function setConfirmedProfile(profile: PatientProfile) {
  confirmedProfile.value = profile
  auth.acceptProfile(profile)
  const nextDraft = profileDraftFrom(profile)
  applyDraft(nextDraft)
  initialDraft.value = { ...nextDraft }
}

function applyDraft(source: ProfileDraft) {
  draft.nickname = source.nickname
  draft.birthYear = source.birthYear
  draft.timezone = source.timezone
}

function isNotFound(error: unknown): boolean { return error instanceof AppError && error.status === 404 }

function fieldError(field: 'nickname' | 'birthYear' | 'timezone'): string {
  if (field === 'nickname') return '昵称最多 64 个字符。'
  if (field === 'birthYear') return '请输入 1900 至 2100 之间的四位出生年份。'
  return '请输入有效的 IANA 时区，例如 Asia/Shanghai。'
}

function confirmLogout() {
  if (loggingOut.value || logoutPromptOpen.value || !session) return
  logoutPromptOpen.value = true
  uni.showModal({
    title: '退出登录',
    content: '退出后需要重新登录才能查看本人资料和记录。',
    confirmText: '退出登录',
    cancelText: '取消',
    success: (result: { confirm: boolean }) => { if (result.confirm) void logout() },
    complete: () => { logoutPromptOpen.value = false },
  })
}

async function logout() {
  if (!session || loggingOut.value) return
  loggingOut.value = true
  try {
    await session.logout()
  } catch {
    // SessionService keeps the public page safe and carries a code-only warning to login.
  } finally {
    loggingOut.value = false
  }
}

</script>

<style lang="scss" scoped>
.profile-scroll { height: 100vh; }
.profile-page { min-height: 100vh; max-width: 430px; margin: 0 auto; padding: calc(env(safe-area-inset-top, 0px) + 10px) 20px calc(env(safe-area-inset-bottom, 0px) + 28px); background: var(--gc-color-canvas); }
.topbar { height: 48px; display: flex; align-items: center; justify-content: space-between; }
.back { width: 44px; height: 44px; border-radius: 22px; background: var(--gc-color-surface); color: var(--gc-color-brand-strong); font-size: 28px; line-height: 1; }
.topbar-title { color: var(--gc-color-text); font-size: 16px; font-weight: var(--gc-font-weight-semibold); }.topbar-spacer { width: 44px; }
.loading-card { min-height: 100px; margin-top: 28px; padding: 20px; display: flex; align-items: center; justify-content: center; gap: 10px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); color: var(--gc-color-muted); font-size: var(--gc-font-size-sm); }
.load-error-card { margin-top: 28px; padding: 16px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); }
.loading-dot { width: 17px; height: 17px; border: 2px solid var(--gc-color-sage); border-top-color: var(--gc-color-brand); border-radius: 50%; animation: turn .7s linear infinite; }@keyframes turn { to { transform: rotate(360deg); } }
.intro { margin: 22px 4px 18px; }.eyebrow { display: block; margin-bottom: 5px; color: var(--gc-color-brand); font-size: 11px; letter-spacing: 1px; font-weight: var(--gc-font-weight-semibold); }.title { display: block; font-size: 26px; line-height: 1.35; font-weight: var(--gc-font-weight-bold); }.subtitle { display: block; margin-top: 7px; color: var(--gc-color-muted); font-size: 13px; line-height: 1.55; }
.profile-card, .account-card { padding: 18px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); box-shadow: var(--gc-shadow-card); }
.identity-row { display: flex; align-items: center; gap: 13px; margin-bottom: 16px; }.avatar { width: 52px; height: 52px; border-radius: 50%; display: grid; place-items: center; background: var(--gc-color-sage-pale); color: var(--gc-color-brand-strong); font-size: 21px; font-weight: var(--gc-font-weight-bold); }.identity-copy { display: flex; flex-direction: column; gap: 3px; }.identity-name { color: var(--gc-color-text); font-size: 16px; font-weight: var(--gc-font-weight-semibold); }.identity-caption { color: var(--gc-color-muted); font-size: 12px; }
.divider { height: 1px; margin: 0 0 18px; background: var(--gc-color-border); }.version-note { margin: 4px 0 8px; display: flex; align-items: flex-start; gap: 8px; color: var(--gc-color-muted); font-size: 12px; line-height: 1.5; }.version-mark { flex: 0 0 18px; width: 18px; height: 18px; border-radius: 50%; display: grid; place-items: center; background: var(--gc-color-sage-pale); color: var(--gc-color-brand); font-size: 11px; }
.conflict-card, .conflict-review { margin: 12px 0; padding: 14px; border: 1px solid var(--gc-color-warning-border, var(--gc-color-yellow)); border-radius: var(--gc-radius-md); background: var(--gc-color-warning-pale, #FFF9E9); }.conflict-title, .review-title { display: block; color: var(--gc-color-warning); font-size: 14px; font-weight: var(--gc-font-weight-semibold); }.conflict-copy, .review-copy { display: block; margin: 6px 0 12px; color: var(--gc-color-muted); font-size: 12px; line-height: 1.55; }.conflict-review :deep(.gc-button) { margin-top: 8px; }.review-row { margin: 8px 0; padding: 9px 10px; border-radius: var(--gc-radius-sm); background: var(--gc-color-surface); }.review-label { display: block; font-size: 12px; font-weight: var(--gc-font-weight-semibold); }.review-value { display: block; margin-top: 3px; color: var(--gc-color-muted); font-size: 12px; overflow-wrap: anywhere; }
.account-card { margin-top: 16px; }.account-copy { margin-bottom: 12px; }.account-title { display: block; font-size: 15px; font-weight: var(--gc-font-weight-semibold); }.account-description { display: block; margin-top: 4px; color: var(--gc-color-muted); font-size: 12px; line-height: 1.5; }
</style>
