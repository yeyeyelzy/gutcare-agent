import { describe, expect, it } from 'vitest'
import {
  appendRecordPage,
  clearRecordPageError,
  failRecordPage,
  initialRecordPageState,
} from '../src/api/recordPagination'

describe('record pagination', () => {
  it('retains existing items and cursor on failure, then appends on retry success', () => {
    const first = { id: 'record-1' }
    const second = { id: 'record-2' }
    const initial = initialRecordPageState([first], 'cursor-1')
    const failed = failRecordPage(initial, '网络暂不可用，请稍后重试。', 'request-1')

    expect(failed).toEqual({
      items: [first],
      cursor: 'cursor-1',
      error: '网络暂不可用，请稍后重试。',
      requestId: 'request-1',
    })

    const retryStart = clearRecordPageError(failed)
    const recovered = appendRecordPage(retryStart, { items: [second], next_cursor: null })
    expect(recovered).toEqual({ items: [first, second], cursor: null, error: '', requestId: '' })
  })
})
