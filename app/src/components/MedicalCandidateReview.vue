<template>
  <view class="candidate-panel" data-testid="medical-candidate-panel">
    <view class="candidate-heading"><text class="candidate-title">逐字段核对</text><button class="candidate-refresh" :disabled="loading || busyCandidateId !== null" data-testid="medical-candidate-refresh" @click="emit('refresh')">刷新</button></view>
    <text class="candidate-note">每个字段需由你单独决定。确认候选不会提升其确定性；拒绝不会写入医疗事实。</text>
    <view v-if="loading && candidates.length === 0" class="candidate-state" role="status" data-testid="medical-candidate-loading">正在读取字段候选…</view>
    <view v-else-if="error && candidates.length === 0" class="candidate-state candidate-state--error" data-testid="medical-candidate-error"><text>{{ error }}</text><GcButton label="重试" variant="secondary" test-id="medical-candidate-retry" @click="emit('refresh')" /></view>
    <view v-else-if="candidates.length === 0" class="candidate-state" data-testid="medical-candidate-empty">当前没有可核对的字段候选。</view>
    <template v-else>
      <text v-if="error" class="candidate-error" role="alert" data-testid="medical-candidate-refresh-error">{{ error }}</text>
      <text v-if="conflictMessage" class="candidate-conflict" role="alert" data-testid="medical-candidate-conflict">{{ conflictMessage }}</text>
      <view v-for="candidate in candidates" :key="candidate.id" class="candidate-card" :data-testid="`medical-candidate-${candidate.id}`">
        <view class="candidate-topline"><text class="candidate-field">{{ candidateFieldLabel(candidate) }}</text><text class="candidate-status" :data-testid="`medical-candidate-status-${candidate.id}`">{{ candidateStatusLabel(candidate.review_status) }}</text></view>
        <text class="candidate-value" :data-testid="`medical-candidate-value-${candidate.id}`">{{ candidateDecisionValueLabel(candidate) }}</text>
        <text v-if="candidate.value_type === 'diagnosis' && isDiagnosis(candidate.value)" class="certainty-note">确定性保留为：{{ certaintyLabel(candidate.value.certainty) }}</text>
        <text v-if="candidate.uncertainty" class="uncertainty-note">解析不确定性：{{ candidate.uncertainty }}</text>
        <view class="candidate-source" data-testid="`medical-candidate-source-${candidate.id}`">
          <text v-if="candidate.confidence !== null">解析置信度 {{ Math.round(candidate.confidence * 100) }}%</text>
          <text v-if="candidateLocatorLabel(candidate.source_locator)">{{ candidateLocatorLabel(candidate.source_locator) }}</text>
          <button v-if="excerptForOnDemandDisplay(candidate)" class="excerpt-toggle" :data-testid="`medical-candidate-excerpt-toggle-${candidate.id}`" @click="toggleExcerpt(candidate.id)">{{ shownExcerpt === candidate.id ? '收起来源摘录' : '按需查看来源摘录' }}</button>
        </view>
        <text v-if="shownExcerpt === candidate.id" class="candidate-excerpt" :data-testid="`medical-candidate-excerpt-${candidate.id}`">{{ excerptForOnDemandDisplay(candidate) }}</text>
        <view v-if="candidate.review_status === 'pending'" class="candidate-actions">
          <GcButton label="按原值确认" variant="primary" :busy="busyCandidateId === candidate.id" :disabled="busyCandidateId !== null" :test-id="`medical-candidate-accept-${candidate.id}`" @click="emit('decide', candidate, 'accept', candidate.value)" />
          <GcButton label="更正后确认" variant="secondary" :disabled="busyCandidateId !== null" :test-id="`medical-candidate-correct-toggle-${candidate.id}`" @click="toggleCorrection(candidate)" />
          <GcButton label="不采纳" variant="secondary" :disabled="busyCandidateId !== null" :test-id="`medical-candidate-reject-${candidate.id}`" @click="emit('decide', candidate, 'reject', null)" />
          <view v-if="correctionCandidate === candidate.id" class="correction-form" :data-testid="`medical-candidate-correction-${candidate.id}`">
            <text class="correction-label">填写你确认的更正值</text>
            <text v-if="candidate.value_type === 'diagnosis'" class="certainty-note">诊断确定性“{{ certaintyLabel(isDiagnosis(candidate.value) ? candidate.value.certainty : '') }}”保持不变；此处仅更正文字。</text>
            <textarea v-model="correctionText[candidate.id]" class="correction-input" :maxlength="candidate.value_type === 'object' ? 4000 : 2000" :aria-label="`${candidateFieldLabel(candidate)}更正值`" :placeholder="candidate.value_type === 'object' ? '按候选结构填写 JSON 对象' : '输入更正后的内容'" :data-testid="`medical-candidate-correction-input-${candidate.id}`" />
            <text v-if="candidate.value_type === 'object'" class="correction-help">对象候选请按字段结构填写 JSON；服务器会再次校验值和单位。</text>
            <text v-if="correctionError[candidate.id]" class="candidate-error" role="alert" :data-testid="`medical-candidate-correction-error-${candidate.id}`">{{ correctionError[candidate.id] }}</text>
            <GcButton label="提交更正决定" :busy="busyCandidateId === candidate.id" :disabled="busyCandidateId !== null" :test-id="`medical-candidate-submit-correction-${candidate.id}`" @click="submitCorrection(candidate)" />
          </view>
        </view>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { MedicalCandidateDecision, MedicalFieldCandidate } from '../api/openapiTypes'
import { candidateDecisionValueLabel, candidateFieldLabel, candidateLocatorLabel, candidateStatusLabel, correctedCandidateValue, excerptForOnDemandDisplay, initialCorrectionText } from '../api/medicalCandidateReview'
import GcButton from './GcButton.vue'

const props = defineProps<{ candidates: MedicalFieldCandidate[]; loading: boolean; error: string; conflictMessage: string; busyCandidateId: string | null }>()
const emit = defineEmits<{
  refresh: []
  decide: [candidate: MedicalFieldCandidate, decision: MedicalCandidateDecision['decision'], value: unknown]
}>()
const correctionCandidate = ref('')
const correctionText = ref<Record<string, string>>({})
const correctionError = ref<Record<string, string>>({})
const shownExcerpt = ref('')

watch(() => props.candidates, (items) => {
  for (const [candidateId] of Object.entries(correctionText.value)) {
    if (!items.some((item) => item.id === candidateId && item.review_status === 'pending')) {
      delete correctionText.value[candidateId]
      delete correctionError.value[candidateId]
      if (correctionCandidate.value === candidateId) correctionCandidate.value = ''
    }
  }
  shownExcerpt.value = ''
})

function toggleExcerpt(candidateId: string) { shownExcerpt.value = shownExcerpt.value === candidateId ? '' : candidateId }
function toggleCorrection(candidate: MedicalFieldCandidate) {
  correctionError.value[candidate.id] = ''
  if (correctionCandidate.value === candidate.id) { correctionCandidate.value = ''; return }
  correctionCandidate.value = candidate.id
  if (!(candidate.id in correctionText.value)) correctionText.value[candidate.id] = initialCorrectionText(candidate)
}
function submitCorrection(candidate: MedicalFieldCandidate) {
  try {
    const value = correctedCandidateValue(candidate, correctionText.value[candidate.id] ?? '')
    correctionError.value[candidate.id] = ''
    emit('decide', candidate, 'correct', value)
  } catch (error) { correctionError.value[candidate.id] = error instanceof Error ? error.message : '更正值无法使用。' }
}
function isDiagnosis(value: unknown): value is { text: string; certainty: string } {
  return typeof value === 'object' && value !== null && !Array.isArray(value) && typeof (value as Record<string, unknown>).text === 'string' && typeof (value as Record<string, unknown>).certainty === 'string'
}
function certaintyLabel(value: string) {
  return ({ explicit: '明确记录', suspected: '疑似记录', rule_out: '待排记录', history: '既往记录' } as Record<string, string>)[value] ?? '无法识别'
}
</script>

<style lang="scss" scoped>
.candidate-panel{margin:14px 0 20px;padding:16px;border:1px solid var(--gc-color-border);border-radius:var(--gc-radius-lg);background:var(--gc-color-surface)}.candidate-heading{display:flex;align-items:center;justify-content:space-between}.candidate-title{color:var(--gc-color-text);font-size:15px;font-weight:var(--gc-font-weight-semibold)}.candidate-refresh{min-width:54px;min-height:44px;padding:0 10px;border:1px solid var(--gc-color-border);border-radius:12px;background:var(--gc-color-surface);color:var(--gc-color-brand);font-size:11px}.candidate-note,.certainty-note,.uncertainty-note,.correction-help{display:block;margin:7px 0;color:var(--gc-color-muted);font-size:10px;line-height:1.5}.candidate-state{display:flex;min-height:86px;align-items:center;justify-content:center;gap:10px;color:var(--gc-color-muted);font-size:12px;text-align:center}.candidate-state--error{flex-direction:column}.candidate-card{margin-top:12px;padding:14px;border:1px solid var(--gc-color-border);border-radius:15px;background:var(--gc-color-canvas)}.candidate-topline{display:flex;align-items:center;justify-content:space-between;gap:8px}.candidate-field{color:var(--gc-color-text);font-size:13px;font-weight:var(--gc-font-weight-semibold)}.candidate-status{padding:5px 8px;border-radius:999px;background:var(--gc-color-sage-pale);color:var(--gc-color-brand-strong);font-size:10px}.candidate-value{display:block;margin:10px 0;color:var(--gc-color-text);font-size:13px;line-height:1.5;overflow-wrap:anywhere}.candidate-source{display:flex;flex-wrap:wrap;align-items:center;gap:8px;color:var(--gc-color-muted);font-size:10px}.excerpt-toggle{min-height:40px;padding:0 8px;border:0;background:transparent;color:var(--gc-color-brand);font-size:10px;text-decoration:underline}.candidate-excerpt{display:block;margin-top:8px;padding:10px;border-left:3px solid var(--gc-color-brand);background:var(--gc-color-surface);color:var(--gc-color-text);font-size:11px;line-height:1.5;overflow-wrap:anywhere}.candidate-actions{display:flex;margin-top:12px;flex-wrap:wrap;gap:8px}.correction-form{display:flex;width:100%;margin-top:8px;flex-direction:column;gap:8px}.correction-label{color:var(--gc-color-text);font-size:11px;font-weight:var(--gc-font-weight-semibold)}.correction-input{box-sizing:border-box;width:100%;min-height:78px;padding:10px;border:1px solid var(--gc-color-border);border-radius:12px;background:var(--gc-color-surface);color:var(--gc-color-text);font-size:12px;line-height:1.5}.candidate-error,.candidate-conflict{display:block;margin-top:9px;padding:10px;border-radius:11px;background:var(--gc-color-danger-pale);color:var(--gc-color-danger);font-size:11px;line-height:1.5}.candidate-conflict{border:1px solid var(--gc-color-danger-border)}
</style>
