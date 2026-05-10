import { defineStore } from 'pinia'
import { ref, watchEffect } from 'vue'

const STORAGE_KEY = 'llm_router_theme'

export const useThemeStore = defineStore('theme', () => {
  const initial = (typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_KEY)) ||
    (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
  const theme = ref<'light' | 'dark'>(initial as 'light' | 'dark')

  watchEffect(() => {
    if (typeof document === 'undefined') return
    if (theme.value === 'dark') {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
    localStorage.setItem(STORAGE_KEY, theme.value)
  })

  function toggle() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }

  return { theme, toggle }
})
