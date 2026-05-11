<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { RefreshCw, ChevronRight } from 'lucide-vue-next'
import Card from '../../components/shared/Card.vue'
import Badge from '../../components/shared/Badge.vue'
import EmptyState from '../../components/shared/EmptyState.vue'
import { listAudit } from '../../api/audit'
import { useToastStore } from '../../stores/toast'
import type { AuditEntry } from '../../api/types'
import { formatDateTime } from '../../utils/format'
import { extractError } from '../../api/client'

const entries = ref<AuditEntry[]>([])
const filterActor = ref('')
const filterAction = ref('')
const expanded = ref(new Set<string>())
const toast = useToastStore()

async function load() {
  try { entries.value = await listAudit({ limit: 200 }) }
  catch (err) { toast.error(extractError(err)) }
}
onMounted(load)

const filtered = computed(() => entries.value.filter(e => {
  if (filterActor.value && !e.actor.toLowerCase().includes(filterActor.value.toLowerCase())) return false
  if (filterAction.value && !e.action.includes(filterAction.value)) return false
  return true
}))

function actionVariant(a: string): 'green' | 'red' | 'amber' | 'blue' | 'indigo' {
  if (a.includes('delete')) return 'red'
  if (a.includes('create')) return 'green'
  if (a.includes('rotate')) return 'amber'
  if (a.includes('update') || a.includes('patch')) return 'blue'
  return 'indigo'
}

function toggle(id: string) {
  if (expanded.value.has(id)) expanded.value.delete(id)
  else expanded.value.add(id)
}

function diffJson(obj: Record<string, unknown> | null): string {
  if (!obj) return '∅'
  return JSON.stringify(obj, null, 2)
}
</script>

<template>
  <div class="space-y-4 animate-fade-in">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">Audit-Log</h1>
        <p class="text-sm text-slate-500 dark:text-slate-400">Protokollierte Konfigurations-Änderungen mit Diff (vorher / nachher).</p>
      </div>
      <button class="rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 inline-flex items-center gap-1.5" @click="load">
        <RefreshCw :size="14" /> Reload
      </button>
    </div>

    <Card>
      <div class="flex flex-wrap items-end gap-3">
        <label class="block min-w-[180px]">
          <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Akteur</span>
          <input v-model="filterActor" placeholder="z.B. admin" class="w-full px-2.5 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm" />
        </label>
        <label class="block min-w-[180px]">
          <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Aktion (Substring)</span>
          <input v-model="filterAction" placeholder="z.B. app." class="w-full px-2.5 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm font-mono" />
        </label>
      </div>
    </Card>

    <Card padded>
      <EmptyState v-if="!filtered.length" title="Keine Audit-Einträge" />
      <div v-else class="space-y-2">
        <div
          v-for="e in filtered"
          :key="e.id"
          class="rounded-md border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 transition-colors"
        >
          <button class="w-full flex items-center gap-3 px-3 py-2.5 text-left" @click="toggle(e.id)">
            <ChevronRight :size="14" class="text-slate-400 transition-transform" :class="expanded.has(e.id) ? 'rotate-90' : ''" />
            <span class="text-xs tabular-nums text-slate-500 w-44">{{ formatDateTime(e.ts) }}</span>
            <Badge :variant="actionVariant(e.action)">{{ e.action }}</Badge>
            <span class="text-sm text-slate-700 dark:text-slate-300">von <strong>{{ e.actor }}</strong></span>
            <span class="text-xs text-slate-500 font-mono ml-auto">{{ e.target }}</span>
          </button>
          <div v-if="expanded.has(e.id)" class="grid grid-cols-2 gap-3 px-3 pb-3 border-t border-slate-200 dark:border-slate-800 pt-3">
            <div>
              <p class="text-xs font-semibold uppercase tracking-wider text-red-600 dark:text-red-400 mb-1">Vorher</p>
              <pre class="text-xs bg-red-50 dark:bg-red-900/20 rounded p-2 overflow-x-auto font-mono text-red-900 dark:text-red-200">{{ diffJson(e.before) }}</pre>
            </div>
            <div>
              <p class="text-xs font-semibold uppercase tracking-wider text-green-600 dark:text-green-400 mb-1">Nachher</p>
              <pre class="text-xs bg-green-50 dark:bg-green-900/20 rounded p-2 overflow-x-auto font-mono text-green-900 dark:text-green-200">{{ diffJson(e.after) }}</pre>
            </div>
          </div>
        </div>
      </div>
    </Card>
  </div>
</template>
