import { client, USE_MOCKS } from './client'
import { mock } from './mock'
import type { QuotaUsage } from './types'

export async function getQuota(appId: string): Promise<QuotaUsage> {
  if (USE_MOCKS) return mock.getQuota(appId)
  const { data } = await client.get<QuotaUsage>(`/quotas/${appId}`)
  return data
}

export async function patchQuota(
  appId: string,
  input: Partial<{ rpm: number; concurrent: number; daily_tokens: number }>
): Promise<QuotaUsage> {
  if (USE_MOCKS) return mock.patchQuota(appId, input)
  const { data } = await client.patch<QuotaUsage>(`/quotas/${appId}`, input)
  return data
}
