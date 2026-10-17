import type { RequestClient } from './requestClient'
import type {
  MedicationCheckin, MedicationCheckinUpdate, MedicationPlan, MedicationPlanCreate,
  MedicationPlanPatch, MedicationPlanTransition, MedicationSchedule, MedicationSchedulePatch,
  MedicationScheduleWrite,
} from './openapiTypes'

export class MedicationApi {
  constructor(private readonly client: RequestClient) {}

  listPlans(): Promise<MedicationPlan[]> {
    return this.client.request({ method: 'GET', path: '/medication-plans' })
  }
  getPlan(id: string): Promise<MedicationPlan> {
    return this.client.request({ method: 'GET', path: `/medication-plans/${encodeURIComponent(id)}` })
  }
  createPlan(body: MedicationPlanCreate, key: string): Promise<MedicationPlan> {
    return this.client.request({ method: 'POST', path: '/medication-plans', data: body, idempotencyKey: key })
  }
  updatePlan(id: string, body: MedicationPlanPatch): Promise<MedicationPlan> {
    return this.client.request({ method: 'PATCH', path: `/medication-plans/${encodeURIComponent(id)}`, data: body })
  }
  deletePlan(id: string, recordVersion: number): Promise<void> {
    const query = new URLSearchParams({ record_version: String(recordVersion) })
    return this.client.request({ method: 'DELETE', path: `/medication-plans/${encodeURIComponent(id)}?${query}` })
  }
  transitionPlan(id: string, body: MedicationPlanTransition, key: string): Promise<MedicationPlan> {
    return this.client.request({ method: 'POST', path: `/medication-plans/${encodeURIComponent(id)}/transitions`, data: body, idempotencyKey: key })
  }
  listSchedules(planId: string): Promise<MedicationSchedule[]> {
    return this.client.request({ method: 'GET', path: `/medication-plans/${encodeURIComponent(planId)}/schedules` })
  }
  createSchedule(planId: string, body: MedicationScheduleWrite, key: string): Promise<MedicationSchedule> {
    return this.client.request({ method: 'POST', path: `/medication-plans/${encodeURIComponent(planId)}/schedules`, data: body, idempotencyKey: key })
  }
  updateSchedule(id: string, body: MedicationSchedulePatch): Promise<MedicationSchedule> {
    return this.client.request({ method: 'PATCH', path: `/medication-schedules/${encodeURIComponent(id)}`, data: body })
  }
  deleteSchedule(id: string, recordVersion: number): Promise<void> {
    const query = new URLSearchParams({ record_version: String(recordVersion) })
    return this.client.request({ method: 'DELETE', path: `/medication-schedules/${encodeURIComponent(id)}?${query}` })
  }
  listCheckins(start: string, end: string): Promise<MedicationCheckin[]> {
    const query = new URLSearchParams({ start, end })
    return this.client.request({ method: 'GET', path: `/medication-checkins?${query}` })
  }
  listTodayCheckins(): Promise<MedicationCheckin[]> {
    return this.client.request({ method: 'GET', path: '/medication-checkins/today' })
  }
  updateCheckin(id: string, body: MedicationCheckinUpdate): Promise<MedicationCheckin> {
    return this.client.request({ method: 'PATCH', path: `/medication-checkins/${encodeURIComponent(id)}`, data: body })
  }
}
