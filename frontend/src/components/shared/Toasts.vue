<script setup lang="ts">
import { useToastStore } from '../../stores/toast'
import { CheckCircle2, AlertCircle, Info, AlertTriangle, X } from 'lucide-vue-next'
import { computed } from 'vue'

const toasts = useToastStore()

const iconMap = computed(() => ({
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
  warning: AlertTriangle,
}))
const colorMap: Record<string, string> = {
  success: 'border-green-300 text-green-800 dark:border-green-600 dark:text-green-200 bg-green-50 dark:bg-green-900/40',
  error: 'border-red-300 text-red-800 dark:border-red-600 dark:text-red-200 bg-red-50 dark:bg-red-900/40',
  info: 'border-slate-300 text-slate-800 dark:border-slate-600 dark:text-slate-200 bg-slate-50 dark:bg-slate-900/40',
  warning: 'border-amber-300 text-amber-800 dark:border-amber-600 dark:text-amber-200 bg-amber-50 dark:bg-amber-900/40',
}
</script>

<template>
  <div class="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
    <div
      v-for="t in toasts.toasts"
      :key="t.id"
      class="pointer-events-auto flex items-start gap-2 rounded-lg border px-3 py-2 shadow-lg backdrop-blur-md text-sm w-72 animate-fade-in"
      :class="colorMap[t.type]"
    >
      <component :is="iconMap[t.type]" :size="18" class="shrink-0 mt-0.5" />
      <p class="flex-1 leading-snug">{{ t.message }}</p>
      <button class="opacity-60 hover:opacity-100" @click="toasts.dismiss(t.id)">
        <X :size="14" />
      </button>
    </div>
  </div>
</template>
