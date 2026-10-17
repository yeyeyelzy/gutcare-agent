export interface RecordPageState<T> {
  items: T[]
  cursor: string | null
  error: string
  requestId: string
}

export interface RecordPage<T> {
  items: T[]
  next_cursor?: string | null
}

export function initialRecordPageState<T>(items: T[] = [], cursor: string | null = null): RecordPageState<T> {
  return { items, cursor, error: '', requestId: '' }
}

export function appendRecordPage<T>(state: RecordPageState<T>, page: RecordPage<T>): RecordPageState<T> {
  return {
    items: [...state.items, ...page.items],
    cursor: page.next_cursor ?? null,
    error: '',
    requestId: '',
  }
}

export function failRecordPage<T>(
  state: RecordPageState<T>,
  error: string,
  requestId = '',
): RecordPageState<T> {
  return { ...state, error, requestId }
}

export function clearRecordPageError<T>(state: RecordPageState<T>): RecordPageState<T> {
  return { ...state, error: '', requestId: '' }
}
