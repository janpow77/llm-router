// Globaler Confirm-Store: jede mutierende UI-Aktion fragt VOR dem API-Call
// "wirklich anwenden?". Aufruf via:
//
//   const confirm = useConfirmStore()
//   const ok = await confirm.ask({ title: 'App löschen?', message: '...', danger: true })
//   if (!ok) return
//   await deleteApp(id)
//
// Eingehaengt wird der Dialog ueber <GlobalConfirmDialog /> im Layout.

import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface ConfirmRequest {
  title: string
  message?: string
  details?: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
}

interface PendingPrompt extends ConfirmRequest {
  resolve: (ok: boolean) => void
}

export const useConfirmStore = defineStore('confirm', () => {
  const pending = ref<PendingPrompt | null>(null)
  const open = ref(false)

  function ask(req: ConfirmRequest): Promise<boolean> {
    return new Promise(resolve => {
      pending.value = { ...req, resolve }
      open.value = true
    })
  }

  function resolve(ok: boolean) {
    if (pending.value) {
      pending.value.resolve(ok)
    }
    pending.value = null
    open.value = false
  }

  function confirm() {
    resolve(true)
  }

  function cancel() {
    resolve(false)
  }

  return { pending, open, ask, confirm, cancel }
})
