<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { Plus, Pencil, Trash2, Power, KeyRound, Eye, RefreshCw, Copy } from 'lucide-vue-next'
import Card from '../../components/shared/Card.vue'
import Badge from '../../components/shared/Badge.vue'
import ProgressBar from '../../components/shared/ProgressBar.vue'
import ConfirmDialog from '../../components/shared/ConfirmDialog.vue'
import Modal from '../../components/shared/Modal.vue'
import SortableTable from '../../components/tables/SortableTable.vue'
import EmptyState from '../../components/shared/EmptyState.vue'
import AppFormModal from './AppFormModal.vue'
import AppDetailDrawer from './AppDetailDrawer.vue'
import { listApps, createApp, patchApp, deleteApp, rotateAppKey, toggleAppEnabled } from '../../api/apps'
import { listModels } from '../../api/models'
import { useConfirmStore } from '../../stores/confirm'
import { useToastStore } from '../../stores/toast'
import type { App, ModelInfo } from '../../api/types'
import { formatNumber, relativeTime } from '../../utils/format'
import { extractError } from '../../api/client'

const apps = ref<App[]>([])
const models = ref<ModelInfo[]>([])
const loading = ref(true)
const toast = useToastStore()
const confirm = useConfirmStore()

const formOpen = ref(false)
const formApp = ref<App | null>(null)
const saving = ref(false)
const detailOpen = ref(false)
const detailId = ref<string | null>(null)
const confirmDelete = ref<App | null>(null)
const confirmRotate = ref<App | null>(null)
const newKeyShown = ref<string | null>(null)

async function load() {
  loading.value = true
  try {
    const [a, m] = await Promise.all([listApps(), listModels()])
    apps.value = a
    models.value = m
  } catch (err) {
    toast.error(extractError(err))
  } finally { loading.value = false }
}

onMounted(load)

function openCreate() {
  formApp.value = null
  formOpen.value = true
}

function openEdit(app: App) {
  formApp.value = app
  formOpen.value = true
}

function openDetail(app: App) {
  detailId.value = app.id
  detailOpen.value = true
}

async function onSave(data: Partial<App>) {
  const isUpdate = !!formApp.value
  const ok = await confirm.ask({
    title: isUpdate ? 'App-Änderungen speichern?' : 'Neue App anlegen?',
    message: isUpdate
      ? `"${formApp.value?.name}" wird aktualisiert. Änderungen wirken sofort live.`
      : `App "${data.name}" wird angelegt. Wirkt sofort live im Routing.`,
  })
  if (!ok) return

  saving.value = true
  try {
    if (formApp.value) {
      await patchApp(formApp.value.id, data)
      toast.success('App aktualisiert.')
    } else {
      const created = await createApp(data)
      toast.success(`App "${created.name}" angelegt.`)
      if (created.api_key) newKeyShown.value = created.api_key
    }
    formOpen.value = false
    await load()
  } catch (err) { toast.error(extractError(err)) }
  finally { saving.value = false }
}

async function doToggle(app: App) {
  const action = app.enabled ? 'deaktivieren' : 'aktivieren'
  const ok = await confirm.ask({
    title: `App ${action}?`,
    message: `"${app.name}" wird ${action}. ${app.enabled ? 'Eingehende Requests werden ab sofort abgewiesen.' : 'App akzeptiert wieder Requests.'}`,
    danger: app.enabled,
  })
  if (!ok) return
  try {
    await toggleAppEnabled(app.id)
    toast.success(`${app.name} ${app.enabled ? 'deaktiviert' : 'aktiviert'}.`)
    await load()
  } catch (err) { toast.error(extractError(err)) }
}

async function doDelete() {
  if (!confirmDelete.value) return
  try {
    await deleteApp(confirmDelete.value.id)
    toast.success('App gelöscht.')
    confirmDelete.value = null
    await load()
  } catch (err) { toast.error(extractError(err)) }
}

async function doRotate() {
  if (!confirmRotate.value) return
  try {
    const result = await rotateAppKey(confirmRotate.value.id)
    newKeyShown.value = result.api_key
    toast.success('API-Key rotiert.')
    confirmRotate.value = null
    await load()
  } catch (err) { toast.error(extractError(err)) }
}

function copyKey() {
  if (!newKeyShown.value) return
  navigator.clipboard.writeText(newKeyShown.value)
  toast.success('In Zwischenablage kopiert.')
}

const columns = [
  { key: 'name', label: 'Name', sortable: true },
  { key: 'api_key_preview', label: 'API-Key', sortable: false },
  { key: 'allowed_models', label: 'Modelle', sortable: false },
  { key: 'request_count_today', label: 'Heute', sortable: true, align: 'right' as const },
  { key: 'quota_pct', label: 'Quota-Auslastung', sortable: false },
  { key: 'enabled', label: 'Status', sortable: true, align: 'center' as const },
  { key: 'updated_at', label: 'Aktualisiert', sortable: true },
]

const tableRows = computed(() => apps.value.map(a => ({
  ...a,
  quota_pct: a.quota.daily_tokens ? Math.min(100, Math.round((a.request_count_today * 1500) / a.quota.daily_tokens * 100)) : 0,
})))

function quotaPct(row: unknown): number {
  return (row as { quota_pct: number }).quota_pct ?? 0
}

function asApp(row: unknown): App {
  return row as App
}
</script>

<template>
  <div class="space-y-4 animate-fade-in">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">Apps</h1>
        <p class="text-sm text-slate-500 dark:text-slate-400">Anwendungen die den Router nutzen — Quotas, Keys und Modell-Whitelists.</p>
      </div>
      <div class="flex items-center gap-2">
        <button class="rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 inline-flex items-center gap-1.5" @click="load">
          <RefreshCw :size="14" /> Neu laden
        </button>
        <button class="rounded-md bg-indigo-600 hover:bg-indigo-700 px-3 py-1.5 text-sm font-semibold text-white inline-flex items-center gap-1.5" @click="openCreate">
          <Plus :size="14" /> Neue App
        </button>
      </div>
    </div>

    <Card padded>
      <SortableTable v-if="apps.length" :columns="columns" :rows="tableRows as unknown as Record<string, unknown>[]" :row-key="(r) => asApp(r).id">
        <template #cell-name="{ row }">
          <div>
            <p class="font-semibold text-slate-900 dark:text-slate-100">{{ asApp(row).name }}</p>
            <p v-if="asApp(row).description" class="text-xs text-slate-500">{{ asApp(row).description }}</p>
          </div>
        </template>
        <template #cell-api_key_preview="{ row }">
          <span class="font-mono text-xs text-slate-600 dark:text-slate-400">{{ asApp(row).api_key_preview }}</span>
        </template>
        <template #cell-allowed_models="{ row }">
          <div class="flex flex-wrap gap-1">
            <span v-for="m in asApp(row).allowed_models.slice(0, 3)" :key="m" class="font-mono text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">{{ m }}</span>
            <span v-if="asApp(row).allowed_models.length > 3" class="text-[10px] text-slate-500">+{{ asApp(row).allowed_models.length - 3 }}</span>
          </div>
        </template>
        <template #cell-request_count_today="{ row }">
          <span class="tabular-nums">{{ formatNumber(asApp(row).request_count_today) }}</span>
        </template>
        <template #cell-quota_pct="{ row }">
          <div class="w-32">
            <ProgressBar :value="quotaPct(row)" :max="100" />
          </div>
        </template>
        <template #cell-enabled="{ row }">
          <Badge :variant="asApp(row).enabled ? 'green' : 'slate'" dot>{{ asApp(row).enabled ? 'Aktiv' : 'Pausiert' }}</Badge>
        </template>
        <template #cell-updated_at="{ row }">
          <span class="text-xs text-slate-500">{{ relativeTime(asApp(row).updated_at) }}</span>
        </template>
        <template #actions="{ row }">
          <div class="inline-flex items-center gap-1">
            <button class="grid place-items-center h-7 w-7 rounded text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100" title="Details" @click="openDetail(asApp(row))">
              <Eye :size="14" />
            </button>
            <button class="grid place-items-center h-7 w-7 rounded text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100" title="Bearbeiten" @click="openEdit(asApp(row))">
              <Pencil :size="14" />
            </button>
            <button class="grid place-items-center h-7 w-7 rounded text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-amber-600" title="Aktivieren/Deaktivieren" @click="doToggle(asApp(row))">
              <Power :size="14" />
            </button>
            <button class="grid place-items-center h-7 w-7 rounded text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-amber-600" title="API-Key rotieren" @click="confirmRotate = asApp(row)">
              <KeyRound :size="14" />
            </button>
            <button class="grid place-items-center h-7 w-7 rounded text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-red-600" title="Löschen" @click="confirmDelete = asApp(row)">
              <Trash2 :size="14" />
            </button>
          </div>
        </template>
      </SortableTable>
      <EmptyState v-else title="Noch keine Apps angelegt" message="Lege eine erste App an, um den Router zu nutzen.">
        <template #action>
          <button class="rounded-md bg-indigo-600 hover:bg-indigo-700 px-3 py-1.5 text-sm font-semibold text-white inline-flex items-center gap-1.5" @click="openCreate">
            <Plus :size="14" /> Neue App
          </button>
        </template>
      </EmptyState>
    </Card>

    <AppFormModal :open="formOpen" :app="formApp" :available-models="models" :saving="saving" @close="formOpen = false" @save="onSave" />
    <AppDetailDrawer :open="detailOpen" :app-id="detailId" @close="detailOpen = false" />

    <ConfirmDialog
      :open="!!confirmDelete"
      title="App löschen?"
      :message="`Die App &quot;${confirmDelete?.name}&quot; wird unwiderruflich gelöscht.`"
      confirm-text="Löschen"
      danger
      @confirm="doDelete"
      @cancel="confirmDelete = null"
    />
    <ConfirmDialog
      :open="!!confirmRotate"
      title="API-Key rotieren?"
      :message="`Der bisherige Key für &quot;${confirmRotate?.name}&quot; wird sofort ungültig. Der neue Key wird genau einmal angezeigt.`"
      confirm-text="Rotieren"
      danger
      @confirm="doRotate"
      @cancel="confirmRotate = null"
    />

    <Modal :open="!!newKeyShown" title="Neuer API-Key" width="32rem" @close="newKeyShown = null">
      <p class="text-sm text-slate-700 dark:text-slate-300 mb-3">Dieser Key wird <strong>nur einmal</strong> angezeigt. Speichere ihn jetzt sicher ab.</p>
      <div class="rounded-md border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/30 p-3">
        <code class="font-mono text-sm break-all">{{ newKeyShown }}</code>
      </div>
      <template #footer>
        <button class="rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-sm font-medium inline-flex items-center gap-1.5" @click="copyKey">
          <Copy :size="14" /> Kopieren
        </button>
        <button class="rounded-md bg-indigo-600 hover:bg-indigo-700 px-3 py-1.5 text-sm font-semibold text-white" @click="newKeyShown = null">Verstanden</button>
      </template>
    </Modal>
  </div>
</template>
