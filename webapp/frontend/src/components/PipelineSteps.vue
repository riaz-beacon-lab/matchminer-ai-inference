<script setup lang="ts">
import type { RunStep } from '@/types'

defineProps<{ steps: RunStep[] }>()

const ICON: Record<RunStep['status'], string> = {
  pending: '○',
  running: '◐',
  done: '✓',
  error: '✕',
  skipped: '–',
}
const TONE: Record<RunStep['status'], string> = {
  pending: 'text-muted-foreground',
  running: 'text-foreground animate-pulse',
  done: 'text-foreground',
  error: 'text-destructive',
  skipped: 'text-muted-foreground line-through',
}
</script>

<template>
  <ol class="flex flex-wrap items-center gap-x-1 gap-y-2 text-xs">
    <li v-for="(s, i) in steps" :key="s.key" class="flex items-center gap-1">
      <span class="flex items-center gap-1.5 rounded-full border px-2.5 py-1" :class="TONE[s.status]" :title="s.detail">
        <span aria-hidden="true">{{ ICON[s.status] }}</span>
        <span>{{ s.label }}</span>
        <span v-if="s.seconds != null && s.status === 'done'" class="tabular-nums text-muted-foreground">{{ s.seconds.toFixed(1) }}s</span>
        <span v-if="s.detail" class="text-muted-foreground">· {{ s.detail }}</span>
      </span>
      <span v-if="i < steps.length - 1" class="text-muted-foreground" aria-hidden="true">→</span>
    </li>
  </ol>
</template>
