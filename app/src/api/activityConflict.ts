import type { ActivityApi } from './activityApi'
import { activityToDraft } from './activityForm'
import type { ActivityDraft } from './activityForm'
import type { ActivityRecord } from './openapiTypes'

export interface ActivityConflictResolution {
  record: ActivityRecord
  draft: ActivityDraft
}

/** Read the competing version only. This helper cannot submit or mutate a record. */
export function loadActivityConflictLatest(api: Pick<ActivityApi, 'get'>, id: string): Promise<ActivityRecord> {
  return api.get(id)
}

/** Explicitly abandon proposed edits and copy the server version into the form. */
export function discardActivityConflictDraft(latest: ActivityRecord): ActivityConflictResolution {
  return { record: latest, draft: activityToDraft(latest) }
}

/** Explicitly retain every proposed field while advancing only the optimistic-lock base. */
export function keepActivityConflictDraft(draft: ActivityDraft, latest: ActivityRecord): ActivityConflictResolution {
  return { record: latest, draft: { ...draft } }
}
