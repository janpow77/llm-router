<script setup lang="ts">
// Globaler Wrapper um ConfirmDialog. Liest aus dem confirm-Store. Wird im
// Layout (App.vue / AppShell.vue) einmalig eingehaengt.
import { storeToRefs } from 'pinia'
import { useConfirmStore } from '../../stores/confirm'
import ConfirmDialog from './ConfirmDialog.vue'

const store = useConfirmStore()
const { pending, open } = storeToRefs(store)
</script>

<template>
  <ConfirmDialog
    :open="open"
    :title="pending?.title"
    :message="pending?.message"
    :confirm-text="pending?.confirmText"
    :cancel-text="pending?.cancelText"
    :danger="pending?.danger"
    @confirm="store.confirm"
    @cancel="store.cancel"
  />
</template>
