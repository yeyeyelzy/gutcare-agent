<template>
  <AuthScaffold test-id="auth-register-profile" eyebrow="PROFILE SETUP" title="开始建档" subtitle="先了解健康数据处理方式，再选择是否继续。" :step="2" step-label="第 2 步 · 健康资料">
    <template v-if="noticeAvailable">
      <NoticeCard title="健康数据处理的单独同意" :description="healthSummary" :version="healthPolicyVersion" variant="consent" test-id="health-processing-notice">
        <button class="consent-toggle" role="checkbox" :aria-checked="accepted" data-testid="health-processing-consent" @click="onConsentChange(!accepted)">
          <view class="check-box" :class="{ 'check-box--checked': accepted }"><text v-if="accepted">✓</text></view>
          <text>我单独同意健康数据处理</text>
        </button>
      </NoticeCard>
      <view v-if="accepted" class="birth-card">
        <text class="section-kicker">BASIC INFO</text>
        <text class="section-title">你的出生年份</text>
        <text class="section-copy">仅收集出生年份，用于建立基本账户资料。</text>
        <GcField id="birth-year" v-model="birthYearInput" label="出生年份" type="number" autocomplete="off" placeholder="例如：1990" :maxlength="4" required test-id="birth-year" />
      </view>
      <InlineProblem :error="error" fallback="注册信息暂时无法提交，请检查后重试。" test-id="register-profile-error" />
      <view v-if="accepted" class="profile-actions">
        <GcButton label="完成注册" :busy="busy" :disabled="busy || !birthYearInput" test-id="register-submit" @click="submitRegistration" />
        <button class="back-link" data-testid="register-profile-back" @click="returnToAccountStep">返回修改账户信息</button>
      </view>
      <view v-else class="profile-actions">
        <GcButton label="暂不同意并退出注册" variant="secondary" test-id="register-cancel" @click="cancelRegistration" />
        <button class="back-link" data-testid="register-profile-back" @click="returnToAccountStep">返回上一步</button>
      </view>
    </template>
    <InlineProblem v-else :error="noticeError" fallback="注册暂不可用：当前构建未配置经批准的健康数据处理告知制品。" test-id="register-health-notice-error" />
  </AuthScaffold>
</template>

<script setup lang="ts">
import { inject, ref } from 'vue'
import { onBackPress, onLoad } from '@dcloudio/uni-app'
import { registrationNotice } from '../../config/registrationNotices'
import { registrationServiceKey, appRouterKey } from '../../api/context'
import { useRegistrationDraftStore } from '../../stores/registrationDraft'
import AuthScaffold from '../../components/AuthScaffold.vue'
import GcButton from '../../components/GcButton.vue'
import GcField from '../../components/GcField.vue'
import InlineProblem from '../../components/InlineProblem.vue'
import NoticeCard from '../../components/NoticeCard.vue'

const draft = useRegistrationDraftStore()
const registration = inject(registrationServiceKey)
const router = inject(appRouterKey)
const accepted = ref(false)
const birthYearInput = ref('')
const error = ref<unknown>(null)
const busy = ref(false)
const noticeError = ref<unknown>(null)
let healthPolicyVersion = ''
let healthSummary = ''
let noticeAvailable = true
try {
  const notice = registrationNotice('health_data_processing')
  healthPolicyVersion = notice.policyVersion
  healthSummary = notice.summary
} catch (cause) {
  noticeAvailable = false
  noticeError.value = cause
}

onLoad(() => {
  try { draft.enterProfileStep() } catch { router?.reLaunch('register') }
})

onBackPress(() => {
  returnToAccountStep()
  return true
})

function returnToAccountStep() { router?.navigateBack() }

function onConsentChange(nextValue: boolean) {
  draft.decideHealthDataProcessing(nextValue, healthPolicyVersion)
  accepted.value = nextValue
  if (!nextValue) birthYearInput.value = ''
  error.value = null
}

function cancelRegistration() {
  draft.cancelWorkflow()
  router?.reLaunch('login')
}

async function submitRegistration() {
  if (!registration || busy.value || !accepted.value) return
  const year = Number(birthYearInput.value)
  if (!Number.isInteger(year) || year < 1900 || year > 2100) {
    error.value = new Error('出生年份无效。')
    return
  }
  try {
    draft.setBirthYear(year)
    busy.value = true
    error.value = null
    await registration.complete()
    uni.showToast({ title: '已受理，请查收验证邮件', icon: 'none' })
    router?.reLaunch('emailVerification')
  } catch (cause) {
    error.value = cause
  } finally {
    busy.value = false
  }
}
</script>

<style lang="scss" scoped>
.birth-card { margin-top: 16px; padding: 18px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); box-shadow: var(--gc-shadow-card); }
.section-kicker { display: block; margin-bottom: 5px; color: var(--gc-color-brand); font-size: 10px; font-weight: var(--gc-font-weight-semibold); letter-spacing: 1.2px; }
.section-title { display: block; color: var(--gc-color-text); font-size: var(--gc-font-size-lg); font-weight: var(--gc-font-weight-semibold); }
.section-copy { display: block; margin: 6px 0 18px; color: var(--gc-color-muted); font-size: 12px; line-height: 1.6; }
.consent-toggle { width: 100%; min-height: 48px; margin-top: 12px; padding: 5px 0; display: flex; align-items: center; gap: 10px; background: transparent; color: var(--gc-color-text); text-align: left; font-size: 12px; line-height: 1.5; }
.check-box { flex: 0 0 22px; width: 22px; height: 22px; border: 1.5px solid var(--gc-color-muted); border-radius: 6px; display: grid; place-items: center; background: var(--gc-color-surface); color: var(--gc-color-on-brand); font-size: 14px; font-weight: var(--gc-font-weight-bold); }
.check-box--checked { border-color: var(--gc-color-brand); background: var(--gc-color-brand); }
.profile-actions { margin-top: 18px; }
.back-link { width: 100%; min-height: 48px; margin-top: 7px; background: transparent; color: var(--gc-color-brand); font-size: var(--gc-font-size-sm); font-weight: var(--gc-font-weight-medium); }
</style>
