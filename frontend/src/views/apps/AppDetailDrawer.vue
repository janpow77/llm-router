<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import Modal from '../../components/shared/Modal.vue'
import Badge from '../../components/shared/Badge.vue'
import { getApp } from '../../api/apps'
import type { AppDetail } from '../../api/types'
import { formatDateTime, formatDuration, formatNumber, formatTime } from '../../utils/format'

const props = defineProps<{ open: boolean; appId: string | null }>()
const emit = defineEmits<{ close: [] }>()

const detail = ref<AppDetail | null>(null)
const loading = ref(false)

async function load() {
  if (!props.appId) return
  loading.value = true
  try {
    detail.value = await getApp(props.appId)
  } finally { loading.value = false }
}

watch(() => [props.open, props.appId], () => { if (props.open) load() })
onMounted(() => { if (props.open) load() })

function statusVariant(s: string) {
  return s === 'ok' ? 'green' : s === 'error' ? 'red' : 'amber'
}
</script>

<template>
  <Modal :open="open" title="App-Details" width="48rem" @close="emit('close')">
    <div v-if="loading" class="text-sm text-slate-500">Lade...</div>
    <div v-else-if="detail" class="space-y-5">
      <div class="grid grid-cols-2 gap-3 text-sm">
        <div>
          <p class="text-xs text-slate-500">Name</p>
          <p class="font-semibold">{{ detail.name }}</p>
        </div>
        <div>
          <p class="text-xs text-slate-500">Status</p>
          <Badge :variant="detail.enabled ? 'green' : 'slate'" dot>{{ detail.enabled ? 'Aktiv' : 'Deaktiviert' }}</Badge>
        </div>
        <div>
          <p class="text-xs text-slate-500">Beschreibung</p>
          <p>{{ detail.description || '—' }}</p>
        </div>
        <div>
          <p class="text-xs text-slate-500">API-Key</p>
          <p class="font-mono text-xs">{{ detail.api_key_preview }}</p>
        </div>
        <div>
          <p class="text-xs text-slate-500">Erstellt</p>
          <p class="text-xs">{{ formatDateTime(detail.created_at) }}</p>
        </div>
        <div>
          <p class="text-xs text-slate-500">Zuletzt aktualisiert</p>
          <p class="text-xs">{{ formatDateTime(detail.updated_at) }}</p>
        </div>
      </div>

      <div>
        <p class="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-2">Quotas</p>
        <div class="grid grid-cols-3 gap-3 text-sm">
          <div class="rounded-md border border-slate-200 dark:border-slate-800 p-3">
            <p class="text-xs text-slate-500">RPM</p>
            <p class="text-lg font-bold tabular-nums">{{ formatNumber(detail.quota.rpm) }}</p>
          </div>
          <div class="rounded-md border border-slate-200 dark:border-slate-800 p-3">
            <p class="text-xs text-slate-500">Concurrent</p>
            <p class="text-lg font-bold tabular-nums">{{ formatNumber(detail.quota.concurrent) }}</p>
          </div>
          <div class="rounded-md border border-slate-200 dark:border-slate-800 p-3">
            <p class="text-xs text-slate-500">Tokens / Tag</p>
            <p class="text-lg font-bold tabular-nums">{{ formatNumber(detail.quota.daily_tokens) }}</p>
          </div>
        </div>
      </div>

      <div>
        <p class="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-2">Erlaubte Modelle</p>
        <div class="flex flex-wrap gap-1.5">
          <Badge v-for="m in detail.allowed_models" :key="m" variant="indigo">{{ m }}</Badge>
        </div>
      </div>

      <div>
        <p class="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-2">Letzte 50 Requests</p>
        <div class="rounded-md border border-slate-200 dark:border-slate-800 max-h-72 overflow-y-auto">
          <table class="w-full text-xs">
            <thead class="bg-slate-50 dark:bg-slate-900 sticky top-0">
              <tr class="text-left">
                <th class="px-2 py-1.5">Zeit</th>
                <th class="px-2 py-1.5">Modell</th>
                <th class="px-2 py-1.5">Status</th>
                <th class="px-2 py-1.5 text-right">Dauer</th>
                <th class="px-2 py-1.5 text-right">Tokens</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in detail.recent_requests" :key="r.request_id" class="border-t border-slate-100 dark:border-slate-800/60">
                <td class="px-2 py-1.5 tabular-nums">{{ formatTime(r.ts) }}</td>
                <td class="px-2 py-1.5 font-mono">{{ r.model }}</td>
                <td class="px-2 py-1.5"><Badge :variant="statusVariant(r.status)" dot>{{ r.status }}</Badge></td>
                <td class="px-2 py-1.5 text-right tabular-nums">{{ formatDuration(r.duration_ms) }}</td>
                <td class="px-2 py-1.5 text-right tabular-nums">{{ formatNumber(r.prompt_tokens + r.completion_tokens) }}</td>
              </tr>
              <tr v-if="!detail.recent_requests.length"><td colspan="5" class="px-2 py-3 text-center text-slate-500">Keine Anfragen.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    <template #footer>
      <button class="rounded-md px-3 py-1.5 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800" @click="emit('close')">Schließen</button>
    </template>
  </Modal>
</template>
