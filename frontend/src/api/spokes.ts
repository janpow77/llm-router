import { client, USE_MOCKS } from './client'
import { mock } from './mock'
import type { Spoke } from './types'

export interface TestConnectionRequest {
  base_url: string
  auth_header?: string
  auth_value?: string
  test_endpoint?: string
}

export interface TestConnectionResponse {
  ok: boolean
  status?: number
  models_count?: number
  sample_models?: string[]
  latency_ms?: number
  error?: string
}

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

/**
 * Testet die Connection zu einem Provider-Endpoint, ohne ihn anzulegen.
 * Wird vom „Test-Connection"-Button im SpokeFormModal benutzt.
 */
export async function testSpokeConnection(
  payload: TestConnectionRequest,
): Promise<TestConnectionResponse> {
  if (USE_MOCKS) {
    // Mock: simuliert OK fuer http(s)-URLs, sonst Fehler.
    const ok = /^https?:\/\//.test(payload.base_url)
    return ok
      ? { ok: true, status: 200, models_count: 3, sample_models: ['mock-llm-a', 'mock-llm-b'], latency_ms: 42 }
      : { ok: false, error: 'invalid base_url' }
  }
  const { data } = await client.post<TestConnectionResponse>('/spokes/test-connection', payload)
  return data
}
