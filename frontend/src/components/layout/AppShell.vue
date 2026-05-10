<script setup lang="ts">
import { RouterView } from 'vue-router'
import Sidebar from './Sidebar.vue'
import TopBar from './TopBar.vue'
import Toasts from '../shared/Toasts.vue'
</script>

<template>
  <div class="flex min-h-screen" style="background: var(--app-bg)">
    <Sidebar />
    <div class="flex-1 flex flex-col min-w-0">
      <TopBar />
      <main class="flex-1 px-6 py-6 overflow-x-hidden">
        <RouterView v-slot="{ Component }">
          <Transition mode="out-in">
            <component :is="Component" />
          </Transition>
        </RouterView>
      </main>
    </div>
    <Toasts />
  </div>
</template>

<style scoped>
.v-enter-active, .v-leave-active {
  transition: opacity 0.15s ease;
}
.v-enter-from, .v-leave-to {
  opacity: 0;
}
</style>
