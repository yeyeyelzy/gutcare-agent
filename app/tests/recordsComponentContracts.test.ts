import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const workspace = readFileSync(new URL('../src/components/RecordWorkspace.vue', import.meta.url), 'utf8')

describe('F03-F05 protected record pages', () => {
  it('keeps loading, true empty, failure, offline, confirmation and conflict states distinct', () => {
    expect(workspace).toContain('state="loading"')
    expect(workspace).toContain('此范围内暂无记录')
    expect(workspace).toContain('当前处于离线状态')
    expect(workspace).toContain('delete-confirm')
    expect(workspace).toContain('RECORD_VERSION_CONFLICT')
    expect(workspace).toContain('重新载入最新记录')
  })

  it('shows an append-only pagination error and retries the same cursor without hiding loaded records', () => {
    expect(workspace).toContain('data-testid="record-more-error"')
    expect(workspace).toContain('test-id="record-more-retry"')
    expect(workspace).toContain('failRecordPage(startingState, problemMessage.value, requestId.value)')
    expect(workspace).toContain('records.value = failed.items')
    expect(workspace).toContain('nextCursor.value = failed.cursor')
    expect(workspace).toContain('cursor: startingState.cursor ?? undefined')
    expect(workspace).toContain('appendRecordPage(startingState, result)')
  })

  it('gates before rendering, hides tab navigation on secondary pages and loads symptom history', () => {
    expect(workspace).toContain('canRenderRoute(props.routeName, auth.state)')
    expect(workspace).toContain('requireAuthentication(props.routeName)')
    expect(workspace).toContain('api.symptomStatusHistory(currentRecord.value.id)')
    expect(workspace).not.toContain('GcBottomNav')
    expect(workspace).toContain('router?.switchTab(\'records\')')
    expect(workspace).not.toMatch(/patient_id|source_type|diagnos|caused by|导致/)
  })
})
