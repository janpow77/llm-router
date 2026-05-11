<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView } from 'vue-router'
import GlobalConfirmDialog from './components/shared/GlobalConfirmDialog.vue'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()

onMounted(() => {
  auth.hydrate()
})
</script>

<template>
  <RouterView />
  <!-- Globaler Bestaetigungsdialog: jede mutierende Aktion ruft useConfirmStore().ask(...) -->
  <GlobalConfirmDialog />
</template>
