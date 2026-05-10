<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from './stores/auth'
import { RouterView } from 'vue-router'

const auth = useAuthStore()

onMounted(() => {
  auth.hydrate()
})
</script>

<template>
  <RouterView />
</template>
