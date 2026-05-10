<script setup lang="ts">
defineProps<{ title?: string; subtitle?: string; padded?: boolean }>()
</script>

<template>
  <section
    class="rounded-xl border bg-white/80 dark:bg-slate-950/60 border-slate-200/70 dark:border-slate-800/70 backdrop-blur-md shadow-sm"
  >
    <header v-if="title || $slots.actions" class="flex items-center justify-between gap-4 px-5 pt-4 pb-3 border-b border-slate-200/70 dark:border-slate-800/70">
      <div>
        <h2 v-if="title" class="text-sm font-semibold tracking-tight text-slate-900 dark:text-slate-100">{{ title }}</h2>
        <p v-if="subtitle" class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.actions" class="flex items-center gap-2">
        <slot name="actions" />
      </div>
    </header>
    <div :class="padded === false ? '' : 'p-5'">
      <slot />
    </div>
  </section>
</template>
