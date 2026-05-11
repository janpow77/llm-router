<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { Plus, Trash2, GripVertical, Save, ArrowUp, ArrowDown } from 'lucide-vue-next'
import Card from '../../components/shared/Card.vue'
import Badge from '../../components/shared/Badge.vue'
import EmptyState from '../../components/shared/EmptyState.vue'
import ConfirmDialog from '../../components/shared/ConfirmDialog.vue'
import { listRoutes, createRoute, patchRoute, deleteRoute } from '../../api/routes'
import { listSpokes } from '../../api/spokes'
import { useConfirmStore } from '../../stores/confirm'
import { useToastStore } from '../../stores/toast'
import type { RouteRule, Spoke } from '../../api/types'
import { extractError } from '../../api/client'

const routes = ref<RouteRule[]>([])
const spokes = ref<Spoke[]>([])
const toast = useToastStore()
const confirm = useConfirmStore()
const newGlob = ref('')
const newSpokeId = ref('')
const confirmDelete = ref<RouteRule | null>(null)
const editingId = ref<string | null>(null)

async function load() {
  try {
    const [r, s] = await Promise.all([listRoutes(), listSpokes()])
    routes.value = r.sort((a, b) => a.priority - b.priority)
    spokes.value = s
    if (s.length && !newSpokeId.value) newSpokeId.value = s[0].id
  } catch (err) { toast.error(extractError(err)) }
}
onMounted(load)

const sortedRoutes = computed(() => [...routes.value].sort((a, b) => a.priority - b.priority))

async function addRoute() {
  if (!newGlob.value || !newSpokeId.value) return
  const spokeName = spokes.value.find(s => s.id === newSpokeId.value)?.name || newSpokeId.value
  const ok = await confirm.ask({
    title: 'Neue Route anlegen?',
    message: `Glob "${newGlob.value.trim()}" → Spoke "${spokeName}". Wirkt sofort live im Routing.`,
  })
  if (!ok) return
  try {
    const max = routes.value.reduce((m, r) => Math.max(m, r.priority), 0)
    await createRoute({
      model_glob: newGlob.value.trim(),
      spoke_id: newSpokeId.value,
      priority: max + 10,
      enabled: true,
    })
    toast.success('Route angelegt.')
    newGlob.value = ''
    await load()
  } catch (err) { toast.error(extractError(err)) }
}

async function move(route: RouteRule, dir: 'up' | 'down') {
  const list = sortedRoutes.value
  const idx = list.findIndex(r => r.id === route.id)
  const swap = dir === 'up' ? idx - 1 : idx + 1
  if (swap < 0 || swap >= list.length) return
  const other = list[swap]
  try {
    await Promise.all([
      patchRoute(route.id, { priority: other.priority }),
      patchRoute(other.id, { priority: route.priority }),
    ])
    await load()
  } catch (err) { toast.error(extractError(err)) }
}

async function toggleEnabled(route: RouteRule) {
  const ok = await confirm.ask({
    title: route.enabled ? 'Route deaktivieren?' : 'Route aktivieren?',
    message: `"${route.model_glob}" wird ${route.enabled ? 'aus dem Routing entfernt' : 'wieder in das Routing aufgenommen'}.`,
    danger: route.enabled,
  })
  if (!ok) return
  try {
    await patchRoute(route.id, { enabled: !route.enabled })
    await load()
  } catch (err) { toast.error(extractError(err)) }
}

async function updateGlob(route: RouteRule, value: string) {
  if (value === route.model_glob) { editingId.value = null; return }
  const ok = await confirm.ask({
    title: 'Glob speichern?',
    message: `"${route.model_glob}" → "${value}". Wirkt sofort live.`,
  })
  if (!ok) { editingId.value = null; return }
  try {
    await patchRoute(route.id, { model_glob: value })
    toast.success('Glob aktualisiert.')
    editingId.value = null
    await load()
  } catch (err) { toast.error(extractError(err)) }
}

async function updateSpoke(route: RouteRule, spokeId: string) {
  if (spokeId === route.spoke_id) return
  const newSpokeName = spokes.value.find(s => s.id === spokeId)?.name || spokeId
  const ok = await confirm.ask({
    title: 'Ziel-Spoke ändern?',
    message: `"${route.model_glob}" → "${newSpokeName}" (neuer Spoke). Wirkt sofort live.`,
  })
  if (!ok) {
    await load()
    return
  }
  try {
    await patchRoute(route.id, { spoke_id: spokeId })
    toast.success('Spoke geändert.')
    await load()
  } catch (err) { toast.error(extractError(err)) }
}

async function doDelete() {
  if (!confirmDelete.value) return
  try {
    await deleteRoute(confirmDelete.value.id)
    toast.success('Route gelöscht.')
    confirmDelete.value = null
    await load()
  } catch (err) { toast.error(extractError(err)) }
}
</script>

<template>
  <div class="space-y-4 animate-fade-in">
    <div>
      <h1 class="text-2xl font-bold tracking-tight">Routing-Regeln</h1>
      <p class="text-sm text-slate-500 dark:text-slate-400">Welches Modell-Pattern wird auf welchen Spoke geroutet? Erste passende Regel (kleinste Priority) gewinnt.</p>
    </div>

    <Card title="Neue Regel">
      <div class="flex flex-wrap items-end gap-3">
        <label class="flex-1 min-w-[180px]">
          <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Model-Glob</span>
          <input v-model="newGlob" placeholder="qwen3:* oder *" class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm font-mono" />
        </label>
        <label class="flex-1 min-w-[180px]">
          <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1">Spoke</span>
          <select v-model="newSpokeId" class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm">
            <option v-for="s in spokes" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
        </label>
        <button class="rounded-md bg-indigo-600 hover:bg-indigo-700 px-3 py-2 text-sm font-semibold text-white inline-flex items-center gap-1.5 disabled:opacity-50" :disabled="!newGlob || !newSpokeId" @click="addRoute">
          <Plus :size="14" /> Hinzufügen
        </button>
      </div>
    </Card>

    <Card padded>
      <EmptyState v-if="!sortedRoutes.length" title="Noch keine Routing-Regeln" message="Mindestens eine Fallback-Regel (* → spoke) wird empfohlen." />
      <div v-else class="space-y-2">
        <div
          v-for="(r, idx) in sortedRoutes"
          :key="r.id"
          class="flex items-center gap-3 rounded-md border border-slate-200 dark:border-slate-800 px-3 py-2.5 hover:bg-slate-50/70 dark:hover:bg-slate-900/40 transition-colors"
        >
          <GripVertical :size="14" class="text-slate-400 shrink-0" />
          <div class="flex flex-col gap-0.5 w-12 shrink-0">
            <button class="text-slate-400 hover:text-indigo-600 disabled:opacity-30" :disabled="idx === 0" @click="move(r, 'up')">
              <ArrowUp :size="12" />
            </button>
            <button class="text-slate-400 hover:text-indigo-600 disabled:opacity-30" :disabled="idx === sortedRoutes.length - 1" @click="move(r, 'down')">
              <ArrowDown :size="12" />
            </button>
          </div>
          <Badge variant="slate">#{{ r.priority }}</Badge>
          <div class="flex-1 min-w-0">
            <input
              v-if="editingId === r.id"
              :value="r.model_glob"
              autofocus
              class="w-full px-2 py-1 rounded border border-indigo-400 bg-white dark:bg-slate-900 text-sm font-mono"
              @keyup.enter="(e) => updateGlob(r, (e.target as HTMLInputElement).value)"
              @keyup.esc="editingId = null"
            />
            <button v-else class="font-mono text-sm text-slate-900 dark:text-slate-100 hover:text-indigo-600" @click="editingId = r.id">{{ r.model_glob }}</button>
          </div>
          <span class="text-slate-400">→</span>
          <select :value="r.spoke_id" class="px-2 py-1 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm" @change="(e) => updateSpoke(r, (e.target as HTMLSelectElement).value)">
            <option v-for="s in spokes" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
          <label class="inline-flex items-center gap-1.5 cursor-pointer">
            <input :checked="r.enabled" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" @change="toggleEnabled(r)" />
            <span class="text-xs text-slate-600 dark:text-slate-400">aktiv</span>
          </label>
          <button class="grid place-items-center h-7 w-7 rounded text-slate-400 hover:bg-red-50 dark:hover:bg-red-900/30 hover:text-red-600" @click="confirmDelete = r">
            <Trash2 :size="14" />
          </button>
        </div>
        <p class="text-xs text-slate-500 mt-3">
          <Save :size="11" class="inline" /> Änderungen werden direkt gespeichert. Klick auf den Glob-Text zum Editieren, Enter zum Bestätigen.
        </p>
      </div>
    </Card>

    <ConfirmDialog
      :open="!!confirmDelete"
      title="Route löschen?"
      :message="`Regel &quot;${confirmDelete?.model_glob}&quot; → ${confirmDelete?.spoke_name} wird entfernt.`"
      confirm-text="Löschen"
      danger
      @confirm="doDelete"
      @cancel="confirmDelete = null"
    />
  </div>
</template>
