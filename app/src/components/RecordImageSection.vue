<template>
  <view class="image-card" data-testid="record-image-section">
    <text class="section-title">{{ kind === 'diet' ? '饮食图片' : '排便图片' }}</text>
    <text class="section-hint">{{ kind === 'diet' ? '最多 10 张' : '最多 1 张' }}；JPEG/PNG，每张不超过 10 MiB。图片为可选附件，不影响手工记录。</text>
    <view v-for="item in rows" :key="item.key" class="image-row" :data-testid="`record-image-${item.state}`">
      <view class="image-status"><text class="state-dot" :class="`state-dot--${item.state}`" /><text>{{ stateLabel(item.state) }}</text><text v-if="item.error" class="image-error">{{ item.error }}</text></view>
      <button v-if="item.attachment" class="inline-action" :disabled="busy" @click="remove(item.attachment)">移除图片</button>
    </view>
    <view v-if="attachments.length < limit" class="image-actions">
      <GcButton label="拍照或从相册选择" variant="secondary" :busy="busy" :disabled="busy || attachmentRefreshRequired" test-id="record-image-pick" @click="prepareSelection" />
    </view>
    <GcButton v-if="attachmentRefreshRequired" label="刷新图片列表" variant="secondary" :busy="busy" :disabled="busy" test-id="record-image-refresh" @click="load" />
    <view v-if="noticeOpen && disclosure" class="modal-backdrop" role="presentation" @click.self="noticeOpen = false">
      <view class="notice-modal" role="dialog" aria-modal="true" aria-labelledby="image-notice-title" data-testid="image-purpose-notice">
        <text id="image-notice-title" class="section-title">{{ kind === 'diet' ? '饮食图片处理说明' : '排便图片处理说明' }}</text>
        <text class="notice-copy">{{ disclosure.summary }}</text><text class="notice-copy">用途：{{ disclosure.purpose_text }}</text>
        <text class="notice-copy">数据范围：{{ disclosure.data_scope }}</text><text class="notice-copy">接收方：{{ disclosure.recipient }}</text>
        <text class="notice-copy">保留：{{ disclosure.retention }}</text><text class="notice-copy">撤回影响：{{ disclosure.withdrawal_effect }}</text>
        <view class="modal-actions"><GcButton label="暂不选择" variant="secondary" test-id="image-notice-decline" @click="noticeOpen = false" /><GcButton label="继续选择图片" test-id="image-notice-continue" @click="choose" /></view>
      </view>
    </view>
    <view v-if="problem" class="image-problem" role="alert">{{ problem }}</view>
    <view v-if="attachments.length" class="recognition-block">
      <GcButton label="请求图片识别" variant="secondary" :busy="busy" :disabled="busy || attachmentRefreshRequired" test-id="record-image-recognize" @click="prepareRecognition" />
      <text class="section-hint">识别只生成待确认候选，不会自动修改记录。</text>
      <view v-if="recognition" class="request-card" data-testid="record-image-recognition">
        <text class="request-status">{{ requestLabel(recognition.status) }} · 第 {{ recognition.attempt }} 次</text>
        <text v-if="recognition.reason_code" class="section-hint">{{ reasonLabel(recognition.reason_code) }}</text>
        <view v-for="group in candidateGroups" :key="group.key" class="candidate-group">
        <text v-if="kind === 'diet'" class="group-title">食物项 · 分字段确认</text>
        <view v-for="candidate in group.candidates" :key="candidate.id" class="candidate-card">
          <text class="candidate-type">{{ candidateLabel(candidate.candidate_type) }}</text>
          <text class="candidate-value">{{ candidate.value === null ? '内容已清除' : String(candidate.value) }}</text>
          <text class="section-hint">把握程度：{{ confidenceLabel(candidate.confidence_band) }}</text>
          <view v-if="candidate.status === 'pending' && isNameDependencyBlocked(candidate)" class="dependency-hint">请先确认或修改同组食物名称。</view>
          <template v-if="candidate.status === 'pending' && !isNameDependencyBlocked(candidate)">
            <input v-if="candidate.candidate_type === 'food_name' || candidate.candidate_type === 'portion_description'" v-model="corrections[candidate.id]" class="candidate-input" :placeholder="candidate.candidate_type === 'food_name' ? '输入确认的食物名称' : '输入确认的粗略份量'" />
            <picker v-else-if="candidate.candidate_type === 'food_category'" :range="categoryLabels" @change="setCategoryEvent(candidate.id)"><view class="candidate-input">{{ corrections[candidate.id] ? categoryLabel(corrections[candidate.id] ?? '') : '选择食物类别（可选）' }}</view></picker>
            <picker v-else :range="bristolLabels" @change="setBristolEvent(candidate.id)"><view class="candidate-input">{{ corrections[candidate.id] ? `Bristol ${corrections[candidate.id]} 型` : '选择 Bristol 类型' }}</view></picker>
            <view class="candidate-actions"><button class="inline-action" :disabled="busy || requestRefreshRequired" @click="decide(candidate, 'accept')">确认</button><button class="inline-action" :disabled="busy || requestRefreshRequired" @click="decide(candidate, 'edit')">修改并确认</button><button class="inline-action" :disabled="busy || requestRefreshRequired" @click="decide(candidate, 'reject')">不采纳</button></view>
          </template>
          <text v-else class="section-hint">{{ candidateStatus(candidate.status) }}</text>
        </view>
        </view>
        <GcButton v-if="canRetry" label="重新请求识别" variant="secondary" :busy="busy" :disabled="busy" test-id="record-image-retry" @click="prepareRecognition(true)" />
        <GcButton v-if="requestRefreshRequired" label="刷新识别状态" variant="secondary" :busy="busy" :disabled="busy" test-id="record-image-refresh-request" @click="restoreRequest" />
      </view>
    </view>
    <view v-if="recognitionNoticeOpen && recognitionDisclosure" class="modal-backdrop" role="presentation" @click.self="recognitionNoticeOpen = false">
      <view class="notice-modal" role="dialog" aria-modal="true" aria-labelledby="recognition-notice-title" data-testid="image-recognition-confirm">
        <text id="recognition-notice-title" class="section-title">确认提交本次识别？</text>
        <text class="notice-copy">将本次所选{{ kind === 'diet' ? '饮食' : '排便' }}图片交由已披露的智能服务生成待确认候选。候选不会自动写入记录。</text>
        <text class="notice-copy">{{ recognitionDisclosure.summary }}</text><text class="notice-copy">接收方：{{ recognitionDisclosure.recipient }}；保留：{{ recognitionDisclosure.retention }}</text>
        <view class="modal-actions"><GcButton label="返回记录" variant="secondary" test-id="recognition-decline" @click="recognitionNoticeOpen = false" /><GcButton label="确认并提交" test-id="recognition-accept" @click="submitRecognition" /></view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, inject, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { onHide, onShow } from '@dcloudio/uni-app'
import { consentApiKey, recordImagesApiKey } from '../api/context'
import type { RecordImageAttachment, RecordImageCandidate, RecordImageDisclosure, RecordImageRecognitionRequest } from '../api/openapiTypes'
import { chooseRecordImages, cleanupRecordImage, readRecordImage } from '../api/recordImagePicker'
import { AppError } from '../api/errors'
import { canRetryRecordImageRequest, candidateRequiresFoodName, disclosureIsUsable, hasRecordImageConsent, mutateThenRefresh, recordImageLimit, runVisibleOperation, submitRecordImageRequest, uploadSelectedRecordImages, VisibleOperationGate } from '../api/recordImageBehavior'
import GcButton from './GcButton.vue'

const props = defineProps<{ kind: 'diet' | 'stool'; recordId: string; recordVersion: number; imageSetVersion: number }>()
const emit = defineEmits<{
  (event: 'changed', recordVersion: number, imageSetVersion: number): void
  (event: 'refresh'): void
}>()
const api = inject(recordImagesApiKey)
const consentApi = inject(consentApiKey)
const limit = computed(() => recordImageLimit(props.kind))
const attachments = ref<RecordImageAttachment[]>([])
const currentRecordVersion = ref(props.recordVersion)
const currentImageSetVersion = ref(props.imageSetVersion)
const attachmentRefreshRequired = ref(false)
const requestRefreshRequired = ref(false)
const rows = ref<Array<{ key: string; state: 'selecting' | 'uploading' | 'scanning' | 'clean' | 'error'; error?: string; attachment?: RecordImageAttachment }>>([])
const busy = ref(false)
const problem = ref('')
const disclosure = ref<RecordImageDisclosure | null>(null)
const noticeOpen = ref(false)
const recognitionDisclosure = ref<RecordImageDisclosure | null>(null)
const recognitionNoticeOpen = ref(false)
const recognition = ref<RecordImageRecognitionRequest | null>(null)
const lastRequestId = ref('')
const corrections = reactive<Record<string, string>>({})
const categoryLabels = ['主食', '蔬菜', '水果', '肉类', '海鲜', '乳制品', '蛋类', '豆类', '零食', '饮品', '混合菜品', '其他']
const categoryCodes = ['grain_staple', 'vegetable', 'fruit', 'meat', 'seafood', 'dairy', 'egg', 'legume', 'snack', 'beverage', 'mixed_dish', 'other']
const bristolLabels = ['1', '2', '3', '4', '5', '6', '7']
const canRetry = computed(() => canRetryRecordImageRequest(recognition.value, attachments.value.length) && !attachmentRefreshRequired.value)
const visibleCandidates = computed(() => recognition.value?.candidates ?? [])
const candidateGroups = computed(() => {
  const grouped = new Map<string, RecordImageCandidate[]>()
  for (const candidate of visibleCandidates.value) {
    const key = candidate.candidate_type === 'bristol_type' ? candidate.id : candidate.candidate_group_key
    grouped.set(key, [...(grouped.get(key) ?? []), candidate])
  }
  return [...grouped.entries()].map(([key, candidates]) => ({ key, candidates }))
})
let pollTimer: ReturnType<typeof setTimeout> | undefined
const lifecycle = new VisibleOperationGate()

watch(() => [props.recordId, props.imageSetVersion] as const, () => { currentRecordVersion.value = props.recordVersion; currentImageSetVersion.value = props.imageSetVersion; clearRecognition(); void load() }, { immediate: true })
watch(() => props.recordVersion, (version) => {
  if (recognition.value && version === recognition.value.decision_record_version) currentRecordVersion.value = version
  else clearRecognition()
})
onBeforeUnmount(() => { lifecycle.dispose(); stopPolling(); clearRecognition(true); rows.value = []; attachments.value = [] })
onHide(() => { lifecycle.hide(); busy.value = false; pendingRetry.value = false; noticeOpen.value = false; recognitionNoticeOpen.value = false; clearRecognition(true) })
onShow(() => { lifecycle.show(); void load(); if (lastRequestId.value) void restoreRequest() })

async function load() {
  const requestGeneration = lifecycle.snapshot()
  if (!api) return
  try { const result = await api.list(props.kind, props.recordId); if (lifecycle.isCurrent(requestGeneration)) { attachments.value = result; rows.value = result.map((attachment) => ({ key: attachment.id, state: 'clean', attachment })); attachmentRefreshRequired.value = false } }
  catch { if (lifecycle.isCurrent(requestGeneration)) problem.value = '图片列表暂不可用，可稍后重试。' }
}
async function prepareSelection() {
  if (busy.value) return
  if (!api || !consentApi) { problem.value = '图片授权或处理说明服务暂不可用；仍可手工记录。'; return }
  problem.value = ''
  await runVisibleOperation(lifecycle, async (isCurrent) => {
    const grants = await consentApi.list()
    if (!isCurrent()) return { kind: 'stale' as const }
    if (!hasRecordImageConsent(grants, 'attachment')) return { kind: 'consent_missing' as const }
    const foundDisclosure = await api.disclosure(purpose())
    return { kind: 'disclosure' as const, disclosure: foundDisclosure }
  }, (result) => {
    if (result.kind === 'stale') return
    if (result.kind === 'consent_missing') { problem.value = '请先在隐私设置中确认健康数据处理与敏感图片授权。'; return }
    disclosure.value = result.disclosure
    if (!disclosureIsUsable(result.disclosure)) { problem.value = '当前图片处理说明暂不可用，图片选择已关闭。'; return }
    noticeOpen.value = true
  }, (error) => { problem.value = error instanceof AppError && error.status === 409 ? '当前授权状态不允许添加图片，请检查隐私设置。' : '图片说明或授权状态暂不可用，请稍后重试。' })
}
async function choose() {
  if (!api || busy.value || !lifecycle.isCurrent(lifecycle.snapshot())) return
  const token = lifecycle.snapshot()
  noticeOpen.value = false
  const remaining = limit.value - attachments.value.length
  if (remaining <= 0) return
  busy.value = true
  const selected = await chooseRecordImages(remaining).catch((error) => { if (lifecycle.isCurrent(token)) problem.value = error instanceof Error ? error.message : '图片选择暂不可用。'; return [] })
  if (!lifecycle.isCurrent(token)) { selected.forEach((image) => cleanupRecordImage(image.path)); return }
  try {
    const rowOffset = rows.value.length
    rows.value = [...rows.value, ...selected.map((_, index) => ({ key: `pending-${Date.now()}-${index}`, state: 'selecting' as const }))]
    const previous = attachments.value
    const result = await mutateThenRefresh(previous, async () => uploadSelectedRecordImages({
      selected,
      isCurrent: () => lifecycle.isCurrent(token),
      read: readRecordImage,
      cleanup: cleanupRecordImage,
      stopOnError: (error) => error instanceof AppError && error.status === 409,
      onState: (index, state, error) => {
        if (!lifecycle.isCurrent(token)) return
        const row = rows.value[rowOffset + index]
        const message = error instanceof AppError && error.status === 409 ? '记录已更新，请重新载入。' : '上传或安全检查未完成。'
        if (row) { row.state = state; if (state === 'error') row.error = message }
        if (state === 'error') problem.value = message
        if (state === 'error' && error instanceof AppError && error.status === 409) emit('refresh')
      },
      upload: async (image, bytes, onScanning, isCurrent) => {
        if (!isCurrent()) return null
        return api!.uploadAndAttach({ kind: props.kind, recordId: props.recordId, recordVersion: currentRecordVersion.value,
          imageSetVersion: currentImageSetVersion.value, position: attachments.value.length,
          name: `record-image.${image.contentType === 'image/png' ? 'png' : 'jpg'}`, contentType: image.contentType,
          bytes, onScanning, isActive: isCurrent }).then((attached) => {
            if (!attached || !isCurrent()) return null
            currentRecordVersion.value = attached.record_version; currentImageSetVersion.value = attached.image_set_version
            return attached
          })
      },
      onAttached: (index, attachment) => {
        if (!lifecycle.isCurrent(token)) return
        const row = rows.value[rowOffset + index]
        if (row) row.attachment = attachment
      },
    }), async () => api!.list(props.kind, props.recordId), () => lifecycle.isCurrent(token))
    if (result.interrupted) return
    if (result.refreshed) {
      attachments.value = result.value
      rows.value = result.value.map((attachment) => ({ key: attachment.id, state: 'clean', attachment }))
      attachmentRefreshRequired.value = false
      if (result.mutation?.attached.length) emit('changed', currentRecordVersion.value, currentImageSetVersion.value)
    } else if (result.mutation?.attached.length) {
      attachmentRefreshRequired.value = true
      problem.value = '图片已关联，但列表刷新失败；当前保留原列表。请刷新图片列表后继续。'
    }
  } finally { if (lifecycle.isCurrent(token)) busy.value = false }
}
async function remove(attachment: RecordImageAttachment) {
  if (!api || busy.value) return
  const token = lifecycle.snapshot()
  busy.value = true; problem.value = ''
  try {
    await api.remove(attachment.id, currentRecordVersion.value, currentImageSetVersion.value)
    if (!lifecycle.isCurrent(token)) return
    currentRecordVersion.value++; currentImageSetVersion.value++
    clearRecognition(); emit('changed', currentRecordVersion.value, currentImageSetVersion.value)
    await load()
  } catch (error) { if (lifecycle.isCurrent(token)) { problem.value = error instanceof AppError && error.status === 409 ? '图片集合已更新，请重新载入后再操作。' : '图片未能移除，请稍后重试。'; if (error instanceof AppError && error.status === 409) await load() } }
  finally { if (lifecycle.isCurrent(token)) busy.value = false }
}
async function prepareRecognition(retry = false) {
  if (busy.value || !attachments.value.length) return
  if (!api || !consentApi) { problem.value = '识别授权或说明服务暂不可用；仍可手工记录。'; return }
  problem.value = ''
  await runVisibleOperation(lifecycle, async (isCurrent) => {
    const grants = await consentApi.list()
    if (!isCurrent()) return { kind: 'stale' as const }
    if (!hasRecordImageConsent(grants, 'recognition')) return { kind: 'consent_missing' as const }
    const foundDisclosure = await api.disclosure(purpose())
    return { kind: 'disclosure' as const, disclosure: foundDisclosure }
  }, (result) => {
    if (result.kind === 'stale') return
    if (result.kind === 'consent_missing') { problem.value = '识别需要健康数据处理、敏感图片和第三方智能服务授权。'; return }
    recognitionDisclosure.value = result.disclosure
    if (!disclosureIsUsable(result.disclosure)) { problem.value = '当前识别说明不可用，已保留手工记录和图片。'; return }
    pendingRetry.value = retry
    recognitionNoticeOpen.value = true
  }, () => { problem.value = '授权或识别说明暂不可用，已保留手工记录和图片。' })
}
const pendingRetry = ref(false)
async function submitRecognition() {
  if (!api || !recognitionDisclosure.value?.policy_version || busy.value) return
  const submissionGeneration = lifecycle.snapshot()
  recognitionNoticeOpen.value = false; busy.value = true; problem.value = ''
  try {
    const acknowledged = await api.acknowledge({ record_id: props.recordId, purpose: purpose(), record_version: props.recordVersion, image_set_version: props.imageSetVersion, policy_version: recognitionDisclosure.value.policy_version, acknowledged: true })
    if (!lifecycle.isCurrent(submissionGeneration)) return
    const body = { record_version: props.recordVersion, image_set_version: props.imageSetVersion, disclosure_token: acknowledged.disclosure_token }
    const created = await submitRecordImageRequest({ explicitlyRetry: pendingRetry.value, retryRequestId: recognition.value?.id,
      body, create: (requestBody) => api!.create(props.kind, props.recordId, requestBody), retry: (requestId, requestBody) => api!.retry(requestId, requestBody) })
    lastRequestId.value = created.id
    if (!lifecycle.isCurrent(submissionGeneration)) return
    recognition.value = created
    correctionsReset(); startPolling()
  } catch (error) {
    if (lifecycle.isCurrent(submissionGeneration)) {
      problem.value = error instanceof AppError && error.status === 409 ? '记录或图片已更新。请刷新后检查当前状态，再由你决定是否重新提交。' : '识别服务暂不可用；手工记录和图片仍可使用。'
      if (error instanceof AppError && error.status === 409 && recognition.value?.id) await refreshRequest()
    }
  } finally { if (lifecycle.isCurrent(submissionGeneration)) { busy.value = false; pendingRetry.value = false } }
}
async function refreshRequest() {
  if (!api || !recognition.value) return
  const requestId = recognition.value.id
  const currentGeneration = lifecycle.snapshot()
  try {
    const latest = await api.getRequest(requestId)
    if (!lifecycle.isCurrent(currentGeneration) || recognition.value?.id !== requestId) return
    recognition.value = latest
    requestRefreshRequired.value = false
    if (['pending', 'processing'].includes(latest.status)) startPolling()
  } catch { if (lifecycle.isCurrent(currentGeneration) && recognition.value?.id === requestId) { requestRefreshRequired.value = true; problem.value = '识别状态刷新失败；保留当前候选，请稍后重试。' } }
}
async function restoreRequest() {
  if (!api || !lastRequestId.value) return
  const requestId = lastRequestId.value
  const currentGeneration = lifecycle.snapshot()
  try {
    const latest = await api.getRequest(requestId)
    if (!lifecycle.isCurrent(currentGeneration) || lastRequestId.value !== requestId) return
    recognition.value = latest
    requestRefreshRequired.value = false
    if (['pending', 'processing'].includes(latest.status)) startPolling()
  } catch { if (lifecycle.isCurrent(currentGeneration)) { requestRefreshRequired.value = true; problem.value = '识别状态暂不可用；保留当前内容，可稍后刷新。'; stopPolling() } }
}
function startPolling() { stopPolling(); pollTimer = setTimeout(async () => { await refreshRequest(); if (recognition.value && ['pending', 'processing'].includes(recognition.value.status)) startPolling() }, 4000) }
function stopPolling() { if (pollTimer) clearTimeout(pollTimer); pollTimer = undefined }
async function decide(candidate: RecordImageCandidate, action: 'accept' | 'edit' | 'reject') {
  if (!api || !recognition.value || busy.value) return
  const corrected = corrections[candidate.id]?.trim() ?? ''
  if (action === 'edit' && !corrected) { problem.value = '请先填写确认值。'; return }
  const decisionGeneration = lifecycle.snapshot()
  const requestId = recognition.value.id
  busy.value = true; problem.value = ''
  try {
    const result = await mutateThenRefresh(recognition.value, () => api!.decide(candidate.id, { candidate_version: candidate.candidate_version, record_version: recognition.value!.decision_record_version, image_set_version: recognition.value!.image_set_version, action, ...(action === 'edit' ? { corrected_value: candidate.candidate_type === 'bristol_type' ? Number(corrected) : corrected } : {}) }), () => api!.getRequest(requestId), () => lifecycle.isCurrent(decisionGeneration) && recognition.value?.id === requestId)
    if (!lifecycle.isCurrent(decisionGeneration) || recognition.value?.id !== requestId) return
    if (!result.refreshed) {
      requestRefreshRequired.value = true
      problem.value = '决定已提交，最新状态获取失败，请刷新识别状态。'
      return
    }
    recognition.value = result.value
    requestRefreshRequired.value = false
    currentRecordVersion.value = recognition.value.decision_record_version
    emit('changed', currentRecordVersion.value, currentImageSetVersion.value)
  } catch (error) {
    if (!lifecycle.isCurrent(decisionGeneration) || recognition.value?.id !== requestId) return
    if (error instanceof AppError && error.status === 409 && error.code === 'candidate_dependency_unmet') { problem.value = '请先确认或修改同组食物名称，再分别处理类别或份量。' }
    else if (error instanceof AppError && error.status === 409) {
      problem.value = '记录已更新，请检查最新候选后再决定；未自动重复提交。'
      await refreshRequest()
      if (!lifecycle.isCurrent(decisionGeneration) || recognition.value?.id !== requestId) return
      if (recognition.value) currentRecordVersion.value = recognition.value.decision_record_version
      emit('changed', currentRecordVersion.value, currentImageSetVersion.value)
    }
    else problem.value = '候选暂未提交，请稍后查看当前状态。'
  } finally { if (lifecycle.isCurrent(decisionGeneration)) busy.value = false }
}
function isNameDependencyBlocked(candidate: RecordImageCandidate): boolean { return candidateRequiresFoodName(candidate, recognition.value?.candidates ?? []) }
function setCategory(id: string, event: { detail?: { value?: string | number } }) { const index = Number(event.detail?.value); corrections[id] = categoryCodes[index] ?? '' }
function setBristol(id: string, event: { detail?: { value?: string | number } }) { corrections[id] = String(Number(event.detail?.value) + 1) }
function setCategoryEvent(id: string) { return (event: { detail?: { value?: string | number } }) => setCategory(id, event) }
function setBristolEvent(id: string) { return (event: { detail?: { value?: string | number } }) => setBristol(id, event) }
function purpose() { return props.kind === 'diet' ? 'diet_image_recognition' as const : 'stool_image_recognition' as const }
function clearRecognition(preserveRequestId = false) { lifecycle.invalidate(); stopPolling(); recognition.value = null; recognitionDisclosure.value = null; correctionsReset(); requestRefreshRequired.value = false; if (!preserveRequestId) lastRequestId.value = '' }
function correctionsReset() { for (const key of Object.keys(corrections)) delete corrections[key] }
function stateLabel(state: string) { return ({ selecting: '选择中', uploading: '上传中', scanning: '安全检查中', clean: '可用于记录', error: '未完成' } as Record<string, string>)[state] ?? '状态未知' }
function requestLabel(status: string) { return ({ pending: '等待处理', processing: '正在处理', candidates_ready: '有待确认候选', no_candidates: '没有可供确认的项目', failed: '处理未完成', cancelled: '已取消', invalidated: '来源已变化' } as Record<string, string>)[status] ?? '识别状态' }
function reasonLabel(reason: string) { return ({ low_image_quality: '图片质量不足', unsupported_image: '图片格式不支持', no_visible_food: '未生成饮食候选', no_reliable_stool_type: '未生成 Bristol 候选', agent_unavailable: '智能服务暂不可用，可继续手工记录' } as Record<string, string>)[reason] ?? '识别暂未完成' }
function candidateLabel(type: string) { return ({ food_name: '食物名称', food_category: '食物类别', portion_description: '粗略份量', bristol_type: 'Bristol 类型' } as Record<string, string>)[type] ?? '待确认项目' }
function confidenceLabel(value: string) { return ({ low: '较低', medium: '中等', high: '较高' } as Record<string, string>)[value] ?? '未说明' }
function categoryLabel(code: string) { return categoryLabels[categoryCodes.indexOf(code)] ?? '选择食物类别（可选）' }
function candidateStatus(status: string) { return ({ accepted: '已确认', edited: '已修改并确认', rejected: '未采纳', invalidated: '已失效' } as Record<string, string>)[status] ?? '待确认' }
</script>

<style lang="scss" scoped>
.image-card,.request-card { display:flex; margin-top:16px; padding:16px; flex-direction:column; gap:9px; border:1px solid var(--gc-color-border); border-radius:var(--gc-radius-lg); background:var(--gc-color-surface); }.section-title { color:var(--gc-color-text); font-size:15px; font-weight:var(--gc-font-weight-semibold); }.section-hint,.notice-copy { color:var(--gc-color-muted); font-size:11px; line-height:1.55; }.image-row { display:flex; min-height:44px; align-items:center; justify-content:space-between; gap:8px; border-top:1px solid var(--gc-color-border); }.image-status { display:flex; align-items:center; gap:7px; color:var(--gc-color-text); font-size:12px; }.state-dot { width:9px; height:9px; border-radius:50%; background:var(--gc-color-muted); }.state-dot--clean { background:var(--gc-color-brand); }.state-dot--error { background:var(--gc-color-danger); }.image-error,.image-problem { color:var(--gc-color-danger); font-size:11px; }.recognition-block { display:flex; margin-top:9px; flex-direction:column; gap:8px; }.request-status { color:var(--gc-color-brand-strong); font-size:13px; font-weight:var(--gc-font-weight-semibold); }.candidate-group { padding:8px 12px; border:1px solid var(--gc-color-border); border-radius:12px; }.group-title { color:var(--gc-color-brand-strong); font-size:12px; font-weight:var(--gc-font-weight-semibold); }.candidate-card { display:flex; padding:12px 0; flex-direction:column; gap:6px; border-top:1px solid var(--gc-color-border); }.candidate-type { color:var(--gc-color-muted); font-size:11px; }.candidate-value { color:var(--gc-color-text); font-size:14px; }.candidate-input { min-height:44px; padding:10px; border:1px solid var(--gc-color-border); border-radius:10px; color:var(--gc-color-text); font-size:13px; }.candidate-actions { display:flex; flex-wrap:wrap; gap:4px; }.inline-action { min-height:44px; padding:0 8px; border:0; background:transparent; color:var(--gc-color-brand-strong); font-size:12px; text-decoration:underline; }.dependency-hint { color:var(--gc-color-muted); font-size:11px; }.modal-backdrop { position:fixed; inset:0; z-index:var(--gc-layer-overlay); display:grid; padding:24px; place-items:center; background:rgba(25,39,32,.38); }.notice-modal { width:100%; max-width:360px; max-height:80vh; overflow-y:auto; padding:22px; border-radius:var(--gc-radius-lg); background:var(--gc-color-surface); box-shadow:var(--gc-shadow-overlay); }.modal-actions { display:flex; margin-top:14px; flex-direction:column; gap:8px; }
</style>
