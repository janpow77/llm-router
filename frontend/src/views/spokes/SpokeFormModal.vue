<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Loader2, CheckCircle2, XCircle, ExternalLink, Sparkles } from 'lucide-vue-next'
import Modal from '../../components/shared/Modal.vue'
import type { Spoke, SpokeCapability, SpokeType } from '../../api/types'
import {
  PROVIDER_PRESETS,
  applyAuthPrefix,
  getProviderPreset,
  stripAuthPrefix,
} from '../../data/providers'
import type { ProviderPreset } from '../../data/providers'
import { testSpokeConnection } from '../../api/spokes'
import { extractError } from '../../api/client'
import { useToastStore } from '../../stores/toast'

const props = defineProps<{ open: boolean; spoke: Spoke | null; saving: boolean }>()
const emit = defineEmits<{ close: []; save: [data: Partial<Spoke>] }>()

const toast = useToastStore()

const TYPE_OPTIONS: { value: SpokeType; label: string; hint: string }[] = [
  { value: 'gpu-llm-manager', label: 'GPU-LLM-Manager', hint: 'Lifecycle-Manager auf NUC/evo/Desktop' },
  { value: 'ollama', label: 'Ollama (direkt)', hint: 'Direkter Ollama-Endpoint, kein Lease-Tracking' },
  { value: 'openai', label: 'OpenAI-kompatibel', hint: 'vLLM, llama.cpp, eigener Server' },
  { value: 'paddle-ocr', label: 'Paddle-OCR', hint: 'OCR-Workload' },
  { value: 'custom', label: 'Custom HTTP', hint: 'Beliebiger Workload' },
]

const ALL_CAPABILITIES: SpokeCapability[] = ['llm', 'embedding', 'rerank', 'ocr', 'vision', 'compute', 'image-gen']

// Provider-Picker: 'custom' = kein Preset (Default beim Neuanlegen).
const selectedPresetId = ref<string>('custom')
const selectedPreset = computed<ProviderPreset>(() => getProviderPreset(selectedPresetId.value))

const form = ref({
  name: '',
  base_url: '',
  type: 'gpu-llm-manager' as SpokeType,
  capabilities: ['llm'] as SpokeCapability[],
  tags: '' as string, // comma-separated im UI
  priority: 100,
  auth_header: 'Authorization',
  /** Klartext-Token wie vom User eingegeben — Praefix wird erst beim Save angewendet. */
  auth_value: '',
  enabled: true,
  fallback_url: '' as string,
  test_endpoint: '' as string,
})

const testState = ref<{
  running: boolean
  result: null | { ok: boolean; message: string }
}>({ running: false, result: null })

watch(() => [props.open, props.spoke], () => {
  if (!props.open) return
  testState.value = { running: false, result: null }
  if (props.spoke) {
    // Beim Edit: versuche zu erkennen ob ein Preset matched, sonst Custom.
    selectedPresetId.value = detectPresetForSpoke(props.spoke)
    const preset = getProviderPreset(selectedPresetId.value)
    form.value = {
      name: props.spoke.name,
      base_url: props.spoke.base_url,
      type: props.spoke.type,
      capabilities: [...(props.spoke.capabilities || ['llm'])],
      tags: (props.spoke.tags || []).join(', '),
      priority: props.spoke.priority ?? 100,
      auth_header: props.spoke.auth?.header || preset.auth_header || 'Authorization',
      // Praefix vom gespeicherten Wert abziehen, damit User den blanken
      // Token sieht.
      auth_value: stripAuthPrefix(props.spoke.auth?.value, preset.auth_value_prefix),
      enabled: props.spoke.enabled,
      fallback_url: props.spoke.fallback_url || '',
      test_endpoint: preset.test_endpoint || '',
    }
  } else {
    selectedPresetId.value = 'custom'
    form.value = {
      name: '',
      base_url: '',
      type: 'gpu-llm-manager',
      capabilities: ['llm'],
      tags: '',
      priority: 100,
      auth_header: 'Authorization',
      auth_value: '',
      enabled: true,
      fallback_url: '',
      test_endpoint: '',
    }
  }
}, { immediate: true })

/**
 * Bestmoegliche Match-Erkennung: gleiche base_url-Praefix ODER gleicher
 * auth_header (case-insensitive). Wenn nichts matched → 'custom'.
 */
function detectPresetForSpoke(spoke: Spoke): string {
  const url = (spoke.base_url || '').toLowerCase()
  const header = (spoke.auth?.header || '').toLowerCase()
  for (const p of PROVIDER_PRESETS) {
    if (p.id === 'custom') continue
    if (p.base_url && url.startsWith(p.base_url.toLowerCase())) return p.id
  }
  if (header) {
    for (const p of PROVIDER_PRESETS) {
      if (p.id === 'custom') continue
      if (p.auth_header.toLowerCase() === header && p.type === spoke.type) return p.id
    }
  }
  return 'custom'
}

function onPresetChange() {
  const preset = selectedPreset.value
  // Reset Test-Result nach Preset-Wechsel.
  testState.value = { running: false, result: null }
  if (preset.id === 'custom') {
    // Custom: nichts ueberschreiben — User behaelt seine Eingaben.
    return
  }
  // Auto-Fuellen — auth_value bleibt leer (User tippt seinen Token).
  form.value.base_url = preset.base_url
  form.value.type = preset.type
  form.value.auth_header = preset.auth_header
  form.value.capabilities = [...preset.capabilities]
  form.value.test_endpoint = preset.test_endpoint || ''
  form.value.auth_value = ''
}

function toggleCap(cap: SpokeCapability) {
  const idx = form.value.capabilities.indexOf(cap)
  if (idx === -1) form.value.capabilities.push(cap)
  else form.value.capabilities.splice(idx, 1)
}

async function onTestConnection() {
  const preset = selectedPreset.value
  const base_url = form.value.base_url.trim()
  if (!base_url) {
    toast.error('Base-URL fehlt.')
    return
  }
  testState.value = { running: true, result: null }
  try {
    const resp = await testSpokeConnection({
      base_url,
      auth_header: form.value.auth_header.trim() || preset.auth_header,
      auth_value: form.value.auth_value
        ? applyAuthPrefix(form.value.auth_value, preset.auth_value_prefix)
        : '',
      test_endpoint: form.value.test_endpoint || preset.test_endpoint || '',
    })
    if (resp.ok) {
      const count = resp.models_count ?? 0
      const latency = resp.latency_ms ?? 0
      const msg = count > 0
        ? `OK — ${count} Modell(e), ${latency} ms`
        : `OK — Status ${resp.status ?? 200}, ${latency} ms`
      testState.value = { running: false, result: { ok: true, message: msg } }
      toast.success(msg)
    } else {
      const msg = `Fehler: ${resp.error || 'unbekannt'}`
      testState.value = { running: false, result: { ok: false, message: msg } }
      toast.error(msg)
    }
  } catch (err) {
    const msg = extractError(err)
    testState.value = { running: false, result: { ok: false, message: msg } }
    toast.error(msg)
  }
}

function submit() {
  const tags = form.value.tags
    .split(',')
    .map(t => t.trim())
    .filter(Boolean)
  const preset = selectedPreset.value
  const headerName = form.value.auth_header.trim() || 'Authorization'
  const finalAuthValue = form.value.auth_value
    ? applyAuthPrefix(form.value.auth_value, preset.auth_value_prefix)
    : ''
  emit('save', {
    name: form.value.name.trim(),
    base_url: form.value.base_url.trim(),
    type: form.value.type,
    capabilities: form.value.capabilities,
    tags,
    priority: Number(form.value.priority),
    enabled: form.value.enabled,
    auth: finalAuthValue
      ? { header: headerName, value: finalAuthValue }
      : null,
    fallback_url: form.value.fallback_url.trim() || null,
  })
}
</script>

<template>
  <Modal :open="open" :title="spoke ? 'Spoke bearbeiten' : 'Neuer Spoke'" width="44rem" @close="emit('close')">
    <form class="space-y-4" @submit.prevent="submit">
      <!-- Provider-Picker -->
      <div class="rounded-md border border-indigo-200 dark:border-indigo-900/60 bg-indigo-50/40 dark:bg-indigo-950/30 p-3 space-y-2">
        <label class="block">
          <span class="block text-xs font-semibold uppercase tracking-wider text-indigo-700 dark:text-indigo-300 mb-1 inline-flex items-center gap-1.5">
            <Sparkles :size="12" />
            Provider-Vorlage
          </span>
          <select
            v-model="selectedPresetId"
            class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
            @change="onPresetChange"
          >
            <option v-for="p in PROVIDER_PRESETS" :key="p.id" :value="p.id">
              {{ p.label }}
            </option>
          </select>
        </label>
        <p v-if="selectedPreset.docs_url" class="text-[11px] text-slate-600 dark:text-slate-400">
          API-Doku:
          <a :href="selectedPreset.docs_url" target="_blank" rel="noopener" class="text-indigo-600 dark:text-indigo-400 hover:underline inline-flex items-center gap-0.5">
            {{ selectedPreset.docs_url }}
            <ExternalLink :size="10" />
          </a>
        </p>
        <p v-if="selectedPreset.notice" class="text-[11px] rounded bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200 px-2 py-1.5 border border-amber-200 dark:border-amber-800">
          <strong>Hinweis:</strong> {{ selectedPreset.notice }}
        </p>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <label class="block">
          <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Name</span>
          <input
v-model="form.name" required placeholder="nuc-gpu-llm-manager"
            class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm font-mono" />
        </label>
        <label class="block">
          <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Priorität (niedriger = bevorzugt)</span>
          <input
v-model.number="form.priority" type="number" min="0" max="10000"
            class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm" />
        </label>
      </div>

      <label class="block">
        <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Base-URL</span>
        <input
v-model="form.base_url" required placeholder="http://100.102.132.11:7842"
          class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm font-mono" />
      </label>

      <label class="block">
        <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Fallback-URL (optional, Auto-Failover)</span>
        <input
v-model="form.fallback_url" placeholder="http://backup-node:7842"
          class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm font-mono" />
        <p class="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
          Bei 3x 5xx/Timeout auf primary schaltet der Proxy temporaer hierher um. Reset nach 5 erfolgreichen primary-Calls.
        </p>
      </label>

      <label class="block">
        <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Typ</span>
        <select v-model="form.type" class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm">
          <option v-for="opt in TYPE_OPTIONS" :key="opt.value" :value="opt.value">
            {{ opt.label }} — {{ opt.hint }}
          </option>
        </select>
      </label>

      <div>
        <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-2">Capabilities</span>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="cap in ALL_CAPABILITIES" :key="cap" type="button"
            class="px-3 py-1.5 rounded-full text-xs font-medium border transition-colors"
            :class="form.capabilities.includes(cap)
              ? 'bg-indigo-600 border-indigo-600 text-white'
              : 'bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800'"
            @click="toggleCap(cap)"
          >{{ cap }}</button>
        </div>
        <p class="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
          Welche Workload-Typen dieser Spoke bedienen kann. Routing-Regeln matchen auf Capability + Modell-Glob.
        </p>
      </div>

      <label class="block">
        <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Tags (komma-getrennt)</span>
        <input
v-model="form.tags" placeholder="nuc, gpu, rtx5070ti, lifecycle"
          class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm" />
      </label>

      <div class="grid grid-cols-3 gap-3">
        <label class="block">
          <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Auth-Header (Name)</span>
          <input
v-model="form.auth_header" placeholder="Authorization"
            class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm font-mono" />
        </label>
        <label class="block col-span-2">
          <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">
            Auth-Wert / API-Key (optional)
          </span>
          <input
v-model="form.auth_value" type="password" autocomplete="off"
            :placeholder="selectedPreset.placeholder_key || 'Bearer eyJ… / sk-…'"
            class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm font-mono" />
        </label>
      </div>
      <p v-if="selectedPreset.auth_value_prefix" class="-mt-2 text-[11px] text-slate-500 dark:text-slate-400">
        Praefix wird automatisch hinzugefuegt: <code class="bg-slate-100 dark:bg-slate-800 px-1 rounded">{{ selectedPreset.auth_value_prefix }}</code>
        — du tippst nur den blanken Token.
      </p>
      <p v-else class="-mt-2 text-[11px] text-slate-500 dark:text-slate-400">
        Header-Name + Wert werden 1:1 an den Spoke weitergereicht. Standard: <code>Authorization</code>. Leer lassen wenn der Spoke ohne Auth erreichbar ist.
      </p>

      <!-- Test-Connection-Button -->
      <div class="flex items-center gap-3 flex-wrap">
        <button
          type="button"
          class="rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 inline-flex items-center gap-1.5 disabled:opacity-50"
          :disabled="testState.running || !form.base_url"
          @click="onTestConnection"
        >
          <Loader2 v-if="testState.running" :size="14" class="animate-spin" />
          <span>{{ testState.running ? 'Teste…' : 'Verbindung testen' }}</span>
        </button>
        <span
          v-if="testState.result"
          class="inline-flex items-center gap-1 text-xs"
          :class="testState.result.ok ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'"
        >
          <CheckCircle2 v-if="testState.result.ok" :size="14" />
          <XCircle v-else :size="14" />
          {{ testState.result.message }}
        </span>
      </div>

      <label class="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
        <input v-model="form.enabled" type="checkbox" class="h-4 w-4 rounded border-slate-300 dark:border-slate-700" />
        Spoke ist aktiv (wird in Health-Loop und Routing einbezogen)
      </label>
    </form>

    <template #footer>
      <button type="button" class="rounded-md px-3 py-1.5 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800" @click="emit('close')">Abbrechen</button>
      <button
type="button" class="rounded-md bg-indigo-600 hover:bg-indigo-700 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
        :disabled="saving || !form.name || !form.base_url || form.capabilities.length === 0"
        @click="submit">
        {{ saving ? 'Speichere...' : (spoke ? 'Speichern' : 'Anlegen') }}
      </button>
    </template>
  </Modal>
</template>
