// Mock-Daten für Frontend-Entwicklung ohne Backend.
// Aktivierbar über VITE_USE_MOCKS=true beim Vite-Start.
import type {
  App, AppDetail, Spoke, ModelInfo, RouteRule, QuotaUsage,
  LogEntry, AuditEntry, DashboardStats, TimeseriesPoint, HealthInfo, Settings,
} from './types'

const now = () => new Date().toISOString()
const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString()
const hoursAgo = (h: number) => new Date(Date.now() - h * 3600_000).toISOString()

const APPS: App[] = [
  {
    id: 'app_audit_designer',
    name: 'audit_designer',
    description: 'Hauptanwendung (NUC)',
    api_key_preview: 'ad_••••f4a2',
    allowed_models: ['qwen3:14b', 'qwen3:8b', 'nomic-embed-text'],
    quota: { rpm: 240, concurrent: 16, daily_tokens: 5_000_000 },
    enabled: true,
    request_count_today: 9421,
    created_at: hoursAgo(72 * 24),
    updated_at: hoursAgo(2),
  },
  {
    id: 'app_auditworkshop',
    name: 'auditworkshop',
    description: 'Workshop-Demo (Hetzner CCX23)',
    api_key_preview: 'aw_••••81c0',
    allowed_models: ['qwen3:14b'],
    quota: { rpm: 120, concurrent: 8, daily_tokens: 2_000_000 },
    enabled: true,
    request_count_today: 4203,
    created_at: hoursAgo(48 * 24),
    updated_at: hoursAgo(8),
  },
  {
    id: 'app_flowinvoice',
    name: 'flowinvoice',
    description: 'Rechnungsverarbeitung (NUC)',
    api_key_preview: 'fi_••••2a91',
    allowed_models: ['qwen3:8b', 'qwen3:14b'],
    quota: { rpm: 120, concurrent: 6, daily_tokens: 1_500_000 },
    enabled: true,
    request_count_today: 3122,
    created_at: hoursAgo(120 * 24),
    updated_at: hoursAgo(36),
  },
  {
    id: 'app_default',
    name: 'default',
    description: 'Fallback für Tests / unbekannte Clients',
    api_key_preview: '—',
    allowed_models: ['*'],
    quota: { rpm: 30, concurrent: 2, daily_tokens: 500_000 },
    enabled: true,
    request_count_today: 1683,
    created_at: hoursAgo(180 * 24),
    updated_at: hoursAgo(120),
  },
  {
    id: 'app_test',
    name: 'test',
    description: 'Manuelle curl-Tests',
    api_key_preview: 'tt_••••0001',
    allowed_models: ['*'],
    quota: { rpm: 60, concurrent: 2, daily_tokens: 100_000 },
    enabled: false,
    request_count_today: 0,
    created_at: hoursAgo(40 * 24),
    updated_at: hoursAgo(240),
  },
]

const SPOKES: Spoke[] = [
  {
    id: 'spk_nuc_egpu',
    name: 'nuc-egpu',
    base_url: 'http://100.102.132.11:11434',
    type: 'ollama',
    status: 'online',
    last_check_at: minutesAgo(0.5),
    models: ['qwen3:14b', 'qwen3:8b', 'nomic-embed-text', 'llama3.2:3b'],
    gpu_info: {
      device: 'NVIDIA GeForce RTX 5070 Ti',
      vram_total_mb: 16384,
      vram_used_mb: 14820,
      utilization_pct: 78,
    },
  },
  {
    id: 'spk_hetzner_ccx23',
    name: 'hetzner-ccx23',
    base_url: 'http://10.0.0.5:11434',
    type: 'ollama',
    status: 'degraded',
    last_check_at: minutesAgo(2),
    models: ['qwen3:14b'],
    gpu_info: null,
  },
]

const MODELS: ModelInfo[] = [
  { id: 'qwen3:14b@nuc-egpu', name: 'qwen3:14b', spoke_id: 'spk_nuc_egpu', spoke_name: 'nuc-egpu', size_gb: 15.2, context_length: 32768, quantization: 'Q8_0' },
  { id: 'qwen3:8b@nuc-egpu', name: 'qwen3:8b', spoke_id: 'spk_nuc_egpu', spoke_name: 'nuc-egpu', size_gb: 8.4, context_length: 32768, quantization: 'Q8_0' },
  { id: 'nomic-embed-text@nuc-egpu', name: 'nomic-embed-text', spoke_id: 'spk_nuc_egpu', spoke_name: 'nuc-egpu', size_gb: 0.27, context_length: 8192, quantization: 'F16' },
  { id: 'llama3.2:3b@nuc-egpu', name: 'llama3.2:3b', spoke_id: 'spk_nuc_egpu', spoke_name: 'nuc-egpu', size_gb: 3.0, context_length: 131072, quantization: 'Q4_K_M' },
  { id: 'qwen3:14b@hetzner-ccx23', name: 'qwen3:14b', spoke_id: 'spk_hetzner_ccx23', spoke_name: 'hetzner-ccx23', size_gb: 15.2, context_length: 32768, quantization: 'Q8_0' },
]

const ROUTES: RouteRule[] = [
  { id: 'rt_1', model_glob: 'qwen3:14b', spoke_id: 'spk_nuc_egpu', spoke_name: 'nuc-egpu', priority: 10, enabled: true },
  { id: 'rt_2', model_glob: 'qwen3:8b', spoke_id: 'spk_nuc_egpu', spoke_name: 'nuc-egpu', priority: 20, enabled: true },
  { id: 'rt_3', model_glob: 'nomic-embed-text', spoke_id: 'spk_nuc_egpu', spoke_name: 'nuc-egpu', priority: 30, enabled: true },
  { id: 'rt_4', model_glob: '*', spoke_id: 'spk_nuc_egpu', spoke_name: 'nuc-egpu', priority: 999, enabled: true },
]

const STATUSES: LogEntry['status'][] = ['ok', 'ok', 'ok', 'ok', 'ok', 'ok', 'ok', 'ok', 'ok', 'error']
const MODEL_NAMES = ['qwen3:14b', 'qwen3:8b', 'nomic-embed-text', 'llama3.2:3b']

function makeLog(i: number): LogEntry {
  const status = STATUSES[i % STATUSES.length]
  return {
    ts: new Date(Date.now() - i * 8000).toISOString(),
    request_id: `req_${String(99999 - i).padStart(8, '0')}`,
    app_id: APPS[i % APPS.length].id,
    model: MODEL_NAMES[i % MODEL_NAMES.length],
    spoke_id: SPOKES[i % SPOKES.length].id,
    status,
    duration_ms: 200 + Math.floor(Math.random() * 3000),
    prompt_tokens: 50 + Math.floor(Math.random() * 500),
    completion_tokens: 100 + Math.floor(Math.random() * 1500),
    error: status === 'error' ? 'Connection refused (spoke timeout)' : null,
  }
}

const LOGS: LogEntry[] = Array.from({ length: 200 }, (_, i) => makeLog(i))

const AUDIT: AuditEntry[] = [
  { id: 'aud_001', ts: minutesAgo(15), actor: 'admin', action: 'app.update', target: 'app_audit_designer',
    before: { quota: { rpm: 100 } }, after: { quota: { rpm: 240 } } },
  { id: 'aud_002', ts: hoursAgo(1), actor: 'admin', action: 'app.create', target: 'app_test',
    before: null, after: { name: 'test', enabled: false } },
  { id: 'aud_003', ts: hoursAgo(2), actor: 'admin', action: 'spoke.health-check', target: 'spk_hetzner_ccx23',
    before: { status: 'online' }, after: { status: 'degraded' } },
  { id: 'aud_004', ts: hoursAgo(4), actor: 'admin', action: 'route.create', target: 'rt_4',
    before: null, after: { model_glob: '*', spoke_id: 'spk_nuc_egpu', priority: 999 } },
  { id: 'aud_005', ts: hoursAgo(8), actor: 'admin', action: 'app.rotate-key', target: 'app_audit_designer',
    before: { api_key_preview: 'ad_••••aaaa' }, after: { api_key_preview: 'ad_••••f4a2' } },
  { id: 'aud_006', ts: hoursAgo(24), actor: 'admin', action: 'settings.update', target: 'settings',
    before: { log_retention_days: 14 }, after: { log_retention_days: 30 } },
]

function makeTimeseries(): TimeseriesPoint[] {
  const points: TimeseriesPoint[] = []
  for (let h = 23; h >= 0; h--) {
    points.push({
      ts: hoursAgo(h),
      requests: 200 + Math.floor(Math.random() * 800) + (h < 8 ? 0 : 200),
      tokens: 50_000 + Math.floor(Math.random() * 200_000),
      errors: Math.floor(Math.random() * 5),
      mean_latency_ms: 600 + Math.floor(Math.random() * 800),
    })
  }
  return points
}

const DASHBOARD: DashboardStats = {
  requests_today: 18429,
  tokens_today: 4_283_910,
  errors_today: 12,
  mean_latency_ms: 842,
  p95_latency_ms: 2410,
  active_apps: APPS.filter(a => a.enabled).length,
  active_spokes: SPOKES.filter(s => s.status === 'online').length,
  top_apps: APPS.map(a => ({ app_id: a.id, name: a.name, count: a.request_count_today }))
    .sort((a, b) => b.count - a.count).slice(0, 5),
  top_models: [
    { model: 'qwen3:14b', count: 12932 },
    { model: 'qwen3:8b', count: 4012 },
    { model: 'nomic-embed-text', count: 1283 },
    { model: 'llama3.2:3b', count: 202 },
  ],
}

const HEALTH: HealthInfo = {
  status: 'ok',
  version: '0.1.0',
  started_at: hoursAgo(38),
  spokes_health: SPOKES.map(s => ({ spoke_id: s.id, status: s.status, last_check_at: s.last_check_at })),
}

const SETTINGS: Settings = {
  router_version: '0.1.0',
  uptime_seconds: 38291,
  log_retention_days: 30,
  default_quotas: { rpm: 60, concurrent: 4, daily_tokens: 1_000_000 },
  data_dir: '/data',
  config_path: '/etc/llm-router/config.yaml',
}

// Mutable copies (so create/update/delete actually have effect in mocked dev)
const state = {
  apps: [...APPS],
  spokes: [...SPOKES],
  models: [...MODELS],
  routes: [...ROUTES],
  logs: [...LOGS],
  audit: [...AUDIT],
  settings: { ...SETTINGS },
}

function delay<T>(value: T, ms = 120): Promise<T> {
  return new Promise(resolve => setTimeout(() => resolve(value), ms))
}

export const mock = {
  // auth
  login: (password: string) =>
    password === 'admin'
      ? delay({ token: 'mock-token-' + Date.now(), expires_at: new Date(Date.now() + 86_400_000).toISOString() })
      : Promise.reject(new Error('Invalid password')),
  me: () => delay({ logged_in: true, expires_at: new Date(Date.now() + 86_400_000).toISOString() }),
  logout: () => delay(null, 50),

  // health & dashboard
  health: () => delay(HEALTH),
  dashboard: () => delay({ ...DASHBOARD, active_apps: state.apps.filter(a => a.enabled).length, active_spokes: state.spokes.filter(s => s.status === 'online').length }),
  timeseries: () => delay(makeTimeseries()),

  // apps
  listApps: () => delay([...state.apps]),
  getApp: (id: string): Promise<AppDetail> => {
    const app = state.apps.find(a => a.id === id)
    if (!app) return Promise.reject(new Error('App not found'))
    return delay({ ...app, recent_requests: state.logs.filter(l => l.app_id === id).slice(0, 50) })
  },
  createApp: (data: Partial<App>): Promise<App> => {
    const id = `app_${data.name?.toLowerCase().replace(/\W+/g, '_') || Date.now()}`
    const fullKey = id.slice(4, 6) + '_' + Math.random().toString(36).slice(2, 26)
    const app: App = {
      id,
      name: data.name || 'unnamed',
      description: data.description || '',
      api_key_preview: fullKey.slice(0, 3) + '••••' + fullKey.slice(-4),
      api_key: fullKey,
      allowed_models: data.allowed_models || ['*'],
      quota: data.quota || { rpm: 60, concurrent: 4, daily_tokens: 1_000_000 },
      enabled: data.enabled ?? true,
      request_count_today: 0,
      created_at: now(),
      updated_at: now(),
    }
    state.apps.push(app)
    return delay(app)
  },
  patchApp: (id: string, data: Partial<App>): Promise<App> => {
    const idx = state.apps.findIndex(a => a.id === id)
    if (idx === -1) return Promise.reject(new Error('App not found'))
    state.apps[idx] = { ...state.apps[idx], ...data, updated_at: now() }
    return delay(state.apps[idx])
  },
  deleteApp: (id: string) => {
    state.apps = state.apps.filter(a => a.id !== id)
    return delay(null)
  },
  rotateAppKey: (id: string) => {
    const idx = state.apps.findIndex(a => a.id === id)
    if (idx === -1) return Promise.reject(new Error('App not found'))
    const fullKey = id.slice(4, 6) + '_' + Math.random().toString(36).slice(2, 26)
    state.apps[idx].api_key_preview = fullKey.slice(0, 3) + '••••' + fullKey.slice(-4)
    state.apps[idx].updated_at = now()
    return delay({ api_key: fullKey })
  },
  toggleAppEnabled: (id: string) => {
    const idx = state.apps.findIndex(a => a.id === id)
    if (idx === -1) return Promise.reject(new Error('App not found'))
    state.apps[idx].enabled = !state.apps[idx].enabled
    state.apps[idx].updated_at = now()
    return delay(state.apps[idx])
  },

  // spokes
  listSpokes: () => delay([...state.spokes]),
  createSpoke: (data: Partial<Spoke>): Promise<Spoke> => {
    const spoke: Spoke = {
      id: `spk_${Date.now()}`,
      name: data.name || 'unnamed',
      base_url: data.base_url || '',
      type: data.type || 'ollama',
      status: 'offline',
      last_check_at: now(),
      models: [],
      gpu_info: null,
    }
    state.spokes.push(spoke)
    return delay(spoke)
  },
  patchSpoke: (id: string, data: Partial<Spoke>) => {
    const idx = state.spokes.findIndex(s => s.id === id)
    if (idx === -1) return Promise.reject(new Error('Spoke not found'))
    state.spokes[idx] = { ...state.spokes[idx], ...data }
    return delay(state.spokes[idx])
  },
  deleteSpoke: (id: string) => {
    state.spokes = state.spokes.filter(s => s.id !== id)
    return delay(null)
  },
  spokeHealthCheck: (id: string) => {
    const idx = state.spokes.findIndex(s => s.id === id)
    if (idx === -1) return Promise.reject(new Error('Spoke not found'))
    state.spokes[idx].last_check_at = now()
    return delay(state.spokes[idx], 600)
  },

  // models
  listModels: () => delay([...state.models]),
  refreshModels: () => delay({ discovered: state.models.length, updated_at: now() }, 800),

  // routes
  listRoutes: () => delay([...state.routes]),
  createRoute: (data: Partial<RouteRule>): Promise<RouteRule> => {
    const spoke = state.spokes.find(s => s.id === data.spoke_id)
    const route: RouteRule = {
      id: `rt_${Date.now()}`,
      model_glob: data.model_glob || '*',
      spoke_id: data.spoke_id || '',
      spoke_name: spoke?.name || '?',
      priority: data.priority ?? 100,
      enabled: data.enabled ?? true,
    }
    state.routes.push(route)
    return delay(route)
  },
  patchRoute: (id: string, data: Partial<RouteRule>) => {
    const idx = state.routes.findIndex(r => r.id === id)
    if (idx === -1) return Promise.reject(new Error('Route not found'))
    if (data.spoke_id) {
      const spoke = state.spokes.find(s => s.id === data.spoke_id)
      data.spoke_name = spoke?.name
    }
    state.routes[idx] = { ...state.routes[idx], ...data }
    return delay(state.routes[idx])
  },
  deleteRoute: (id: string) => {
    state.routes = state.routes.filter(r => r.id !== id)
    return delay(null)
  },

  // quotas
  getQuota: (appId: string): Promise<QuotaUsage> => {
    const app = state.apps.find(a => a.id === appId)
    if (!app) return Promise.reject(new Error('App not found'))
    return delay({
      app_id: appId,
      limits: app.quota,
      current: {
        rpm: Math.floor(Math.random() * app.quota.rpm * 0.9),
        concurrent: Math.floor(Math.random() * app.quota.concurrent * 0.7),
        daily_tokens: Math.floor(app.quota.daily_tokens * (0.1 + Math.random() * 0.6)),
      },
    })
  },
  patchQuota: (appId: string, data: Partial<{ rpm: number; concurrent: number; daily_tokens: number }>) => {
    const idx = state.apps.findIndex(a => a.id === appId)
    if (idx === -1) return Promise.reject(new Error('App not found'))
    state.apps[idx].quota = { ...state.apps[idx].quota, ...data }
    return delay({ app_id: appId, limits: state.apps[idx].quota, current: { rpm: 0, concurrent: 0, daily_tokens: 0 } })
  },

  // logs
  listLogs: (params: { app_id?: string; model?: string; status?: string; limit?: number } = {}) => {
    let filtered = [...state.logs]
    if (params.app_id) filtered = filtered.filter(l => l.app_id === params.app_id)
    if (params.model) filtered = filtered.filter(l => l.model === params.model)
    if (params.status) filtered = filtered.filter(l => l.status === params.status)
    if (params.limit) filtered = filtered.slice(0, params.limit)
    return delay(filtered)
  },

  // audit
  listAudit: (params: { actor?: string; action?: string; limit?: number } = {}) => {
    let filtered = [...state.audit]
    if (params.actor) filtered = filtered.filter(a => a.actor === params.actor)
    if (params.action) filtered = filtered.filter(a => a.action.includes(params.action!))
    if (params.limit) filtered = filtered.slice(0, params.limit)
    return delay(filtered)
  },

  // settings
  getSettings: () => delay({ ...state.settings }),
  patchSettings: (data: Partial<Settings>) => {
    state.settings = { ...state.settings, ...data }
    return delay(state.settings)
  },

  // pseudo-stream of new log events for SSE substitution
  nextStreamLog: (): LogEntry => makeLog(0),
}
