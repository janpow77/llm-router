<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed, nextTick, watch } from 'vue'
import { Pause, Play, Trash2, ArrowDown, RefreshCw } from 'lucide-vue-next'
import Card from '../../components/shared/Card.vue'
import Badge from '../../components/shared/Badge.vue'
import EmptyState from '../../components/shared/EmptyState.vue'
import { listLogs, streamLogs } from '../../api/logs'
import { listApps } from '../../api/apps'
import { useToastStore } from '../../stores/toast'
import type { LogEntry, App } from '../../api/types'
import { formatDuration, formatNumber, formatTime } from '../../utils/format'
import { extractError } from '../../api/client'

const logs = ref<LogEntry[]>([])
const apps = ref<App[]>([])
const filterApp = ref('')
const filterModel = ref('')
const filterStatus = ref('')
const paused = ref(false)
const autoScroll = ref(true)
const scrollEl = ref<HTMLElement | null>(null)
const toast = useToastStore()
let cleanup: (() => void) | null = null

const filtered = computed(() => {
  return logs.value.filter(l => {
    if (filterApp.value && l.app_id !== filterApp.value) return false
    if (filterModel.value && !l.model.includes(filterModel.value)) return false
    if (filterStatus.value && l.status !== filterStatus.value) return false
    return true
  })
})

async function load() {
  try {
    const [lg, ap] = await Promise.all([listLogs({ limit: 200 }), listApps()])
    logs.value = lg
    apps.value = ap
  } catch (err) { toast.error(extractError(err)) }
}

function startStream() {
  cleanup?.()
  cleanup = streamLogs((entry) => {
    if (paused.value) return
    logs.value.unshift(entry)
    if (logs.value.length > 500) logs.value = logs.value.slice(0, 500)
    if (autoScroll.value) {
      nextTick(() => {
        if (scrollEl.value) scrollEl.value.scrollTop = 0
      })
    }
  }, () => {
    toast.error('Log-Stream-Verbindung verloren.')
  })
}

onMounted(async () => {
  await load()
  startStream()
})

onBeforeUnmount(() => {
  cleanup?.()
})

watch(paused, (v) => {
  if (v) toast.info('Stream pausiert.')
})

function clear() {
  logs.value = []
  toast.info('Logs geleert.')
}

function statusVariant(s: string) {
  return s === 'ok' ? 'green' : s === 'error' ? 'red' : 'amber'
}
</script>

<template>
  <div class="space-y-4 animate-fade-in">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">Live-Logs</h1>
        <p class="text-sm text-slate-500 dark:text-slate-400">SSE-Stream aller Requests. Filter wirken sofort, neueste zuerst.</p>
      </div>
      <div class="flex items-center gap-2">
        <button class="rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 inline-flex items-center gap-1.5" @click="load">
          <RefreshCw :size="14" /> Reload
        </button>
        <button class="rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-sm font-medium inline-flex items-center gap-1.5" :class="paused ? 'text-green-600 dark:text-green-400' : 'text-amber-600 dark:text-amber-400'" @click="paused = !paused">
          <component :is="paused ? Play : Pause" :size="14" /> {{ paused ? 'Fortsetzen' : 'Pausieren' }}
        </button>
        <button class="rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-sm font-medium text-slate-600 hover:text-red-600 dark:text-slate-300 inline-flex items-center gap-1.5" @click="clear">
          <Trash2 :size="14" /> Leeren
        </button>
      </div>
    </div>

    <Card>
      <div class="flex flex-wrap items-end gap-3">
        <label class="block min-w-[180px]">
          <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">App</span>
          <select v-model="filterApp" class="w-full px-2.5 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm">
            <option value="">Alle</option>
            <option v-for="a in apps" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select>
        </label>
        <label class="block min-w-[180px]">
          <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Modell</span>
          <input v-model="filterModel" placeholder="z.B. qwen3" class="w-full px-2.5 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm font-mono" />
        </label>
        <label class="block min-w-[140px]">
          <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Status</span>
          <select v-model="filterStatus" class="w-full px-2.5 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm">
            <option value="">Alle</option>
            <option value="ok">ok</option>
            <option value="error">error</option>
            <option value="rate_limited">rate_limited</option>
            <option value="timeout">timeout</option>
          </select>
        </label>
        <label class="inline-flex items-center gap-1.5 ml-auto cursor-pointer">
          <input v-model="autoScroll" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-indigo-600" />
          <span class="text-xs text-slate-600 dark:text-slate-400 inline-flex items-center gap-1"><ArrowDown :size="12" /> Auto-Scroll</span>
        </label>
      </div>
    </Card>

    <Card padded>
      <div ref="scrollEl" class="overflow-y-auto max-h-[60vh]">
        <table class="w-full text-xs">
          <thead class="sticky top-0 bg-white dark:bg-slate-950 z-10">
            <tr class="border-b border-slate-200 dark:border-slate-800 text-left">
              <th class="px-2 py-1.5 font-semibold uppercase tracking-wider text-slate-500">Zeit</th>
              <th class="px-2 py-1.5 font-semibold uppercase tracking-wider text-slate-500">Status</th>
              <th class="px-2 py-1.5 font-semibold uppercase tracking-wider text-slate-500">App</th>
              <th class="px-2 py-1.5 font-semibold uppercase tracking-wider text-slate-500">Modell</th>
              <th class="px-2 py-1.5 font-semibold uppercase tracking-wider text-slate-500 text-right">Dauer</th>
              <th class="px-2 py-1.5 font-semibold uppercase tracking-wider text-slate-500 text-right">Tokens (in/out)</th>
              <th class="px-2 py-1.5 font-semibold uppercase tracking-wider text-slate-500">Fehler</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="l in filtered" :key="l.request_id" class="border-b border-slate-100 dark:border-slate-800/60 hover:bg-slate-50 dark:hover:bg-slate-900/40 animate-fade-in">
              <td class="px-2 py-1.5 tabular-nums text-slate-500">{{ formatTime(l.ts) }}</td>
              <td class="px-2 py-1.5"><Badge :variant="statusVariant(l.status)" dot>{{ l.status }}</Badge></td>
              <td class="px-2 py-1.5">{{ l.app_id.replace('app_', '') }}</td>
              <td class="px-2 py-1.5 font-mono">{{ l.model }}</td>
              <td class="px-2 py-1.5 tabular-nums text-right">{{ formatDuration(l.duration_ms) }}</td>
              <td class="px-2 py-1.5 tabular-nums text-right">{{ formatNumber(l.prompt_tokens) }} / {{ formatNumber(l.completion_tokens) }}</td>
              <td class="px-2 py-1.5 text-red-600 dark:text-red-400 truncate max-w-xs" :title="l.error || ''">{{ l.error || '—' }}</td>
            </tr>
            <tr v-if="!filtered.length">
              <td colspan="7">
                <EmptyState title="Keine Logs" message="Warte auf eingehende Requests oder passe die Filter an." />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>
  </div>
</template>
