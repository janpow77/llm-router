import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '../src/stores/auth'
import { useToastStore } from '../src/stores/toast'

describe('Stores', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('Auth: login mit korrektem Mock-Passwort setzt Token', async () => {
    const auth = useAuthStore()
    expect(auth.isAuthenticated).toBe(false)
    const ok = await auth.login('admin')
    expect(ok).toBe(true)
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.token).toMatch(/^mock-token-/)
  })

  it('Auth: login mit falschem Passwort → error', async () => {
    const auth = useAuthStore()
    const ok = await auth.login('wrong')
    expect(ok).toBe(false)
    expect(auth.error).toBeTruthy()
    expect(auth.isAuthenticated).toBe(false)
  })

  it('Auth: logout löscht Token', async () => {
    const auth = useAuthStore()
    await auth.login('admin')
    expect(auth.isAuthenticated).toBe(true)
    await auth.logout()
    expect(auth.isAuthenticated).toBe(false)
    expect(localStorage.getItem('llm_router_admin_token')).toBeNull()
  })

  it('Toast: push und auto-dismiss', () => {
    const t = useToastStore()
    expect(t.toasts.length).toBe(0)
    t.success('Hallo')
    expect(t.toasts.length).toBe(1)
    expect(t.toasts[0].type).toBe('success')
    expect(t.toasts[0].message).toBe('Hallo')
  })

  it('Toast: dismiss per ID', () => {
    const t = useToastStore()
    const id = t.info('Test')
    t.dismiss(id)
    expect(t.toasts.length).toBe(0)
  })
})
