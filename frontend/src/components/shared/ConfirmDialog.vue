<script setup lang="ts">
import Modal from './Modal.vue'
import { AlertTriangle } from 'lucide-vue-next'

defineProps<{
  open: boolean
  title?: string
  message?: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
}>()
const emit = defineEmits<{ confirm: []; cancel: [] }>()
</script>

<template>
  <Modal :open="open" :title="title || 'Bestätigung erforderlich'" @close="emit('cancel')">
    <div class="flex gap-3">
      <div class="shrink-0 rounded-full p-2" :class="danger ? 'bg-red-100 dark:bg-red-900/40' : 'bg-amber-100 dark:bg-amber-900/40'">
        <AlertTriangle :size="20" :class="danger ? 'text-red-600 dark:text-red-300' : 'text-amber-600 dark:text-amber-300'" />
      </div>
      <p class="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">{{ message }}</p>
    </div>
    <template #footer>
      <button
        class="rounded-md px-3 py-1.5 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
        @click="emit('cancel')"
      >{{ cancelText || 'Abbrechen' }}</button>
      <button
        class="rounded-md px-3 py-1.5 text-sm font-semibold text-white"
        :class="danger ? 'bg-red-600 hover:bg-red-700' : 'bg-indigo-600 hover:bg-indigo-700'"
        @click="emit('confirm')"
      >{{ confirmText || 'Bestätigen' }}</button>
    </template>
  </Modal>
</template>
