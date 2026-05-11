import { describe, it, expect } from 'vitest'
import * as appsApi from '../src/api/apps'
import * as spokesApi from '../src/api/spokes'
import * as modelsApi from '../src/api/models'
import * as routesApi from '../src/api/routes'
import * as logsApi from '../src/api/logs'
import * as auditApi from '../src/api/audit'
import * as dashboardApi from '../src/api/dashboard'
import * as settingsApi from '../src/api/settings'

describe('Mock-API', () => {
  it('liefert Apps', async () => {
    const apps = await appsApi.listApps()
    expect(apps.length).toBeGreaterThan(0)
    expect(apps[0]).toHaveProperty('name')
    expect(apps[0]).toHaveProperty('quota')
  })

  it('liefert Spokes mit GPU-Info', async () => {
    const spokes = await spokesApi.listSpokes()
    expect(spokes.length).toBeGreaterThan(0)
    const withGpu = spokes.find(s => s.gpu_info !== null)
    expect(withGpu?.gpu_info?.vram_total_mb).toBeGreaterThan(0)
  })

  it('liefert Modelle quer über Spokes', async () => {
    const models = await modelsApi.listModels()
    expect(models.length).toBeGreaterThan(0)
    expect(models[0].quantization).toBeTruthy()
  })

  it('liefert Routes sortierbar nach Priority', async () => {
    const routes = await routesApi.listRoutes()
    const sorted = [...routes].sort((a, b) => a.priority - b.priority)
    expect(sorted[0].priority).toBeLessThanOrEqual(sorted[sorted.length - 1].priority)
  })

  it('liefert Logs', async () => {
    const logs = await logsApi.listLogs({ limit: 10 })
    expect(logs.length).toBeLessThanOrEqual(10)
    expect(logs[0]).toHaveProperty('status')
  })

  it('liefert Audit-Einträge', async () => {
    const audit = await auditApi.listAudit()
    expect(audit.length).toBeGreaterThan(0)
    expect(audit[0]).toHaveProperty('action')
  })

  it('liefert Dashboard-Stats', async () => {
    const d = await dashboardApi.getDashboard()
    expect(d.requests_today).toBeGreaterThan(0)
    expect(d.top_apps.length).toBeGreaterThan(0)
  })

  it('liefert Settings', async () => {
    const s = await settingsApi.getSettings()
    expect(s.router_version).toBeTruthy()
    expect(s.default_quotas.rpm).toBeGreaterThan(0)
  })
})
