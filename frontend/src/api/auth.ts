import { client, USE_MOCKS } from './client'
import { mock } from './mock'

export interface LoginResponse { token: string; expires_at: string }
export interface MeResponse { logged_in: boolean; expires_at: string }

export async function login(password: string): Promise<LoginResponse> {
  if (USE_MOCKS) return mock.login(password)
  const { data } = await client.post<LoginResponse>('/auth/login', { password })
  return data
}

export async function logout(): Promise<void> {
  if (USE_MOCKS) { await mock.logout(); return }
  await client.post('/auth/logout')
}

export async function me(): Promise<MeResponse> {
  if (USE_MOCKS) return mock.me()
  const { data } = await client.get<MeResponse>('/auth/me')
  return data
}
