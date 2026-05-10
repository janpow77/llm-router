import { client, USE_MOCKS } from './client'
import { mock } from './mock'
import type { DashboardStats, TimeseriesPoint, HealthInfo } from './types'

export async function getHealth(): Promise<HealthInfo> {
  if (USE_MOCKS) return mock.health()
  const { data } = await client.get<HealthInfo>('/health')
  return data
}

export async function getDashboard(): Promise<DashboardStats> {
  if (USE_MOCKS) return mock.dashboard()
  const { data } = await client.get<DashboardStats>('/dashboard')
  return data
}

export async function getTimeseries(bucket = '1h', hours = 24): Promise<TimeseriesPoint[]> {
  if (USE_MOCKS) return mock.timeseries()
  const { data } = await client.get<TimeseriesPoint[]>('/dashboard/timeseries', {
    params: { bucket, hours },
  })
  return data
}
