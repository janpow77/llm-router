<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RefreshCw, Boxes } from 'lucide-vue-next'
import Card from '../../components/shared/Card.vue'
import SortableTable from '../../components/tables/SortableTable.vue'
import EmptyState from '../../components/shared/EmptyState.vue'
import Badge from '../../components/shared/Badge.vue'
import { listModels, refreshModels } from '../../api/models'
import { useToastStore } from '../../stores/toast'
import type { ModelInfo } from '../../api/types'
import { extractError } from '../../api/client'

const models = ref<ModelInfo[]>([])
const loading = ref(false)
const refreshing = ref(false)
const toast = useToastStore()

async function load() {
  loading.value = true
  try { models.value = await listModels() }
  catch (err) { toast.error(extractError(err)) }
  finally { loading.value = false }
}

async function doRefresh() {
  refreshing.value = true
  try {
    const result = await refreshModels()
    toast.success(`${result.discovered} Modelle gefunden.`)
    await load()
  } catch (err) { toast.error(extractError(err)) }
  finally { refreshing.value = false }
}

onMounted(load)

const columns = [
  { key: 'name', label: 'Modell', sortable: true },
  { key: 'spoke_name', label: 'Spoke', sortable: true },
  { key: 'quantization', label: 'Quantization', sortable: true, align: 'center' as const },
  { key: 'size_gb', label: 'Größe', sortable: true, align: 'right' as const },
  { key: 'context_length', label: 'Context', sortable: true, align: 'right' as const },
]

function asModel(row: unknown): ModelInfo {
  return row as ModelInfo
}
</script>

<template>
  <div class="space-y-4 animate-fade-in">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">Modelle</h1>
        <p class="text-sm text-slate-500 dark:text-slate-400">Modell-Discovery aus allen Spokes. Refresh holt aktuelle Liste vom Backend.</p>
      </div>
      <button class="rounded-md bg-indigo-600 hover:bg-indigo-700 px-3 py-1.5 text-sm font-semibold text-white inline-flex items-center gap-1.5 disabled:opacity-50" :disabled="refreshing" @click="doRefresh">
        <RefreshCw :size="14" :class="refreshing ? 'animate-spin' : ''" />
        {{ refreshing ? 'Aktualisiere...' : 'Refresh from Spokes' }}
      </button>
    </div>

    <Card padded>
      <SortableTable v-if="models.length" :columns="columns" :rows="models as unknown as Record<string, unknown>[]" :row-key="(r) => asModel(r).id">
        <template #cell-name="{ row }">
          <div class="flex items-center gap-2">
            <Boxes :size="14" class="text-indigo-500 shrink-0" />
            <span class="font-mono font-semibold">{{ asModel(row).name }}</span>
          </div>
        </template>
        <template #cell-spoke_name="{ row }">
          <Badge variant="blue">{{ asModel(row).spoke_name }}</Badge>
        </template>
        <template #cell-quantization="{ row }">
          <span class="font-mono text-xs">{{ asModel(row).quantization }}</span>
        </template>
        <template #cell-size_gb="{ row }">
          <span class="tabular-nums">{{ asModel(row).size_gb.toFixed(1).replace('.', ',') }} GB</span>
        </template>
        <template #cell-context_length="{ row }">
          <span class="tabular-nums">{{ asModel(row).context_length.toLocaleString('de-DE') }}</span>
        </template>
      </SortableTable>
      <EmptyState v-else title="Keine Modelle gefunden" message="Klick „Refresh from Spokes“, um Modelle abzufragen." />
    </Card>
  </div>
</template>
