<script setup lang="ts">
import { computed } from 'vue'
type Variant = 'green' | 'red' | 'amber' | 'blue' | 'slate' | 'indigo'
const props = defineProps<{ variant?: Variant; dot?: boolean }>()

const classes = computed(() => {
  const v = props.variant || 'slate'
  const map: Record<Variant, string> = {
    green: 'bg-green-50 text-green-700 ring-green-600/20 dark:bg-green-900/30 dark:text-green-300 dark:ring-green-400/30',
    red: 'bg-red-50 text-red-700 ring-red-600/20 dark:bg-red-900/30 dark:text-red-300 dark:ring-red-400/30',
    amber: 'bg-amber-50 text-amber-800 ring-amber-600/20 dark:bg-amber-900/30 dark:text-amber-300 dark:ring-amber-400/30',
    blue: 'bg-blue-50 text-blue-700 ring-blue-600/20 dark:bg-blue-900/30 dark:text-blue-300 dark:ring-blue-400/30',
    slate: 'bg-slate-100 text-slate-700 ring-slate-500/20 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-500/30',
    indigo: 'bg-indigo-50 text-indigo-700 ring-indigo-600/20 dark:bg-indigo-900/30 dark:text-indigo-300 dark:ring-indigo-400/30',
  }
  return map[v]
})

const dotColor = computed(() => {
  const v = props.variant || 'slate'
  const map: Record<Variant, string> = {
    green: 'bg-green-500', red: 'bg-red-500', amber: 'bg-amber-500',
    blue: 'bg-blue-500', slate: 'bg-slate-400', indigo: 'bg-indigo-500',
  }
  return map[v]
})
</script>

<template>
  <span class="inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset" :class="classes">
    <span v-if="dot" class="h-1.5 w-1.5 rounded-full" :class="dotColor" />
    <slot />
  </span>
</template>
