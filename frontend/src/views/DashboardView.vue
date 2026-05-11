<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { Activity, Zap, Server, AppWindow, AlertTriangle } from 'lucide-vue-next'
import Card from '../components/shared/Card.vue'
import Sparkline from '../components/shared/Sparkline.vue'
import Badge from '../components/shared/Badge.vue'
import Spinner from '../components/shared/Spinner.vue'
import { getDashboard, getTimeseries } from '../api/dashboard'
import { listLogs } from '../api/logs'
import { formatNumber, formatDuration, formatTime, relativeTime } from '../utils/format'
import { sparklinePath } from '../utils/chart'
import type { DashboardStats, TimeseriesPoint, LogEntry } from '../api/types'

const stats = ref<DashboardStats | null>(null)
const series = ref<TimeseriesPoint[]>([])
const recentLogs = ref<LogEntry[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    const [s, t, l] = await Promise.all([
      getDashboard(),
      getTimeseries('1h', 24),
      listLogs({ limit: 10 }),
    ])
    stats.value = s
    series.value = t
    recentLogs.value = l
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

onMounted(load)

const requestSeries = computed(() => series.value.map(p => p.requests))
const errorSeries = computed(() => series.value.map(p => p.errors))

const heroStats = computed(() => stats.value ? [
  { label: 'Requests heute', value: formatNumber(stats.value.requests_today), icon: Activity, accent: 'indigo' },
  { label: 'Aktive Apps', value: stats.value.active_apps, icon: AppWindow, accent: 'green' },
  { label: 'Aktive Spokes', value: stats.value.active_spokes, icon: Server, accent: 'blue' },
  { label: 'Mean Latency', value: formatDuration(stats.value.mean_latency_ms), icon: Zap, accent: 'amber' },
] : [])

// Chart geometry for the timeseries SVG
const chartW = 800
const chartH = 220
const chartPad = { l: 36, r: 16, t: 16, b: 28 }

const chartGeom = computed(() => {
  const max = Math.max(...requestSeries.value, 1)
  const path = sparklinePath(
    requestSeries.value,
    chartW - chartPad.l - chartPad.r,
    chartH - chartPad.t - chartPad.b
  )
  // Translate path coordinates to add padding
  return { path, max }
})

const errorChartPath = computed(() => sparklinePath(
  errorSeries.value,
  chartW - chartPad.l - chartPad.r,
  chartH - chartPad.t - chartPad.b
))

const yLabels = computed(() => {
  const max = chartGeom.value.max
  return [max, Math.round(max * 0.66), Math.round(max * 0.33), 0]
})

const xLabels = computed(() => {
  if (!series.value.length) return []
  const total = series.value.length
  return [0, Math.floor(total / 3), Math.floor(2 * total / 3), total - 1].map(i => series.value[i])
})

const accentColor: Record<string, string> = {
  indigo: 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-400',
  green: 'bg-green-500/10 text-green-600 dark:text-green-400',
  blue: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
  amber: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
}

function statusVariant(s: string) {
  return s === 'ok' ? 'green' : s === 'error' ? 'red' : 'amber'
}
</script>

<template>
  <div class="space-y-6 animate-fade-in">
    <div v-if="loading && !stats" class="flex items-center gap-2 text-slate-500"><Spinner /> Lade Dashboard...</div>
    <div v-else-if="error" class="rounded-md border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/30 p-4 text-red-800 dark:text-red-200 text-sm">
      <p class="font-semibold flex items-center gap-2"><AlertTriangle :size="16" /> Fehler beim Laden</p>
      <p class="mt-1">{{ error }}</p>
      <button class="mt-2 text-xs underline" @click="load">Erneut versuchen</button>
    </div>

    <template v-if="stats">
      <!-- Hero stats -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card v-for="s in heroStats" :key="s.label" :padded="true">
          <div class="flex items-start justify-between">
            <div>
              <p class="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">{{ s.label }}</p>
              <p class="mt-2 text-2xl font-bold tabular-nums text-slate-900 dark:text-slate-100">{{ s.value }}</p>
            </div>
            <div class="grid place-items-center h-9 w-9 rounded-lg" :class="accentColor[s.accent]">
              <component :is="s.icon" :size="16" />
            </div>
          </div>
        </Card>
      </div>

      <!-- Time series -->
      <Card title="Aktivität (letzte 24 Stunden)" subtitle="Requests pro Stunde, Fehler-Overlay rot">
        <template #actions>
          <Badge variant="indigo" dot>Requests</Badge>
          <Badge variant="red" dot>Fehler</Badge>
        </template>
        <div class="overflow-x-auto">
          <svg :width="chartW" :height="chartH" :viewBox="`0 0 ${chartW} ${chartH}`" class="w-full h-auto">
            <!-- Grid lines + Y labels -->
            <g v-for="(y, i) in yLabels" :key="`y-${i}`">
              <line
                :x1="chartPad.l"
                :x2="chartW - chartPad.r"
                :y1="chartPad.t + (chartH - chartPad.t - chartPad.b) * (i / (yLabels.length - 1))"
                :y2="chartPad.t + (chartH - chartPad.t - chartPad.b) * (i / (yLabels.length - 1))"
                class="stroke-slate-200 dark:stroke-slate-800"
                stroke-width="1"
              />
              <text
                :x="chartPad.l - 6"
                :y="chartPad.t + (chartH - chartPad.t - chartPad.b) * (i / (yLabels.length - 1)) + 4"
                text-anchor="end"
                class="fill-slate-400 text-[10px] tabular-nums"
              >{{ y }}</text>
            </g>
            <!-- Requests line -->
            <g :transform="`translate(${chartPad.l}, ${chartPad.t})`">
              <path
                :d="chartGeom.path"
                fill="none"
                class="stroke-indigo-500"
                stroke-width="2"
                stroke-linejoin="round"
                stroke-linecap="round"
              />
              <path
                :d="`${chartGeom.path} L${chartW - chartPad.l - chartPad.r},${chartH - chartPad.t - chartPad.b} L0,${chartH - chartPad.t - chartPad.b} Z`"
                class="fill-indigo-500/15"
                stroke="none"
              />
              <path
                :d="errorChartPath"
                fill="none"
                class="stroke-red-500"
                stroke-width="1.5"
                stroke-dasharray="3 2"
              />
            </g>
            <!-- X labels -->
            <g>
              <text
                v-for="(p, idx) in xLabels"
                :key="`x-${idx}`"
                :x="chartPad.l + ((chartW - chartPad.l - chartPad.r) / (series.length - 1)) * series.indexOf(p)"
                :y="chartH - 8"
                text-anchor="middle"
                class="fill-slate-400 text-[10px]"
              >{{ formatTime(p.ts) }}</text>
            </g>
          </svg>
        </div>
      </Card>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- Top Apps -->
        <Card title="Top Apps" subtitle="Nach Requests heute" class="lg:col-span-1">
          <div class="space-y-3">
            <div v-for="(app, i) in stats.top_apps" :key="app.app_id" class="space-y-1.5">
              <div class="flex items-center justify-between text-sm">
                <span class="font-medium text-slate-900 dark:text-slate-100">{{ app.name }}</span>
                <span class="tabular-nums text-slate-600 dark:text-slate-400">{{ formatNumber(app.count) }}</span>
              </div>
              <div class="h-1.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                <div class="h-full bg-indigo-500" :style="{ width: ((app.count / stats.top_apps[0].count) * 100) + '%' }" />
              </div>
              <p v-if="i === 0" class="text-[10px] text-slate-400">Spitzenreiter</p>
            </div>
          </div>
        </Card>

        <!-- Top Models -->
        <Card title="Top Modelle" subtitle="Nach Requests heute">
          <div class="space-y-3">
            <div v-for="m in stats.top_models" :key="m.model" class="space-y-1.5">
              <div class="flex items-center justify-between text-sm">
                <span class="font-mono text-xs text-slate-900 dark:text-slate-100">{{ m.model }}</span>
                <span class="tabular-nums text-slate-600 dark:text-slate-400">{{ formatNumber(m.count) }}</span>
              </div>
              <div class="h-1.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                <div class="h-full bg-blue-500" :style="{ width: ((m.count / stats.top_models[0].count) * 100) + '%' }" />
              </div>
            </div>
          </div>
        </Card>

        <!-- Live Activity -->
        <Card title="Live-Activity" subtitle="Letzte 10 Requests">
          <div class="space-y-2 max-h-72 overflow-y-auto">
            <div
              v-for="log in recentLogs"
              :key="log.request_id"
              class="flex items-center justify-between gap-2 py-1.5 border-b border-slate-100 dark:border-slate-800/60 last:border-0"
            >
              <div class="flex items-center gap-2 min-w-0">
                <Badge :variant="statusVariant(log.status)" dot>{{ log.status }}</Badge>
                <span class="font-mono text-xs text-slate-700 dark:text-slate-300 truncate">{{ log.model }}</span>
              </div>
              <div class="text-right">
                <p class="text-xs tabular-nums text-slate-500">{{ formatDuration(log.duration_ms) }}</p>
                <p class="text-[10px] text-slate-400">{{ relativeTime(log.ts) }}</p>
              </div>
            </div>
          </div>
        </Card>
      </div>

      <!-- Mini sparklines row -->
      <Card title="Trend-Indikatoren" subtitle="Sparklines pro Metrik der letzten 24h">
        <div class="grid grid-cols-2 md:grid-cols-4 gap-6">
          <div>
            <p class="text-xs uppercase tracking-wider text-slate-500 mb-1">Requests</p>
            <Sparkline :values="requestSeries" :width="160" :height="40" color="rgb(99 102 241)" :fill="true" />
          </div>
          <div>
            <p class="text-xs uppercase tracking-wider text-slate-500 mb-1">Tokens</p>
            <Sparkline :values="series.map(p => p.tokens)" :width="160" :height="40" color="rgb(59 130 246)" :fill="true" />
          </div>
          <div>
            <p class="text-xs uppercase tracking-wider text-slate-500 mb-1">Latency</p>
            <Sparkline :values="series.map(p => p.mean_latency_ms)" :width="160" :height="40" color="rgb(245 158 11)" :fill="true" />
          </div>
          <div>
            <p class="text-xs uppercase tracking-wider text-slate-500 mb-1">Fehler</p>
            <Sparkline :values="errorSeries" :width="160" :height="40" color="rgb(239 68 68)" :fill="true" />
          </div>
        </div>
      </Card>
    </template>
  </div>
</template>
