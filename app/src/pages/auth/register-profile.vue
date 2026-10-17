<template>
  <view class="screen">
    <button class="back" @click="returnToAccountStep">返回修改账户信息</button>
    <text class="heading">开始建档</text>
    <template v-if="noticeAvailable">
      <text class="notice-copy">{{ healthSummary }}</text>
      <view class="choice"><switch :checked="accepted" @change="onConsentChange" /><text>我单独同意健康数据处理</text></view>
      <button class="secondary" @click="cancelRegistration">暂不同意并退出注册</button>
      <template v-if="accepted">
        <label class="label" for="birth-year">出生年份</label>
        <input id="birth-year" v-model="birthYearInput" class="input" type="number" placeholder="例如：1990" />
        <text v-if="message" class="notice" role="alert">{{ message }}</text>
        <button class="primary" :loading="busy" :disabled="busy || !birthYearInput" @click="submitRegistration">完成注册</button>
      </template>
    </template>
    <text v-else class="notice" role="alert">注册暂不可用：当前构建未配置经批准的注册告知制品。</text>
  </view>
</template>

<script setup lang="ts">
import { inject, ref } from 'vue'
import { onBackPress, onLoad } from '@dcloudio/uni-app'
import { registrationNotice } from '../../config/registrationNotices'
import { registrationServiceKey, appRouterKey } from '../../api/context'
import { useRegistrationDraftStore } from '../../stores/registrationDraft'

const draft = useRegistrationDraftStore()
const registration = inject(registrationServiceKey)
const router = inject(appRouterKey)
const accepted = ref(false)
const birthYearInput = ref('')
const message = ref('')
const busy = ref(false)
let healthPolicyVersion = ''
let healthSummary = ''
let noticeAvailable = true
try {
  const notice = registrationNotice('health_data_processing')
  healthPolicyVersion = notice.policyVersion
  healthSummary = notice.summary
} catch {
  noticeAvailable = false
}

onLoad(() => {
  try {
    draft.enterProfileStep()
  } catch {
    router?.reLaunch('register')
  }
})

onBackPress(() => {
  returnToAccountStep()
  return true
})

function returnToAccountStep() {
  router?.navigateBack()
}

function onConsentChange(event: Event) {
  const detail = (event as unknown as { detail: { value: boolean } }).detail
  const nextValue = detail.value
  draft.decideHealthDataProcessing(nextValue, healthPolicyVersion)
  accepted.value = nextValue
  if (!nextValue) birthYearInput.value = ''
  message.value = ''
}

function cancelRegistration() {
  draft.cancelWorkflow()
  router?.reLaunch('login')
}

async function submitRegistration() {
  if (!registration || busy.value) return
  const year = Number(birthYearInput.value)
  try {
    draft.setBirthYear(year)
    busy.value = true
    await registration.complete()
    uni.showToast({ title: '已受理，请查收验证邮件', icon: 'none' })
    router?.reLaunch('emailVerification')
  } catch {
    message.value = '注册信息不完整或服务暂不可用，请检查后重试。'
  } finally {
    busy.value = false
  }
}
</script>

<style lang="scss" scoped>
.screen { min-height: 100vh; padding: 40px 24px 32px; display: flex; flex-direction: column; background: var(--gc-color-canvas); }
.back { align-self: flex-start; margin: 0 0 20px; padding: 0; background: transparent; color: var(--gc-color-brand); }
.heading { font-size: 28px; font-weight: 700; margin-bottom: 24px; }
.notice-copy { padding: 14px; border-radius: var(--gc-radius-sm); background: var(--gc-color-surface); line-height: 1.6; }
.secondary { margin-top: 20px; background: transparent; color: var(--gc-color-brand); }
.choice { display: flex; align-items: center; gap: 10px; margin-top: 20px; }
.label { margin: 24px 0 8px; font-weight: 600; }
.input { height: 52px; padding: 0 14px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-sm); background: var(--gc-color-surface); }
.primary { margin-top: auto; border-radius: var(--gc-radius-md); background: var(--gc-color-brand); color: white; }
.notice { margin-top: 16px; color: var(--gc-color-danger); }
</style>
