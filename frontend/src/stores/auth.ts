import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as authApi from '../api/auth'
import { setToken, getToken } from '../api/client'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(getToken())
  const expiresAt = ref<string | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const isAuthenticated = computed(() => !!token.value)

  function hydrate() {
    token.value = getToken()
  }

  async function login(password: string): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      const result = await authApi.login(password)
      token.value = result.token
      expiresAt.value = result.expires_at
      setToken(result.token)
      return true
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Login fehlgeschlagen'
      return false
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    try { await authApi.logout() } catch { /* ignore */ }
    token.value = null
    expiresAt.value = null
    setToken(null)
  }

  return { token, expiresAt, loading, error, isAuthenticated, login, logout, hydrate }
})
