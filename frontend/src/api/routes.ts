import { client, USE_MOCKS } from './client'
import { mock } from './mock'
import type { RouteRule } from './types'

export async function listRoutes(): Promise<RouteRule[]> {
  if (USE_MOCKS) return mock.listRoutes()
  const { data } = await client.get<RouteRule[]>('/routes')
  return data
}

export async function createRoute(input: Partial<RouteRule>): Promise<RouteRule> {
  if (USE_MOCKS) return mock.createRoute(input)
  const { data } = await client.post<RouteRule>('/routes', input)
  return data
}

export async function patchRoute(id: string, input: Partial<RouteRule>): Promise<RouteRule> {
  if (USE_MOCKS) return mock.patchRoute(id, input)
  const { data } = await client.patch<RouteRule>(`/routes/${id}`, input)
  return data
}

export async function deleteRoute(id: string): Promise<void> {
  if (USE_MOCKS) { await mock.deleteRoute(id); return }
  await client.delete(`/routes/${id}`)
}
