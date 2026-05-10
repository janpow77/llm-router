import { client, USE_MOCKS } from './client'
import { mock } from './mock'
import type { AuditEntry } from './types'

export interface AuditFilter {
  actor?: string
  action?: string
  limit?: number
  since?: string
}

export async function listAudit(params: AuditFilter = {}): Promise<AuditEntry[]> {
  if (USE_MOCKS) return mock.listAudit(params)
  const { data } = await client.get<AuditEntry[]>('/audit', { params })
  return data
}
