<script setup lang="ts">
import { onMounted, onBeforeUnmount } from 'vue'
import { X } from 'lucide-vue-next'

const props = defineProps<{ open: boolean; title?: string; width?: string }>()
const emit = defineEmits<{ close: [] }>()

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open) emit('close')
}
onMounted(() => document.addEventListener('keydown', onKey))
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <Transition>
      <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-slate-900/60 backdrop-blur-sm" @click="emit('close')" />
        <div
          class="relative w-full rounded-xl border bg-white dark:bg-slate-950 border-slate-200 dark:border-slate-800 shadow-2xl animate-fade-in"
          :style="{ maxWidth: width || '32rem' }"
        >
          <header class="flex items-center justify-between gap-4 px-5 py-4 border-b border-slate-200 dark:border-slate-800">
            <h3 class="text-base font-semibold text-slate-900 dark:text-slate-100">{{ title }}</h3>
            <button
              class="rounded-md p-1 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
              @click="emit('close')"
            >
              <X :size="18" />
            </button>
          </header>
          <div class="p-5 max-h-[70vh] overflow-y-auto">
            <slot />
          </div>
          <footer v-if="$slots.footer" class="flex items-center justify-end gap-2 px-5 py-3 border-t border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-900/60 rounded-b-xl">
            <slot name="footer" />
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
