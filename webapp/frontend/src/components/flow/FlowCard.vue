<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import { computed } from 'vue'

import ScoreMeter from '@/components/flow/ScoreMeter.vue'

export interface FlowCardData {
  eyebrow: string
  title: string
  subtitle?: string
  color: string
  icon?: string
  badge?: string
  score?: number
  cutoff?: number
  scoreLabel?: string
  width?: number
  dimmed?: boolean
  inputs?: boolean
  outputs?: boolean
}

const props = defineProps<{ data: FlowCardData; selected?: boolean }>()
const width = computed(() => `${props.data.width ?? 240}px`)
</script>

<template>
  <div
    class="rounded-lg border bg-card text-left shadow-sm transition-opacity"
    :class="[selected ? 'ring-2 ring-foreground/70' : '', data.dimmed ? 'opacity-35' : '']"
    :style="{ width, borderLeft: `4px solid ${data.color}` }"
  >
    <Handle v-if="data.inputs !== false" type="target" :position="Position.Left" />
    <div class="px-3 py-2">
      <div class="flex items-center justify-between gap-2 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        <span class="flex items-center gap-1">
          <span v-if="data.icon" class="inline-flex size-3.5 items-center justify-center rounded-full text-[9px] text-white" :style="{ background: data.color }">{{ data.icon }}</span>
          {{ data.eyebrow }}
        </span>
        <span v-if="data.badge" class="normal-case tracking-normal text-foreground/80">{{ data.badge }}</span>
      </div>
      <div class="mt-0.5 line-clamp-2 text-sm font-medium leading-snug text-foreground">{{ data.title }}</div>
      <div v-if="data.subtitle" class="mt-0.5 line-clamp-3 text-xs leading-snug text-muted-foreground">{{ data.subtitle }}</div>
      <ScoreMeter v-if="data.score != null" class="mt-1.5" :value="data.score" :cutoff="data.cutoff" :label="data.scoreLabel" />
    </div>
    <Handle v-if="data.outputs !== false" type="source" :position="Position.Right" />
  </div>
</template>
