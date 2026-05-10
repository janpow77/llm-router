<script setup lang="ts">
defineProps<{ size?: number }>()
</script>

<template>
  <svg
    class="animate-spin text-indigo-500"
    :width="size || 18"
    :height="size || 18"
    viewBox="0 0 24 24"
    fill="none"
  >
    <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-opacity="0.2" stroke-width="3" />
    <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
  </svg>
</template>
