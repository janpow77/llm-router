// Vitest setup — globale Test-Konfiguration
import { vi } from 'vitest'

// Mocks aktivieren in Tests
;(import.meta.env as Record<string, string>).VITE_USE_MOCKS = 'true'

// LocalStorage-Polyfill (happy-dom hat das schon, aber zur Sicherheit)
if (typeof localStorage === 'undefined') {
  const store = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', {
    value: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => store.set(k, v),
      removeItem: (k: string) => store.delete(k),
      clear: () => store.clear(),
    },
  })
}

// matchMedia-Polyfill für Theme
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}
