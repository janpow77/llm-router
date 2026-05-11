<script setup lang="ts">
import { ref, watch } from 'vue'
import Modal from '../../components/shared/Modal.vue'
import type { Spoke, SpokeCapability, SpokeType } from '../../api/types'

const props = defineProps<{ open: boolean; spoke: Spoke | null; saving: boolean }>()
const emit = defineEmits<{ close: []; save: [data: Partial<Spoke>] }>()

const TYPE_OPTIONS: { value: SpokeType; label: string; hint: string }[] = [
  { value: 'gpu-llm-manager', label: 'GPU-LLM-Manager', hint: 'Lifecycle-Manager auf NUC/evo/Desktop' },
  { value: 'ollama', label: 'Ollama (direkt)', hint: 'Direkter Ollama-Endpoint, kein Lease-Tracking' },
  { value: 'openai', label: 'OpenAI-kompatibel', hint: 'vLLM, llama.cpp, eigener Server' },
  { value: 'paddle-ocr', label: 'Paddle-OCR', hint: 'OCR-Workload' },
  { value: 'custom', label: 'Custom HTTP', hint: 'Beliebiger Workload' },
]

const ALL_CAPABILITIES: SpokeCapability[] = ['llm', 'embedding', 'rerank', 'ocr', 'vision', 'compute', 'image-gen']

const form = ref({
  name: '',
  base_url: '',
  type: 'gpu-llm-manager' as SpokeType,
  capabilities: ['llm'] as SpokeCapability[],
  tags: '' as string, // comma-separated im UI
  priority: 100,
  auth_header: 'Authorization',
  auth_value: '',
  enabled: true,
  fallback_url: '' as string,
})

watch(() => [props.open, props.spoke], () => {
  if (!props.open) return
  if (props.spoke) {
    form.value = {
      name: props.spoke.name,
      base_url: props.spoke.base_url,
      type: props.spoke.type,
      capabilities: [...(props.spoke.capabilities || ['llm'])],
      tags: (props.spoke.tags || []).join(', '),
      priority: props.spoke.priority ?? 100,
      auth_header: props.spoke.auth?.header || 'Authorization',
      auth_value: props.spoke.auth?.value || '',
      enabled: props.spoke.enabled,
      fallback_url: props.spoke.fallback_url || '',
    }
  } else {
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
    }
  }
}, { immediate: true })

function toggleCap(cap: SpokeCapability) {
  const idx = form.value.capabilities.indexOf(cap)
  if (idx === -1) form.value.capabilities.push(cap)
  else form.value.capabilities.splice(idx, 1)
}

function submit() {
  const tags = form.value.tags
    .split(',')
    .map(t => t.trim())
    .filter(Boolean)
  const headerName = form.value.auth_header.trim() || 'Authorization'
  emit('save', {
    name: form.value.name.trim(),
    base_url: form.value.base_url.trim(),
    type: form.value.type,
    capabilities: form.value.capabilities,
    tags,
    priority: Number(form.value.priority),
    enabled: form.value.enabled,
    auth: form.value.auth_value
      ? { header: headerName, value: form.value.auth_value }
      : null,
    fallback_url: form.value.fallback_url.trim() || null,
  })
}
</script>

<template>
  <Modal :open="open" :title="spoke ? 'Spoke bearbeiten' : 'Neuer Spoke'" width="44rem" @close="emit('close')">
    <form class="space-y-4" @submit.prevent="submit">
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
            @click="toggleCap(cap)"
            class="px-3 py-1.5 rounded-full text-xs font-medium border transition-colors"
            :class="form.capabilities.includes(cap)
              ? 'bg-indigo-600 border-indigo-600 text-white'
              : 'bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800'"
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
          <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Auth-Wert / API-Key (optional)</span>
          <input
v-model="form.auth_value" type="password" autocomplete="off" placeholder="Bearer eyJ… / sk-…"
            class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm font-mono" />
        </label>
      </div>
      <p class="-mt-2 text-[11px] text-slate-500 dark:text-slate-400">
        Header-Name + Wert werden 1:1 an den Spoke weitergereicht. Standard: <code>Authorization</code>. Leer lassen wenn der Spoke ohne Auth erreichbar ist.
      </p>

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
