import type { ConsentStatus, RecordImageAttachment, RecordImageCandidate, RecordImageDisclosure, RecordImageRecognitionRequest } from './openapiTypes'

export class VisibleOperationGate {
  private generation = 0
  private visible = true
  private disposed = false

  snapshot(): number { return this.generation }
  isCurrent(snapshot: number): boolean { return this.visible && !this.disposed && snapshot === this.generation }
  hide(): void { this.visible = false; this.generation++ }
  show(): void { if (!this.disposed) { this.visible = true; this.generation++ } }
  invalidate(): void { this.generation++ }
  dispose(): void { this.visible = false; this.disposed = true; this.generation++ }
}

export async function runVisibleOperation<T>(gate: VisibleOperationGate, operation: (isCurrent: () => boolean) => Promise<T>, onSuccess: (value: T) => void, onFailure: (error: unknown) => void): Promise<void> {
  const token = gate.snapshot()
  const isCurrent = () => gate.isCurrent(token)
  try {
    const value = await operation(isCurrent)
    if (isCurrent()) onSuccess(value)
  } catch (error) {
    if (isCurrent()) onFailure(error)
  }
}

export function hasRecordImageConsent(statuses: ConsentStatus[], purpose: 'attachment' | 'recognition'): boolean {
  const required = purpose === 'attachment'
    ? ['health_data_processing', 'sensitive_image']
    : ['health_data_processing', 'sensitive_image', 'third_party_ai']
  return required.every((type) => statuses.some((status) => status.consent_type === type && status.granted))
}

export function disclosureIsUsable(disclosure: RecordImageDisclosure | null | undefined): disclosure is RecordImageDisclosure & { policy_version: string } {
  return Boolean(disclosure?.enabled && disclosure.policy_version)
}

export function canRetryRecordImageRequest(request: RecordImageRecognitionRequest | null, attachmentCount: number): boolean {
  return attachmentCount > 0 && Boolean(request && ['failed', 'cancelled', 'invalidated'].includes(request.status))
}

export function recordImageLimit(kind: 'diet' | 'stool'): number { return kind === 'diet' ? 10 : 1 }

export async function submitRecordImageRequest<T>(input: {
  explicitlyRetry: boolean; retryRequestId?: string; body: { record_version: number; image_set_version: number; disclosure_token: string };
  create: (body: { record_version: number; image_set_version: number; disclosure_token: string }) => Promise<T>;
  retry: (requestId: string, body: { record_version: number; image_set_version: number; disclosure_token: string }) => Promise<T>;
}): Promise<T> {
  if (input.explicitlyRetry && input.retryRequestId) return input.retry(input.retryRequestId, input.body)
  return input.create(input.body)
}

export function candidateRequiresFoodName(candidate: RecordImageCandidate, candidates: RecordImageCandidate[]): boolean {
  if (candidate.candidate_type !== 'food_category' && candidate.candidate_type !== 'portion_description') return false
  return candidates.some((item) => item.candidate_type === 'food_name'
    && item.candidate_group_key === candidate.candidate_group_key && item.status === 'pending')
}

export async function mutateThenRefresh<T, M>(previous: T, mutate: () => Promise<M>, refresh: () => Promise<T>, isCurrent: () => boolean): Promise<{
  mutation: M | null; value: T; refreshed: boolean; interrupted: boolean; refreshError?: unknown;
}> {
  const mutation = await mutate()
  if (!isCurrent()) return { mutation, value: previous, refreshed: false, interrupted: true }
  try {
    const value = await refresh()
    if (!isCurrent()) return { mutation, value: previous, refreshed: false, interrupted: true }
    return { mutation, value, refreshed: true, interrupted: false }
  } catch (refreshError) {
    return { mutation, value: previous, refreshed: false, interrupted: !isCurrent(), refreshError }
  }
}

export interface WorkflowImage { path: string; sizeBytes: number; contentType: 'image/jpeg' | 'image/png' }
export type WorkflowImageState = 'selecting' | 'uploading' | 'scanning' | 'clean' | 'error'

export async function uploadSelectedRecordImages(options: {
  selected: WorkflowImage[];
  isCurrent: () => boolean;
  read: (path: string) => Promise<ArrayBuffer>;
  upload: (image: WorkflowImage, bytes: ArrayBuffer, onScanning: () => void, isCurrent: () => boolean) => Promise<RecordImageAttachment | null>;
  cleanup: (path: string) => void;
  stopOnError?: (error: unknown) => boolean;
  onState: (index: number, state: WorkflowImageState, error?: unknown) => void;
  onAttached: (index: number, attachment: RecordImageAttachment) => void;
}): Promise<{ interrupted: boolean; stopped: boolean; attached: RecordImageAttachment[] }> {
  const attached: RecordImageAttachment[] = []
  const cleanedIndexes = new Set<number>()
  let interrupted = false
  let stopped = false
  let index = 0
  try {
    for (; index < options.selected.length; index++) {
      const image = options.selected[index]!
      if (!options.isCurrent()) { interrupted = true; break }
      let bytes: ArrayBuffer | null = null
      try {
        options.onState(index, 'selecting')
        if (!options.isCurrent()) { interrupted = true; break }
        options.onState(index, 'uploading')
        bytes = await options.read(image.path)
        if (!options.isCurrent()) { interrupted = true; break }
        if (bytes.byteLength <= 0 || bytes.byteLength > MAX_IMAGE_BYTES) throw new Error('图片大小无效。')
        const result = await options.upload(image, bytes, () => {
          if (options.isCurrent()) options.onState(index, 'scanning')
        }, options.isCurrent)
        if (!options.isCurrent() || !result) { interrupted = true; break }
        attached.push(result)
        options.onAttached(index, result)
        options.onState(index, 'clean')
      } catch (error) {
        if (!options.isCurrent()) { interrupted = true; break }
        options.onState(index, 'error', error)
        if (options.stopOnError?.(error)) { stopped = true; break }
      } finally {
        if (bytes) new Uint8Array(bytes).fill(0)
        options.cleanup(image.path)
        cleanedIndexes.add(index)
      }
    }
  } finally {
    for (let cleanupIndex = 0; cleanupIndex < options.selected.length; cleanupIndex++) {
      if (!cleanedIndexes.has(cleanupIndex)) options.cleanup(options.selected[cleanupIndex]!.path)
    }
  }
  return { interrupted, stopped, attached }
}

const MAX_IMAGE_BYTES = 10 * 1024 * 1024
