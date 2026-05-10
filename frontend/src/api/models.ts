import { client, USE_MOCKS } from './client'
import { mock } from './mock'
import type { ModelInfo } from './types'

export async function listModels(): Promise<ModelInfo[]> {
  if (USE_MOCKS) return mock.listModels()
  const { data } = await client.get<ModelInfo[]>('/models')
  return data
}

export async function refreshModels(): Promise<{ discovered: number; updated_at: string }> {
  if (USE_MOCKS) return mock.refreshModels()
  const { data } = await client.post<{ discovered: number; updated_at: string }>('/models/refresh')
  return data
}
