<script setup lang="ts">
import { RouterLink } from 'vue-router'
import {
  LayoutDashboard, AppWindow, Server, Boxes, Route, Gauge,
  ScrollText, History, Settings, Satellite,
} from 'lucide-vue-next'

const items = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, exact: true },
  { to: '/apps', label: 'Apps', icon: AppWindow },
  { to: '/spokes', label: 'Spokes', icon: Server },
  { to: '/models', label: 'Modelle', icon: Boxes },
  { to: '/routes', label: 'Routing', icon: Route },
  { to: '/quotas', label: 'Quotas', icon: Gauge },
  { to: '/logs', label: 'Logs (live)', icon: ScrollText },
  { to: '/audit', label: 'Audit', icon: History },
  { to: '/settings', label: 'Einstellungen', icon: Settings },
]
</script>

<template>
  <aside
    class="hidden md:flex w-[264px] shrink-0 flex-col border-r border-slate-200/70 dark:border-slate-800/70"
    style="background: var(--sidebar-bg)"
  >
    <div class="px-5 pt-5 pb-4 border-b border-slate-200/70 dark:border-slate-800/70">
      <RouterLink to="/" class="flex items-center gap-2.5">
        <div class="grid place-items-center h-9 w-9 rounded-lg bg-indigo-600 text-white shadow-sm">
          <Satellite :size="18" />
        </div>
        <div>
          <p class="font-semibold tracking-tight text-slate-900 dark:text-slate-100 leading-none">LLM-Router</p>
          <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">Admin-Konsole</p>
        </div>
      </RouterLink>
    </div>

    <nav class="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
      <RouterLink
        v-for="item in items"
        :key="item.to"
        :to="item.to"
        :exact-active-class="item.exact ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300' : ''"
        active-class="bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300"
        class="flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800/60 transition-colors"
      >
        <component :is="item.icon" :size="16" />
        <span>{{ item.label }}</span>
      </RouterLink>
    </nav>

    <div class="px-5 py-3 border-t border-slate-200/70 dark:border-slate-800/70 text-xs text-slate-500 dark:text-slate-500">
      <p>v0.1.0 · Hub für alle LLM-Calls</p>
    </div>
  </aside>
</template>
