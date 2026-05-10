<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useThemeStore } from '../../stores/theme'
import { useAuthStore } from '../../stores/auth'
import { useRouter } from 'vue-router'
import { Sun, Moon, LogOut, Activity } from 'lucide-vue-next'
import { getHealth } from '../../api/dashboard'
import Badge from '../shared/Badge.vue'
import type { HealthInfo } from '../../api/types'

const theme = useThemeStore()
const auth = useAuthStore()
const router = useRouter()

const health = ref<HealthInfo | null>(null)

onMounted(async () => {
  try { health.value = await getHealth() } catch { /* ignore */ }
})

async function doLogout() {
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <header
    class="sticky top-0 z-30 flex items-center justify-between gap-4 px-6 py-3 border-b border-slate-200/70 dark:border-slate-800/70 backdrop-blur-md"
    style="background: var(--sidebar-bg)"
  >
    <div class="flex items-center gap-3">
      <div class="md:hidden grid place-items-center h-9 w-9 rounded-lg bg-indigo-600 text-white">
        <Activity :size="16" />
      </div>
      <div>
        <h1 class="text-sm font-semibold text-slate-900 dark:text-slate-100">{{ $route.name }}</h1>
        <p v-if="health" class="text-xs text-slate-500 dark:text-slate-400 leading-tight">
          Router v{{ health.version }} · {{ health.spokes_health.length }} Spoke(s)
        </p>
      </div>
    </div>

    <div class="flex items-center gap-2">
      <Badge v-if="health" :variant="health.status === 'ok' ? 'green' : health.status === 'degraded' ? 'amber' : 'red'" dot>
        {{ health.status === 'ok' ? 'Online' : health.status === 'degraded' ? 'Degraded' : 'Offline' }}
      </Badge>

      <button
        class="grid place-items-center h-9 w-9 rounded-md text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
        :title="theme.theme === 'dark' ? 'Light Mode' : 'Dark Mode'"
        @click="theme.toggle"
      >
        <Sun v-if="theme.theme === 'dark'" :size="16" />
        <Moon v-else :size="16" />
      </button>

      <button
        class="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
        title="Abmelden"
        @click="doLogout"
      >
        <LogOut :size="14" />
        <span class="hidden sm:inline">Abmelden</span>
      </button>
    </div>
  </header>
</template>
