<script setup lang="ts">
import { Inbox } from 'lucide-vue-next'
defineProps<{ title?: string; message?: string }>()
</script>

<template>
  <div class="flex flex-col items-center justify-center text-center py-12 text-slate-500 dark:text-slate-400">
    <div class="rounded-full bg-slate-100 dark:bg-slate-800 p-3 mb-3">
      <slot name="icon"><Inbox :size="22" /></slot>
    </div>
    <p class="text-sm font-medium text-slate-700 dark:text-slate-300">{{ title || 'Keine Daten' }}</p>
    <p v-if="message" class="text-xs mt-1 max-w-xs">{{ message }}</p>
    <div v-if="$slots.action" class="mt-4">
      <slot name="action" />
    </div>
  </div>
</template>
