<script setup lang="ts">
import { ref, watch } from 'vue'
import Modal from '../../components/shared/Modal.vue'
import type { App, ModelInfo } from '../../api/types'

const props = defineProps<{
  open: boolean
  app: App | null
  availableModels: ModelInfo[]
  saving: boolean
}>()

const emit = defineEmits<{
  close: []
  save: [data: Partial<App>]
}>()

const form = ref({
  name: '',
  description: '',
  allowed_models: [] as string[],
  rpm: 60,
  concurrent: 4,
  daily_tokens: 1_000_000,
  enabled: true,
})

watch(() => [props.open, props.app], () => {
  if (props.open) {
    if (props.app) {
      form.value = {
        name: props.app.name,
        description: props.app.description || '',
        allowed_models: [...props.app.allowed_models],
        rpm: props.app.quota.rpm,
        concurrent: props.app.quota.concurrent,
        daily_tokens: props.app.quota.daily_tokens,
        enabled: props.app.enabled,
      }
    } else {
      form.value = { name: '', description: '', allowed_models: [], rpm: 60, concurrent: 4, daily_tokens: 1_000_000, enabled: true }
    }
  }
}, { immediate: true })

function toggleModel(name: string) {
  const idx = form.value.allowed_models.indexOf(name)
  if (idx === -1) form.value.allowed_models.push(name)
  else form.value.allowed_models.splice(idx, 1)
}

function submit() {
  emit('save', {
    name: form.value.name.trim(),
    description: form.value.description.trim(),
    allowed_models: form.value.allowed_models,
    quota: {
      rpm: Number(form.value.rpm),
      concurrent: Number(form.value.concurrent),
      daily_tokens: Number(form.value.daily_tokens),
    },
    enabled: form.value.enabled,
  })
}
</script>

<template>
  <Modal :open="open" :title="app ? 'App bearbeiten' : 'Neue App anlegen'" width="42rem" @close="emit('close')">
    <form class="space-y-4" @submit.prevent="submit">
      <div class="grid grid-cols-2 gap-4">
        <label class="block">
          <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Name</span>
          <input
            v-model="form.name"
            required
            placeholder="audit_designer"
            class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </label>
        <label class="block">
          <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Aktiviert</span>
          <div class="flex items-center gap-2 h-10">
            <input v-model="form.enabled" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
            <span class="text-sm text-slate-700 dark:text-slate-300">App akzeptiert Requests</span>
          </div>
        </label>
      </div>

      <label class="block">
        <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Beschreibung</span>
        <input
          v-model="form.description"
          placeholder="Workshop-Demo (Hetzner CCX23)"
          class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </label>

      <div>
        <p class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-2">Erlaubte Modelle</p>
        <div class="flex flex-wrap gap-1.5">
          <button
            v-for="m in availableModels"
            :key="m.id"
            type="button"
            class="px-2.5 py-1 rounded-md text-xs font-mono border transition-colors"
            :class="form.allowed_models.includes(m.name)
              ? 'bg-indigo-600 text-white border-indigo-600'
              : 'bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 border-slate-300 dark:border-slate-700 hover:border-indigo-400'"
            @click="toggleModel(m.name)"
          >{{ m.name }}</button>
          <button
            type="button"
            class="px-2.5 py-1 rounded-md text-xs font-mono border transition-colors"
            :class="form.allowed_models.includes('*')
              ? 'bg-indigo-600 text-white border-indigo-600'
              : 'bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 border-slate-300 dark:border-slate-700 hover:border-indigo-400'"
            @click="toggleModel('*')"
          >* (alle)</button>
        </div>
      </div>

      <div>
        <p class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-2">Quota-Limits</p>
        <div class="grid grid-cols-3 gap-3">
          <label class="block">
            <span class="block text-xs text-slate-600 dark:text-slate-400 mb-1">Requests / min</span>
            <input v-model.number="form.rpm" type="number" min="0" class="w-full px-2.5 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm tabular-nums" />
          </label>
          <label class="block">
            <span class="block text-xs text-slate-600 dark:text-slate-400 mb-1">Concurrent</span>
            <input v-model.number="form.concurrent" type="number" min="0" class="w-full px-2.5 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm tabular-nums" />
          </label>
          <label class="block">
            <span class="block text-xs text-slate-600 dark:text-slate-400 mb-1">Tokens / Tag</span>
            <input v-model.number="form.daily_tokens" type="number" min="0" step="100000" class="w-full px-2.5 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm tabular-nums" />
          </label>
        </div>
      </div>
    </form>
    <template #footer>
      <button class="rounded-md px-3 py-1.5 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800" @click="emit('close')">Abbrechen</button>
      <button
        class="rounded-md bg-indigo-600 hover:bg-indigo-700 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
        :disabled="saving || !form.name"
        @click="submit"
      >{{ saving ? 'Speichere...' : (app ? 'Speichern' : 'Anlegen') }}</button>
    </template>
  </Modal>
</template>
