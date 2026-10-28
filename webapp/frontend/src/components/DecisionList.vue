<script setup lang="ts">
import { DECISIONS } from '@/components/flow/palette'
import ScoreMeter from '@/components/flow/ScoreMeter.vue'
import type { TrialDecision } from '@/types'

defineProps<{ decisions: TrialDecision[]; cutoff: number }>()
const selected = defineModel<string | null>('selected', { default: null })
</script>

<template>
  <div class="divide-y">
    <button
      v-for="d in decisions"
      :key="d.trial_id"
      class="grid w-full grid-cols-[9.5rem_1fr_11rem] items-center gap-3 px-3 py-2 text-left text-sm hover:bg-muted/60"
      :class="selected === `trial:${d.trial_id}` ? 'bg-muted' : ''"
      @click="selected = `trial:${d.trial_id}`"
    >
      <span class="flex items-center gap-1.5 text-xs font-medium">
        <span class="inline-flex size-4 items-center justify-center rounded-full text-[10px] text-white" :style="{ background: DECISIONS[d.decision].color }">{{ DECISIONS[d.decision].icon }}</span>
        {{ DECISIONS[d.decision].label }}
      </span>
      <span class="min-w-0">
        <span class="block text-xs text-muted-foreground">#{{ d.rank }} · {{ d.trial_id }} · space {{ d.clinical_space_number }}</span>
        <span class="block truncate">{{ d.trial_title }}</span>
      </span>
      <ScoreMeter :value="d.match_quality_score" :cutoff="cutoff" />
    </button>
  </div>
</template>
