<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import DecisionList from '@/components/DecisionList.vue'
import DetailPanel from '@/components/DetailPanel.vue'
import FlowCanvas from '@/components/flow/FlowCanvas.vue'
import { buildDecisionGraph, buildJourneyGraph } from '@/components/flow/graphs'
import { DECISIONS, GROUPS } from '@/components/flow/palette'
import PipelineSteps from '@/components/PipelineSteps.vue'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useRunStore } from '@/stores/run'

const props = defineProps<{ id: string }>()
const store = useRunStore()
watch(() => props.id, (id) => store.load(id), { immediate: true })

const run = computed(() => store.run)
const result = computed(() => run.value?.result ?? {})
const cutoff = computed(() => result.value.score_cutoff ?? 0.2)
const selected = ref<string | null>(null)
const tab = ref('flow')

const decisionGraph = computed(() => buildDecisionGraph(result.value, cutoff.value))
const journeyGraph = computed(() => buildJourneyGraph(result.value.journey?.events ?? []))
const counts = computed(() =>
  (result.value.decisions ?? []).reduce<Record<string, number>>((a, d) => ({ ...a, [d.decision]: (a[d.decision] ?? 0) + 1 }), {}),
)
</script>

<template>
  <div class="flex h-[calc(100vh-3.5rem)] flex-col gap-3 p-4">
    <p v-if="store.error && !run" class="text-destructive">{{ store.error }}</p>
    <template v-if="run">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div class="text-xs text-muted-foreground">MRN</div>
          <div class="font-mono text-lg font-semibold">{{ run.mrn }}</div>
        </div>
        <div v-if="result.journey?.headline" class="max-w-2xl flex-1 text-sm text-muted-foreground">{{ result.journey.headline }}</div>
        <div class="flex gap-4 text-sm">
          <span v-for="(meta, key) in DECISIONS" :key="key" class="flex items-center gap-1.5">
            <span class="inline-flex size-4 items-center justify-center rounded-full text-[10px] text-white" :style="{ background: meta.color }">{{ meta.icon }}</span>
            <span class="tabular-nums font-semibold">{{ counts[key] ?? 0 }}</span> {{ meta.label }}
          </span>
        </div>
      </div>
      <PipelineSteps :steps="run.steps" />
      <p v-if="run.error" class="text-sm text-destructive">{{ run.error }}</p>

      <div class="grid min-h-0 flex-1 gap-3 lg:grid-cols-[1fr_24rem]">
        <Tabs v-model="tab" class="flex min-h-0 flex-col">
          <TabsList>
            <TabsTrigger value="flow">Decision flow</TabsTrigger>
            <TabsTrigger value="journey">Patient journey</TabsTrigger>
            <TabsTrigger value="trials">Trials</TabsTrigger>
          </TabsList>
          <TabsContent value="flow" class="min-h-0 flex-1 rounded-lg border bg-card">
            <div class="flex gap-4 border-b px-3 py-1.5 text-[11px] text-muted-foreground">
              <span>Notes → key events → summary → patient → candidate trials → decision</span>
              <span v-for="g in GROUPS" :key="g.label" class="flex items-center gap-1">
                <span class="size-2.5 rounded-sm" :style="{ background: g.color }" />{{ g.label }}
              </span>
            </div>
            <FlowCanvas id="decision-flow" v-model:selected="selected" :nodes="decisionGraph.nodes" :edges="decisionGraph.edges" class="h-[calc(100%-2rem)]" />
          </TabsContent>
          <TabsContent value="journey" class="min-h-0 flex-1 rounded-lg border bg-card">
            <FlowCanvas v-if="result.journey?.events.length" id="journey-flow" v-model:selected="selected" :nodes="journeyGraph.nodes" :edges="journeyGraph.edges" />
            <p v-else class="p-4 text-sm text-muted-foreground">No key events yet.</p>
          </TabsContent>
          <TabsContent value="trials" class="min-h-0 flex-1 overflow-auto rounded-lg border bg-card">
            <DecisionList v-model:selected="selected" :decisions="result.decisions ?? []" :cutoff="cutoff" />
          </TabsContent>
        </Tabs>
        <aside class="min-h-0 overflow-auto rounded-lg border bg-card p-4">
          <DetailPanel v-model:selected="selected" :result="result" :cutoff="cutoff" />
          <p v-if="!result.summary" class="text-sm text-muted-foreground">Waiting for the patient summary…</p>
        </aside>
      </div>
      <p class="text-[11px] text-muted-foreground">
        Model-generated matching to support trial screening; it does not replace clinical review of full eligibility criteria.
      </p>
    </template>
  </div>
</template>
