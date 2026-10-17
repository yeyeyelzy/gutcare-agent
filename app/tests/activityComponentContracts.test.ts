import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const workspace = readFileSync(new URL('../src/components/ActivityWorkspace.vue', import.meta.url), 'utf8')

describe('F07 protected activity workspace', () => {
  it('keeps page-level auth gate before API access and supports all CRUD views', () => {
    expect(workspace).toContain('canRenderRoute(props.routeName, auth.state)')
    expect(workspace).toContain('router?.requireAuthentication(props.routeName)')
    expect(workspace).toContain('api.list({ limit: 30 })')
    expect(workspace).toContain('api.get(id)')
    expect(workspace).toContain('api.create(result.body)')
    expect(workspace).toContain('record_version: current.value!.record_version')
    expect(workspace).toContain('api.delete(removed.id, removed.record_version)')
  })

  it('distinguishes loading/empty/error/offline/pagination and preserves records on conflict', () => {
    for (const id of ['activity-loading', 'activity-empty', 'activity-error', 'activity-more-error', 'activity-more-retry', 'activity-delete-confirm']) expect(workspace).toContain(id)
    expect(workspace).toContain('当前处于离线状态')
    expect(workspace).toContain('failRecordPage(state, problemMessage.value, requestId.value)')
    expect(workspace).toContain('records.value = failed.items')
    expect(workspace).toContain('RECORD_VERSION_CONFLICT')
    expect(workspace).toContain('草稿已保留，尚未提交')
  })

  it('uses frozen F07 field names, bounded other description and hides bottom navigation', () => {
    for (const token of ['activity_type', 'subjective_feeling', 'duration_minutes', 'occurred_at']) expect(workspace).toContain(token)
    expect(workspace).toContain('maxlength="160"')
    expect(workspace).toContain('activityType')
    expect(workspace).toContain('draft.activityType === \'other\'')
    expect(workspace).toContain('ActivityWorkspaceRouteName')
    expect(workspace).not.toContain('GcBottomNav')
    expect(workspace).not.toMatch(/patient_id|device_source|ai_source|diagnos|处方|因果/)
  })

  it('shows the draft beside latest server data and requires explicit resolution before PATCH', () => {
    for (const token of [
      'activity-conflict-draft', 'activity-conflict-latest', 'activity-conflict-discard',
      'activity-conflict-rebase', 'activity-conflict-rebased', '确认以最新版本保存',
      'loadActivityConflictLatest(api, editingId.value)', 'keepActivityConflictDraft({ ...draft }, latest)',
      'discardActivityConflictDraft(latest)',
    ]) expect(workspace).toContain(token)
    expect(workspace).toContain(':disabled="busy || conflict"')
    expect(workspace).toContain('if (isVersionConflict(error) && editing.value && editingId.value) await loadConflictLatest()')
    expect(workspace).not.toContain('reloadConflict')
  })
})
