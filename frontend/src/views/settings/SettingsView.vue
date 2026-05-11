<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Save, Server, Folder, Clock, Tag } from 'lucide-vue-next'
import Card from '../../components/shared/Card.vue'
import { getSettings, patchSettings } from '../../api/settings'
import { useToastStore } from '../../stores/toast'
import type { Settings } from '../../api/types'
import { formatUptime } from '../../utils/format'
import { extractError } from '../../api/client'

const settings = ref<Settings | null>(null)
const form = ref({ log_retention_days: 30, default_rpm: 60, default_concurrent: 4, default_daily_tokens: 1_000_000 })
const dirty = ref(false)
const saving = ref(false)
const toast = useToastStore()

async function load() {
  try {
    settings.value = await getSettings()
    form.value.log_retention_days = settings.value.log_retention_days
    form.value.default_rpm = settings.value.default_quotas.rpm
    form.value.default_concurrent = settings.value.default_quotas.concurrent
    form.value.default_daily_tokens = settings.value.default_quotas.daily_tokens
    dirty.value = false
  } catch (err) { toast.error(extractError(err)) }
}
onMounted(load)

function markDirty() { dirty.value = true }

async function save() {
  saving.value = true
  try {
    await patchSettings({
      log_retention_days: form.value.log_retention_days,
      default_quotas: {
        rpm: form.value.default_rpm,
        concurrent: form.value.default_concurrent,
        daily_tokens: form.value.default_daily_tokens,
      },
    })
    toast.success('Einstellungen gespeichert.')
    await load()
  } catch (err) { toast.error(extractError(err)) }
  finally { saving.value = false }
}
</script>

<template>
  <div class="space-y-4 animate-fade-in">
    <div>
      <h1 class="text-2xl font-bold tracking-tight">System-Einstellungen</h1>
      <p class="text-sm text-slate-500 dark:text-slate-400">Globale Defaults für Router-Verhalten und neue Apps.</p>
    </div>

    <div v-if="settings" class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <Card title="Router-Info" subtitle="Read-only">
        <dl class="text-sm space-y-3">
          <div class="flex items-start gap-2">
            <Tag :size="14" class="text-indigo-500 mt-0.5" />
            <div>
              <dt class="text-xs text-slate-500">Version</dt>
              <dd class="font-mono">{{ settings.router_version }}</dd>
            </div>
          </div>
          <div class="flex items-start gap-2">
            <Clock :size="14" class="text-indigo-500 mt-0.5" />
            <div>
              <dt class="text-xs text-slate-500">Uptime</dt>
              <dd class="tabular-nums">{{ formatUptime(settings.uptime_seconds) }}</dd>
            </div>
          </div>
          <div class="flex items-start gap-2">
            <Folder :size="14" class="text-indigo-500 mt-0.5" />
            <div>
              <dt class="text-xs text-slate-500">Daten-Verzeichnis</dt>
              <dd class="font-mono text-xs">{{ settings.data_dir }}</dd>
            </div>
          </div>
          <div class="flex items-start gap-2">
            <Server :size="14" class="text-indigo-500 mt-0.5" />
            <div>
              <dt class="text-xs text-slate-500">Config-Pfad</dt>
              <dd class="font-mono text-xs">{{ settings.config_path }}</dd>
            </div>
          </div>
        </dl>
      </Card>

      <Card title="Default-Quotas" subtitle="Werden bei neuen Apps vorbelegt." class="lg:col-span-2">
        <div class="space-y-4">
          <div class="grid grid-cols-3 gap-3">
            <label class="block">
              <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Requests / min</span>
              <input v-model.number="form.default_rpm" type="number" min="0" class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm tabular-nums" @input="markDirty" />
            </label>
            <label class="block">
              <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Concurrent</span>
              <input v-model.number="form.default_concurrent" type="number" min="0" class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm tabular-nums" @input="markDirty" />
            </label>
            <label class="block">
              <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Tokens / Tag</span>
              <input v-model.number="form.default_daily_tokens" type="number" min="0" step="100000" class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm tabular-nums" @input="markDirty" />
            </label>
          </div>

          <hr class="border-slate-200 dark:border-slate-800" />

          <label class="block max-w-xs">
            <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Log-Retention (Tage)</span>
            <input v-model.number="form.log_retention_days" type="number" min="1" max="365" class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm tabular-nums" @input="markDirty" />
            <p class="text-xs text-slate-500 mt-1">Logs älter als diese Anzahl Tage werden automatisch gelöscht.</p>
          </label>

          <div class="flex justify-end pt-2">
            <button class="rounded-md bg-indigo-600 hover:bg-indigo-700 px-4 py-2 text-sm font-semibold text-white inline-flex items-center gap-2 disabled:opacity-50" :disabled="!dirty || saving" @click="save">
              <Save :size="14" />
              {{ saving ? 'Speichere...' : 'Speichern' }}
            </button>
          </div>
        </div>
      </Card>
    </div>
  </div>
</template>
