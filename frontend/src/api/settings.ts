import { client, USE_MOCKS } from './client'
import { mock } from './mock'
import type { Settings } from './types'

export async function getSettings(): Promise<Settings> {
  if (USE_MOCKS) return mock.getSettings()
  const { data } = await client.get<Settings>('/settings')
  return data
}

export async function patchSettings(input: Partial<Settings>): Promise<Settings> {
  if (USE_MOCKS) return mock.patchSettings(input)
  const { data } = await client.patch<Settings>('/settings', input)
  return data
}
