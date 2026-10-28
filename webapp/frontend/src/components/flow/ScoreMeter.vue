<script setup lang="ts">
import { computed } from 'vue'

import { METER_FILL } from '@/components/flow/palette'

// 0-1 meter with an optional cutoff tick; the value is always printed.
const props = defineProps<{ value: number; cutoff?: number; label?: string }>()
const pct = (v: number) => `${Math.max(0, Math.min(1, v)) * 100}%`
const fill = computed(() => pct(props.value))
</script>

<template>
  <div class="flex items-center gap-2" :title="cutoff != null ? `cutoff ${cutoff}` : undefined">
    <span v-if="label" class="text-[10px] text-muted-foreground">{{ label }}</span>
    <div class="relative h-1.5 flex-1 rounded-full bg-muted">
      <div class="h-full rounded-full" :style="{ width: fill, background: METER_FILL }" />
      <div v-if="cutoff != null" class="absolute -top-0.5 h-2.5 w-0.5 bg-foreground/70" :style="{ left: pct(cutoff) }" />
    </div>
    <span class="w-8 text-right text-[11px] tabular-nums text-foreground">{{ value.toFixed(2) }}</span>
  </div>
</template>
