<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ value: number; max?: number; label?: string }>()

const pct = computed(() => {
  const max = props.max ?? 100
  if (!max) return 0
  return Math.min(100, Math.max(0, (props.value / max) * 100))
})

const color = computed(() => {
  if (pct.value >= 90) return 'bg-red-500'
  if (pct.value >= 70) return 'bg-amber-500'
  return 'bg-indigo-500'
})
</script>

<template>
  <div>
    <div v-if="label" class="flex items-center justify-between text-xs text-slate-600 dark:text-slate-400 mb-1">
      <span>{{ label }}</span>
      <span class="tabular-nums">{{ Math.round(pct) }}%</span>
    </div>
    <div class="h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
      <div class="h-full transition-[width] duration-300 ease-out" :class="color" :style="{ width: pct + '%' }" />
    </div>
  </div>
</template>
