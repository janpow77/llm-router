import { client, USE_MOCKS } from './client'
import { mock } from './mock'
import type { Spoke } from './types'

export async function listSpokes(): Promise<Spoke[]> {
  if (USE_MOCKS) return mock.listSpokes()
  const { data } = await client.get<Spoke[]>('/spokes')
  return data
}

export async function createSpoke(input: Partial<Spoke>): Promise<Spoke> {
  if (USE_MOCKS) return mock.createSpoke(input)
  const { data } = await client.post<Spoke>('/spokes', input)
  return data
}

export async function patchSpoke(id: string, input: Partial<Spoke>): Promise<Spoke> {
  if (USE_MOCKS) return mock.patchSpoke(id, input)
  const { data } = await client.patch<Spoke>(`/spokes/${id}`, input)
  return data
}

export async function deleteSpoke(id: string): Promise<void> {
  if (USE_MOCKS) { await mock.deleteSpoke(id); return }
  await client.delete(`/spokes/${id}`)
}

export async function spokeHealthCheck(id: string): Promise<Spoke> {
  if (USE_MOCKS) return mock.spokeHealthCheck(id)
  const { data } = await client.post<Spoke>(`/spokes/${id}/health-check`)
  return data
}
