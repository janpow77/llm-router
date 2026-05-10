import { client, USE_MOCKS } from './client'
import { mock } from './mock'
import type { App, AppDetail } from './types'

export async function listApps(): Promise<App[]> {
  if (USE_MOCKS) return mock.listApps()
  const { data } = await client.get<App[]>('/apps')
  return data
}

export async function getApp(id: string): Promise<AppDetail> {
  if (USE_MOCKS) return mock.getApp(id)
  const { data } = await client.get<AppDetail>(`/apps/${id}`)
  return data
}

export async function createApp(input: Partial<App>): Promise<App> {
  if (USE_MOCKS) return mock.createApp(input)
  const { data } = await client.post<App>('/apps', input)
  return data
}

export async function patchApp(id: string, input: Partial<App>): Promise<App> {
  if (USE_MOCKS) return mock.patchApp(id, input)
  const { data } = await client.patch<App>(`/apps/${id}`, input)
  return data
}

export async function deleteApp(id: string): Promise<void> {
  if (USE_MOCKS) { await mock.deleteApp(id); return }
  await client.delete(`/apps/${id}`)
}

export async function rotateAppKey(id: string): Promise<{ api_key: string }> {
  if (USE_MOCKS) return mock.rotateAppKey(id)
  const { data } = await client.post<{ api_key: string }>(`/apps/${id}/rotate-key`)
  return data
}

export async function toggleAppEnabled(id: string): Promise<App> {
  if (USE_MOCKS) return mock.toggleAppEnabled(id)
  const { data } = await client.post<App>(`/apps/${id}/toggle-enabled`)
  return data
}
