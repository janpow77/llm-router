<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { Satellite, KeyRound } from 'lucide-vue-next'
import Spinner from '../components/shared/Spinner.vue'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const password = ref('')

async function submit() {
  const ok = await auth.login(password.value)
  if (ok) {
    const next = (route.query.next as string) || '/'
    router.push(next)
  }
}
</script>

<template>
  <div class="min-h-screen grid place-items-center px-4" style="background: var(--app-bg)">
    <div class="w-full max-w-sm">
      <div class="text-center mb-8">
        <div class="inline-grid place-items-center h-12 w-12 rounded-2xl bg-indigo-600 text-white shadow-lg mb-3">
          <Satellite :size="22" />
        </div>
        <h1 class="text-xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">LLM-Router Admin</h1>
        <p class="text-sm text-slate-500 dark:text-slate-400 mt-1">Zentrale Steuerkonsole für alle LLM-Anfragen.</p>
      </div>

      <form
        class="rounded-xl border bg-white/80 dark:bg-slate-950/60 border-slate-200/70 dark:border-slate-800/70 backdrop-blur-md p-6 shadow-sm"
        @submit.prevent="submit"
      >
        <label class="block">
          <span class="block text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-1.5">Admin-Passwort</span>
          <div class="relative">
            <KeyRound class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" :size="16" />
            <input
              v-model="password"
              type="password"
              autofocus
              required
              autocomplete="current-password"
              placeholder="••••••••"
              class="w-full pl-9 pr-3 py-2.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
          </div>
        </label>

        <p v-if="auth.error" class="mt-3 text-sm text-red-600 dark:text-red-400">{{ auth.error }}</p>

        <button
          type="submit"
          :disabled="auth.loading"
          class="mt-5 w-full inline-flex items-center justify-center gap-2 rounded-md bg-indigo-600 hover:bg-indigo-700 text-white py-2.5 text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Spinner v-if="auth.loading" :size="16" />
          <span>{{ auth.loading ? 'Authentifiziere...' : 'Anmelden' }}</span>
        </button>

        <p class="mt-4 text-xs text-center text-slate-400 dark:text-slate-500">
          Mock-Modus: Passwort <code class="font-mono">admin</code>
        </p>
      </form>
    </div>
  </div>
</template>
