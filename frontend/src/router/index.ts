import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('../components/layout/AppShell.vue'),
    children: [
      { path: '', name: 'dashboard', component: () => import('../views/DashboardView.vue') },
      { path: 'apps', name: 'apps', component: () => import('../views/apps/AppsListView.vue') },
      { path: 'spokes', name: 'spokes', component: () => import('../views/spokes/SpokesView.vue') },
      { path: 'models', name: 'models', component: () => import('../views/models/ModelsView.vue') },
      { path: 'routes', name: 'routes', component: () => import('../views/routes/RoutesView.vue') },
      { path: 'quotas', name: 'quotas', component: () => import('../views/quotas/QuotasView.vue') },
      { path: 'logs', name: 'logs', component: () => import('../views/logs/LogsView.vue') },
      { path: 'audit', name: 'audit', component: () => import('../views/audit/AuditView.vue') },
      { path: 'settings', name: 'settings', component: () => import('../views/settings/SettingsView.vue') },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

const router = createRouter({
  history: createWebHistory('/admin/'),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  auth.hydrate()
  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: 'login', query: { next: to.fullPath } }
  }
  if (to.name === 'login' && auth.isAuthenticated) {
    return { name: 'dashboard' }
  }
})

export default router
