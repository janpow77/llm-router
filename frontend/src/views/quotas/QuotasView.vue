<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RefreshCw, Save } from 'lucide-vue-next'
import Card from '../../components/shared/Card.vue'
import ProgressBar from '../../components/shared/ProgressBar.vue'
import EmptyState from '../../components/shared/EmptyState.vue'
import { listApps } from '../../api/apps'
import { getQuota, patchQuota } from '../../api/quotas'
import { useToastStore } from '../../stores/toast'
import type { App, QuotaUsage } from '../../api/types'
import { formatNumber } from '../../utils/format'
import { extractError } from '../../api/client'

interface Row {
  app: App
  quota: QuotaUsage | null
  edit: { rpm: number; concurrent: number; daily_tokens: number }
  dirty: boolean
  saving: boolean
}

const rows = ref<Row[]>([])
const toast = useToastStore()
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const apps = await listApps()
    const quotas = await Promise.all(apps.map(a => getQuota(a.id).catch(() => null)))
    rows.value = apps.map((a, i) => ({
      app: a,
      quota: quotas[i],
      edit: {
        rpm: quotas[i]?.limits.rpm ?? a.quota.rpm,
        concurrent: quotas[i]?.limits.concurrent ?? a.quota.concurrent,
        daily_tokens: quotas[i]?.limits.daily_tokens ?? a.quota.daily_tokens,
      },
      dirty: false,
      saving: false,
    }))
  } catch (err) { toast.error(extractError(err)) }
  finally { loading.value = false }
}
onMounted(load)

function markDirty(row: Row) {
  if (!row.quota) return
  row.dirty =
    row.edit.rpm !== row.quota.limits.rpm ||
    row.edit.concurrent !== row.quota.limits.concurrent ||
    row.edit.daily_tokens !== row.quota.limits.daily_tokens
}

async function saveRow(row: Row) {
  row.saving = true
  try {
    await patchQuota(row.app.id, row.edit)
    toast.success(`${row.app.name} aktualisiert.`)
    row.dirty = false
    await load()
  } catch (err) { toast.error(extractError(err)) }
  finally { row.saving = false }
}
</script>

<template>
  <div class="space-y-4 animate-fade-in">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">Quotas</h1>
        <p class="text-sm text-slate-500 dark:text-slate-400">Live-Auslastung pro App. Inline-Edit der Limits.</p>
      </div>
      <button class="rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 inline-flex items-center gap-1.5" @click="load">
        <RefreshCw :size="14" /> Neu laden
      </button>
    </div>

    <Card padded>
      <EmptyState v-if="!rows.length && !loading" title="Keine Apps vorhanden" />
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-slate-200 dark:border-slate-800 text-left">
              <th class="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400">App</th>
              <th class="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 w-64">Requests / min</th>
              <th class="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 w-64">Concurrent</th>
              <th class="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 w-72">Tokens / Tag</th>
              <th class="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 text-right">Aktion</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.app.id" class="border-b border-slate-100 dark:border-slate-800/60">
              <td class="px-3 py-3">
                <p class="font-semibold text-slate-900 dark:text-slate-100">{{ row.app.name }}</p>
                <p v-if="row.app.description" class="text-xs text-slate-500">{{ row.app.description }}</p>
              </td>
              <td class="px-3 py-3">
                <input v-model.number="row.edit.rpm" type="number" min="0" class="w-20 px-2 py-1 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm tabular-nums" @input="markDirty(row)" />
                <div class="mt-2">
                  <ProgressBar :value="row.quota?.current.rpm ?? 0" :max="row.edit.rpm" />
                  <p class="text-[10px] text-slate-500 mt-0.5 tabular-nums">{{ formatNumber(row.quota?.current.rpm ?? 0) }} / {{ formatNumber(row.edit.rpm) }}</p>
                </div>
              </td>
              <td class="px-3 py-3">
                <input v-model.number="row.edit.concurrent" type="number" min="0" class="w-20 px-2 py-1 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm tabular-nums" @input="markDirty(row)" />
                <div class="mt-2">
                  <ProgressBar :value="row.quota?.current.concurrent ?? 0" :max="row.edit.concurrent" />
                  <p class="text-[10px] text-slate-500 mt-0.5 tabular-nums">{{ formatNumber(row.quota?.current.concurrent ?? 0) }} / {{ formatNumber(row.edit.concurrent) }}</p>
                </div>
              </td>
              <td class="px-3 py-3">
                <input v-model.number="row.edit.daily_tokens" type="number" min="0" step="100000" class="w-32 px-2 py-1 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm tabular-nums" @input="markDirty(row)" />
                <div class="mt-2">
                  <ProgressBar :value="row.quota?.current.daily_tokens ?? 0" :max="row.edit.daily_tokens" />
                  <p class="text-[10px] text-slate-500 mt-0.5 tabular-nums">{{ formatNumber(row.quota?.current.daily_tokens ?? 0) }} / {{ formatNumber(row.edit.daily_tokens) }}</p>
                </div>
              </td>
              <td class="px-3 py-3 text-right">
                <button v-if="row.dirty" class="rounded-md bg-indigo-600 hover:bg-indigo-700 px-2.5 py-1 text-xs font-semibold text-white inline-flex items-center gap-1 disabled:opacity-50" :disabled="row.saving" @click="saveRow(row)">
                  <Save :size="12" /> {{ row.saving ? '...' : 'Speichern' }}
                </button>
                <span v-else class="text-xs text-slate-400">unverändert</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>
  </div>
</template>
