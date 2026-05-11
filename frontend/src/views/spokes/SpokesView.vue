<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus, Pencil, Trash2, RefreshCw, HeartPulse, Server, Cpu } from 'lucide-vue-next'
import Card from '../../components/shared/Card.vue'
import Badge from '../../components/shared/Badge.vue'
import ProgressBar from '../../components/shared/ProgressBar.vue'
import ConfirmDialog from '../../components/shared/ConfirmDialog.vue'
import EmptyState from '../../components/shared/EmptyState.vue'
import SpokeFormModal from './SpokeFormModal.vue'
import { listSpokes, createSpoke, patchSpoke, deleteSpoke, spokeHealthCheck } from '../../api/spokes'
import { useConfirmStore } from '../../stores/confirm'
import { useToastStore } from '../../stores/toast'
import type { Spoke } from '../../api/types'
import { formatBytes, relativeTime, formatPercent } from '../../utils/format'
import { extractError } from '../../api/client'

const spokes = ref<Spoke[]>([])
const loading = ref(false)
const formOpen = ref(false)
const formSpoke = ref<Spoke | null>(null)
const saving = ref(false)
const confirmDelete = ref<Spoke | null>(null)
const checkingId = ref<string | null>(null)
const toast = useToastStore()
const confirm = useConfirmStore()

async function load() {
  loading.value = true
  try { spokes.value = await listSpokes() }
  catch (err) { toast.error(extractError(err)) }
  finally { loading.value = false }
}
onMounted(load)

function statusVariant(s: string) {
  return s === 'online' ? 'green' : s === 'degraded' ? 'amber' : 'red'
}

function openCreate() { formSpoke.value = null; formOpen.value = true }
function openEdit(s: Spoke) { formSpoke.value = s; formOpen.value = true }

async function onSave(data: Partial<Spoke>) {
  const isUpdate = !!formSpoke.value
  const ok = await confirm.ask({
    title: isUpdate ? 'Spoke speichern?' : 'Neuen Spoke anlegen?',
    message: isUpdate
      ? `"${formSpoke.value?.name}" wird aktualisiert. Routing-Änderungen wirken sofort live.`
      : `Spoke "${data.name}" (${data.type}) wird angelegt und steht ab sofort im Routing zur Verfügung.`,
  })
  if (!ok) return

  saving.value = true
  try {
    if (formSpoke.value) {
      await patchSpoke(formSpoke.value.id, data)
      toast.success('Spoke aktualisiert.')
    } else {
      await createSpoke(data)
      toast.success('Spoke angelegt.')
    }
    formOpen.value = false
    await load()
  } catch (err) { toast.error(extractError(err)) }
  finally { saving.value = false }
}

async function doDelete() {
  if (!confirmDelete.value) return
  try {
    await deleteSpoke(confirmDelete.value.id)
    toast.success('Spoke gelöscht.')
    confirmDelete.value = null
    await load()
  } catch (err) { toast.error(extractError(err)) }
}

async function doHealthCheck(s: Spoke) {
  checkingId.value = s.id
  try {
    const updated = await spokeHealthCheck(s.id)
    toast.success(`${s.name}: ${updated.status}`)
    await load()
  } catch (err) { toast.error(extractError(err)) }
  finally { checkingId.value = null }
}
</script>

<template>
  <div class="space-y-4 animate-fade-in">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">Spokes</h1>
        <p class="text-sm text-slate-500 dark:text-slate-400">GPU/LLM-Hosts hinter dem Router. Live-Status und Modell-Discovery.</p>
      </div>
      <div class="flex items-center gap-2">
        <button class="rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 inline-flex items-center gap-1.5" @click="load">
          <RefreshCw :size="14" /> Neu laden
        </button>
        <button class="rounded-md bg-indigo-600 hover:bg-indigo-700 px-3 py-1.5 text-sm font-semibold text-white inline-flex items-center gap-1.5" @click="openCreate">
          <Plus :size="14" /> Neuer Spoke
        </button>
      </div>
    </div>

    <div v-if="!spokes.length && !loading">
      <Card><EmptyState title="Keine Spokes konfiguriert" message="Lege einen Ollama- oder OpenAI-kompatiblen Endpoint an." /></Card>
    </div>

    <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card v-for="s in spokes" :key="s.id" :padded="true">
        <div class="flex items-start justify-between gap-3 mb-4">
          <div class="flex items-start gap-3 min-w-0">
            <div class="grid place-items-center h-10 w-10 rounded-lg shrink-0" :class="s.status === 'online' ? 'bg-green-500/10 text-green-600 dark:text-green-400' : s.status === 'degraded' ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400' : 'bg-red-500/10 text-red-600 dark:text-red-400'">
              <Server :size="18" />
            </div>
            <div class="min-w-0">
              <h3 class="font-semibold text-slate-900 dark:text-slate-100">{{ s.name }}</h3>
              <p class="text-xs text-slate-500 font-mono truncate">{{ s.base_url }}</p>
              <div class="flex items-center gap-2 mt-1.5 text-[11px] text-slate-500 flex-wrap">
                <Badge :variant="statusVariant(s.status)" dot>{{ s.status }}</Badge>
                <span>·</span>
                <span class="font-medium">{{ s.type }}</span>
                <span>·</span>
                <span>Prio {{ s.priority }}</span>
                <span>·</span>
                <span>geprüft {{ relativeTime(s.last_check_at) }}</span>
                <template v-if="s.source === 'dynamic'">
                  <span>·</span>
                  <Badge :variant="s.status === 'offline' ? 'red' : 'indigo'">dynamic</Badge>
                  <span v-if="s.last_seen_at" class="text-[10px]">HB {{ relativeTime(s.last_seen_at) }}</span>
                </template>
                <template v-if="s.fallback_url">
                  <span>·</span>
                  <span class="text-[10px] font-mono" title="Fallback-URL fuer Auto-Failover">↳ {{ s.fallback_url }}</span>
                </template>
              </div>
              <div v-if="s.capabilities?.length" class="flex flex-wrap gap-1 mt-2">
                <Badge v-for="cap in s.capabilities" :key="cap" variant="indigo">{{ cap }}</Badge>
              </div>
              <div v-if="s.tags?.length" class="flex flex-wrap gap-1 mt-1.5">
                <span v-for="t in s.tags" :key="t" class="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">#{{ t }}</span>
              </div>
            </div>
          </div>
          <div class="flex items-center gap-1 shrink-0">
            <button class="grid place-items-center h-7 w-7 rounded text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-indigo-600" :class="checkingId === s.id ? 'animate-pulse-soft' : ''" :disabled="checkingId === s.id" title="Health-Check" @click="doHealthCheck(s)">
              <HeartPulse :size="14" />
            </button>
            <button
              class="grid place-items-center h-7 w-7 rounded text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent"
              :disabled="s.source === 'dynamic'"
              :title="s.source === 'dynamic' ? 'Dynamisch registriert — bearbeite stattdessen den Spoke-Agent' : 'Bearbeiten'"
              @click="s.source !== 'dynamic' && openEdit(s)"
            >
              <Pencil :size="14" />
            </button>
            <button class="grid place-items-center h-7 w-7 rounded text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-red-600" title="Löschen" @click="confirmDelete = s">
              <Trash2 :size="14" />
            </button>
          </div>
        </div>

        <div v-if="s.gpu_info" class="rounded-md border border-slate-200 dark:border-slate-800 p-3 mb-4 bg-slate-50/50 dark:bg-slate-900/40">
          <div class="flex items-center gap-2 mb-2">
            <Cpu :size="14" class="text-indigo-500" />
            <span class="text-xs font-semibold">{{ s.gpu_info.device || 'GPU' }}</span>
          </div>
          <div class="grid grid-cols-2 gap-3 text-xs">
            <div v-if="s.gpu_info.vram_total_mb">
              <p class="text-slate-500 mb-0.5">VRAM</p>
              <ProgressBar :value="s.gpu_info.vram_used_mb || 0" :max="s.gpu_info.vram_total_mb" />
              <p class="text-[10px] text-slate-500 mt-1 tabular-nums">{{ formatBytes((s.gpu_info.vram_used_mb || 0) * 1024 * 1024) }} / {{ formatBytes(s.gpu_info.vram_total_mb * 1024 * 1024) }}</p>
            </div>
            <div v-if="s.gpu_info.util_pct !== null && s.gpu_info.util_pct !== undefined">
              <p class="text-slate-500 mb-0.5">Auslastung</p>
              <ProgressBar :value="s.gpu_info.util_pct" :max="100" />
              <p class="text-[10px] text-slate-500 mt-1 tabular-nums">{{ formatPercent(s.gpu_info.util_pct) }}</p>
            </div>
          </div>
        </div>

        <div>
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5">Modelle ({{ s.models.length }})</p>
          <div class="flex flex-wrap gap-1">
            <Badge v-for="m in s.models" :key="m" variant="indigo">{{ m }}</Badge>
            <span v-if="!s.models.length" class="text-xs text-slate-500">Keine Modelle entdeckt.</span>
          </div>
        </div>
      </Card>
    </div>

    <SpokeFormModal :open="formOpen" :spoke="formSpoke" :saving="saving" @close="formOpen = false" @save="onSave" />
    <ConfirmDialog
      :open="!!confirmDelete"
      title="Spoke löschen?"
      :message="`Spoke &quot;${confirmDelete?.name}&quot; wird entfernt. Bestehende Routes verlieren ihren Endpoint.`"
      confirm-text="Löschen"
      danger
      @confirm="doDelete"
      @cancel="confirmDelete = null"
    />
  </div>
</template>
