import { defineStore } from 'pinia'
import type { RegisterRequest } from '../api/openapiTypes'

export interface AccountStepInput {
  email: string
  password: string
  confirmPassword: string
  privacyPolicyAccepted: boolean
  privacyPolicyVersion: string
}

export const useRegistrationDraftStore = defineStore('registrationDraft', {
  state: () => ({
    email: '',
    password: '',
    confirmPassword: '',
    privacyPolicyAccepted: false,
    privacyPolicyVersion: '',
    profileStepVisited: false,
    healthDataProcessingConsent: false,
    healthDataProcessingPolicyVersion: '',
    birthYear: null as number | null,
  }),
  actions: {
    saveAccountStep(input: AccountStepInput): void {
      if (!input.privacyPolicyAccepted) throw new Error('请先确认隐私政策。')
      if (input.password !== input.confirmPassword) throw new Error('两次输入的密码不一致。')
      if (!input.email.trim() || !input.password || !input.privacyPolicyVersion) throw new Error('注册信息不完整。')
      this.email = input.email.trim()
      this.password = input.password
      this.confirmPassword = input.confirmPassword
      this.privacyPolicyAccepted = input.privacyPolicyAccepted
      this.privacyPolicyVersion = input.privacyPolicyVersion
      this.profileStepVisited = false
      this.healthDataProcessingConsent = false
      this.healthDataProcessingPolicyVersion = ''
      this.birthYear = null
    },
    enterProfileStep(): void {
      if (!this.email || !this.password || !this.privacyPolicyAccepted) throw new Error('请先完成注册账户信息。')
      this.profileStepVisited = true
    },
    decideHealthDataProcessing(accepted: boolean, policyVersion: string): void {
      if (!this.profileStepVisited) throw new Error('请先进入健康资料授权步骤。')
      this.healthDataProcessingConsent = accepted
      this.healthDataProcessingPolicyVersion = accepted ? policyVersion : ''
      if (!accepted) this.birthYear = null
    },
    setBirthYear(year: number): void {
      if (!this.profileStepVisited || !this.healthDataProcessingConsent) {
        throw new Error('同意健康数据处理前不能采集出生年份。')
      }
      if (!Number.isInteger(year) || year < 1900 || year > 2100) throw new Error('出生年份无效。')
      this.birthYear = year
    },
    buildRegisterRequest(): RegisterRequest {
      if (!this.privacyPolicyAccepted || !this.profileStepVisited || !this.healthDataProcessingConsent
        || !this.email || !this.password || this.password !== this.confirmPassword
        || !this.privacyPolicyVersion || !this.healthDataProcessingPolicyVersion || this.birthYear === null) {
        throw new Error('注册信息或必需授权尚未完成。')
      }
      // Explicit construction ensures confirmation password and non-contract fields cannot leak.
      return {
        email: this.email,
        password: this.password,
        birth_year: this.birthYear,
        privacy_policy_version: this.privacyPolicyVersion,
        health_data_processing_consent: true,
        health_data_processing_policy_version: this.healthDataProcessingPolicyVersion,
      }
    },
    clearPasswordsAfterAccepted(): void {
      this.password = ''
      this.confirmPassword = ''
      this.privacyPolicyAccepted = false
      this.privacyPolicyVersion = ''
      this.profileStepVisited = false
      this.healthDataProcessingConsent = false
      this.healthDataProcessingPolicyVersion = ''
      this.birthYear = null
    },
    clear(): void {
      this.$reset()
    },
    cancelWorkflow(): void {
      this.$reset()
    },
  },
})
