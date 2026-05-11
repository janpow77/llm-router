// Geteilte Domain-Typen — abgeleitet aus api-contract.md

export interface Quota {
  rpm: number
  concurrent: number
  daily_tokens: number
}

export interface App {
  id: string
  name: string
  description?: string
  api_key_preview: string
  api_key?: string  // only on create / rotate
  allowed_models: string[]
  quota: Quota
  enabled: boolean
  request_count_today: number
  created_at: string
  updated_at: string
}

export interface AppDetail extends App {
  recent_requests: LogEntry[]
}

export type SpokeStatus = 'online' | 'offline' | 'degraded' | 'unknown'

// Spoke-Typen — siehe Backend admin/models.py
//   - ollama:          direkter Ollama-Server
//   - openai:          OpenAI-kompatibler Server
//   - gpu-llm-manager: zentraler GPU-/LLM-Lifecycle-Manager (NUC/evo/Desktop)
//   - paddle-ocr:      OCR-Workload
//   - custom:          beliebiger HTTP-Workload
export type SpokeType =
  | 'ollama'
  | 'openai'
  | 'gpu-llm-manager'
  | 'paddle-ocr'
  | 'custom'

// Workload-Capabilities die ein Spoke anbieten kann
export type SpokeCapability =
  | 'llm'
  | 'embedding'
  | 'rerank'
  | 'ocr'
  | 'vision'
  | 'compute'
  | 'image-gen'

// Phase 3: Quelle eines Spokes
export type SpokeSource = 'manual' | 'dynamic'

export interface GpuInfo {
  device?: string | null
  vram_total_mb?: number | null
  vram_used_mb?: number | null
  util_pct?: number | null
}

export interface Spoke {
  id: string
  name: string
  base_url: string
  type: SpokeType
  capabilities: SpokeCapability[]
  tags: string[]
  priority: number
  gpu_info?: GpuInfo | null
  status: SpokeStatus
  last_check_at?: string | null
  last_error?: string | null
  enabled: boolean
  models: string[]
  created_at: string
  updated_at: string
  auth?: { header?: string; value?: string } | null
  // Phase 3: Dynamic-Spoke-Metadaten
  source?: SpokeSource
  last_seen_at?: string | null
  version?: string | null
  fallback_url?: string | null
}

export interface ModelInfo {
  id: string
  name: string
  spoke_id: string
  spoke_name: string
  size_gb: number
  context_length: number
  quantization: string
}

export interface RouteRule {
  id: string
  model_glob: string
  spoke_id: string
  spoke_name: string
  priority: number
  enabled: boolean
}

export interface QuotaUsage {
  app_id: string
  limits: Quota
  current: { rpm: number; concurrent: number; daily_tokens: number }
}

export type LogStatus = 'ok' | 'error' | 'rate_limited' | 'timeout'

export interface LogEntry {
  ts: string
  request_id: string
  app_id: string
  model: string
  spoke_id: string
  status: LogStatus
  duration_ms: number
  prompt_tokens: number
  completion_tokens: number
  error: string | null
}

export interface AuditEntry {
  id: string
  ts: string
  actor: string
  action: string
  target: string
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
}

export interface DashboardStats {
  requests_today: number
  tokens_today: number
  errors_today: number
  mean_latency_ms: number
  p95_latency_ms: number
  active_apps: number
  active_spokes: number
  top_apps: { app_id: string; name: string; count: number }[]
  top_models: { model: string; count: number }[]
}

export interface TimeseriesPoint {
  ts: string
  requests: number
  tokens: number
  errors: number
  mean_latency_ms: number
}

export interface HealthInfo {
  status: 'ok' | 'degraded' | 'down'
  version: string
  started_at: string
  spokes_health: { spoke_id: string; status: SpokeStatus; last_check_at: string }[]
}

export interface Settings {
  router_version: string
  uptime_seconds: number
  log_retention_days: number
  default_quotas: Quota
  data_dir: string
  config_path: string
}
