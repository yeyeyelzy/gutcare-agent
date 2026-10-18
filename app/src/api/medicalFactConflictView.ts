import type { MedicalFactConflict } from './openapiTypes'

export type MedicalFactConflictMember = NonNullable<MedicalFactConflict['members']>[number]
export type MedicalFactConflictStatusFilter = 'open' | 'resolved' | 'invalidated' | 'all'

export function conflictStatusLabel(status: MedicalFactConflict['status']): string {
  return ({ open: '待本人核对', resolved: '已选择保留双方', invalidated: '来源已失效' } as const)[status]
}

export function conflictFieldLabel(fieldCode: MedicalFactConflictMember['field_code']): string {
  return fieldCode === 'test_item' ? '检验项目' : '检验结果'
}

/** Only render scalar item names or the controlled result member; never stringify backend objects. */
export function conflictMemberValueLabel(member: MedicalFactConflictMember): string {
  if (member.field_code === 'test_item') return typeof member.value === 'string' ? member.value.slice(0, 200) : '字段内容暂不可显示'
  if (!isPlainRecord(member.value)) return '字段内容暂不可显示'
  const result = member.value.result
  if (typeof result === 'string' && result.length > 0) return result.slice(0, 200)
  if (typeof result === 'number' && Number.isFinite(result)) return String(result)
  return '字段内容暂不可显示'
}

export function conflictMemberUnitLabel(unit: string | null | undefined): string | null {
  return typeof unit === 'string' && unit.trim().length > 0 ? unit.trim().slice(0, 32) : null
}

export function conflictSampledOnLabel(value: string | null): string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : '采样日期未记录'
}

export function conflictDocumentIdLabel(value: string): string {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value) ? value : '来源档案不可用'
}

export function canKeepBoth(conflict: MedicalFactConflict): boolean {
  return conflict.status === 'open' && Array.isArray(conflict.members) && conflict.members.length >= 2
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false
  const prototype = Object.getPrototypeOf(value)
  return prototype === Object.prototype || prototype === null
}
