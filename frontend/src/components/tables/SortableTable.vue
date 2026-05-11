<script setup lang="ts">
import { ref, computed } from 'vue'
import { ChevronUp, ChevronDown } from 'lucide-vue-next'

type Row = Record<string, unknown>
interface Column {
  key: string
  label: string
  sortable?: boolean
  align?: 'left' | 'right' | 'center'
  width?: string
}

const props = defineProps<{
  columns: Column[]
  rows: Row[]
  rowKey?: (_row: Row) => string | number
}>()

const sortKey = ref<string | null>(null)
const sortDir = ref<'asc' | 'desc'>('asc')

function toggleSort(col: Column) {
  if (col.sortable === false) return
  if (sortKey.value === String(col.key)) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = String(col.key)
    sortDir.value = 'asc'
  }
}

const sorted = computed(() => {
  if (!sortKey.value) return props.rows
  const key = sortKey.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  return [...props.rows].sort((a, b) => {
    const av = a[key] as unknown
    const bv = b[key] as unknown
    if (av === bv) return 0
    if (av === null || av === undefined) return 1
    if (bv === null || bv === undefined) return -1
    return (av as number) > (bv as number) ? dir : -dir
  })
})

function getRowKey(row: Row, idx: number): string | number {
  return props.rowKey ? props.rowKey(row) : idx
}
</script>

<template>
  <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-slate-200 dark:border-slate-800 text-left">
          <th
            v-for="col in columns"
            :key="String(col.key)"
            class="px-4 py-2.5 text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider select-none"
            :class="[
              col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left',
              col.sortable !== false ? 'cursor-pointer hover:text-slate-900 dark:hover:text-slate-200' : '',
            ]"
            :style="col.width ? { width: col.width } : {}"
            @click="toggleSort(col)"
          >
            <span class="inline-flex items-center gap-1">
              {{ col.label }}
              <template v-if="sortKey === String(col.key)">
                <ChevronUp v-if="sortDir === 'asc'" :size="12" />
                <ChevronDown v-else :size="12" />
              </template>
            </span>
          </th>
          <th v-if="$slots.actions" class="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400">Aktionen</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, idx) in sorted"
          :key="getRowKey(row, idx)"
          class="border-b border-slate-100 dark:border-slate-800/60 hover:bg-slate-50 dark:hover:bg-slate-900/40 transition-colors"
        >
          <td
            v-for="col in columns"
            :key="String(col.key)"
            class="px-4 py-3"
            :class="col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'"
          >
            <slot :name="`cell-${String(col.key)}`" :row="row" :value="(row as Record<string, unknown>)[String(col.key)]">
              {{ (row as Record<string, unknown>)[String(col.key)] }}
            </slot>
          </td>
          <td v-if="$slots.actions" class="px-4 py-3 text-right">
            <slot name="actions" :row="row" />
          </td>
        </tr>
        <tr v-if="!sorted.length">
          <td :colspan="columns.length + ($slots.actions ? 1 : 0)" class="px-4 py-8 text-center text-slate-500 dark:text-slate-400">
            <slot name="empty">Keine Einträge.</slot>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
