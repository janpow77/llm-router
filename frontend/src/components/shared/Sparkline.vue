<script setup lang="ts">
import { computed } from 'vue'
import { sparklinePath } from '../../utils/chart'

const props = defineProps<{
  values: number[]
  width?: number
  height?: number
  color?: string
  fill?: boolean
}>()

const w = computed(() => props.width ?? 120)
const h = computed(() => props.height ?? 30)
const stroke = computed(() => props.color || 'currentColor')

const path = computed(() => sparklinePath(props.values, w.value, h.value))

const areaPath = computed(() => {
  if (!props.values.length) return ''
  const linePath = sparklinePath(props.values, w.value, h.value)
  return `${linePath} L${w.value - 2},${h.value - 2} L2,${h.value - 2} Z`
})
</script>

<template>
  <svg :width="w" :height="h" :viewBox="`0 0 ${w} ${h}`" class="overflow-visible">
    <path
      v-if="fill"
      :d="areaPath"
      :fill="stroke"
      fill-opacity="0.12"
      stroke="none"
    />
    <path :d="path" :stroke="stroke" stroke-width="1.5" fill="none" stroke-linejoin="round" stroke-linecap="round" />
  </svg>
</template>
