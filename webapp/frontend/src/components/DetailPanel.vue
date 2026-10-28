<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { CATEGORY_LABEL, DECISIONS } from '@/components/flow/palette'
import ScoreMeter from '@/components/flow/ScoreMeter.vue'
import { Badge } from '@/components/ui/badge'
import type { Decision, Note, RunResult } from '@/types'

const props = defineProps<{ result: RunResult; cutoff: number }>()
const selected = defineModel<string | null>('selected', { default: null })

const kind = computed(() => selected.value?.split(':')[0] ?? null)
const key = computed(() => selected.value?.split(':').slice(1).join(':') ?? '')

const notes = computed(() => props.result.notes ?? [])
const noteById = computed(() => new Map(notes.value.map((n) => [n.note_id, n])))
const openNote = ref<Note | null>(null)
watch(selected, () => (openNote.value = null))

const note = computed(() => (kind.value === 'note' ? noteById.value.get(key.value) : undefined))
const groupNotes = computed(() =>
  kind.value === 'notegrp' ? notes.value.filter((n) => `${n.note_date.slice(0, 4)} · ${n.event_type}` === key.value) : [],
)
const event = computed(() => (kind.value === 'event' ? props.result.journey?.events.find((e) => e.id === key.value) : undefined))
const trial = computed(() => (kind.value === 'trial' ? props.result.decisions?.find((d) => d.trial_id === key.value) : undefined))
const decisionTrials = computed(() =>
  kind.value === 'decision' ? (props.result.decisions ?? []).filter((d) => d.decision === key.value) : [],
)
const summary = computed(() => props.result.summary)
const fields = computed(() => summary.value?.parsed.fields ?? {})
const date = (iso: string) => iso.slice(0, 10)
</script>

<template>
  <div class="space-y-3 text-sm">
    <!-- Note -->
    <template v-if="note">
      <div class="text-xs text-muted-foreground">{{ note.note_id }} · {{ date(note.note_date) }} · {{ note.event_type }}</div>
      <pre class="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 font-sans text-xs leading-relaxed">{{ note.note_text }}</pre>
    </template>

    <!-- Note group / cited notes -->
    <template v-else-if="kind === 'notegrp' || event">
      <template v-if="event">
        <div class="text-xs text-muted-foreground">{{ CATEGORY_LABEL[event.category] }} · {{ event.date }}</div>
        <div class="font-medium">{{ event.title }}</div>
        <p class="text-muted-foreground">{{ event.detail }}</p>
        <div class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Source notes</div>
      </template>
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="n in event ? event.note_ids.map((id) => noteById.get(id)).filter(Boolean) : groupNotes"
          :key="n!.note_id"
          class="rounded-md border px-2 py-1 text-xs hover:bg-muted"
          :class="openNote?.note_id === n!.note_id ? 'bg-muted' : ''"
          @click="openNote = n!"
        >
          {{ n!.note_id }} · {{ date(n!.note_date) }} · {{ n!.event_type }}
        </button>
      </div>
      <pre v-if="openNote" class="max-h-[50vh] overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 font-sans text-xs leading-relaxed">{{ openNote.note_text }}</pre>
    </template>

    <!-- Trial -->
    <template v-else-if="trial">
      <div class="flex items-center gap-2">
        <Badge variant="outline" :style="{ borderColor: DECISIONS[trial.decision].color }">
          {{ DECISIONS[trial.decision].icon }} {{ DECISIONS[trial.decision].label }}
        </Badge>
        <a class="text-xs underline" :href="`https://clinicaltrials.gov/study/${trial.trial_id}`" target="_blank" rel="noopener">{{ trial.trial_id }}</a>
      </div>
      <div class="font-medium">{{ trial.trial_title }}</div>
      <ul class="list-disc space-y-0.5 pl-5 text-muted-foreground">
        <li v-for="r in trial.decision_reasons" :key="r">{{ r }}</li>
      </ul>
      <div class="space-y-1.5">
        <ScoreMeter :value="trial.match_quality_score" :cutoff="cutoff" label="TrialChecker" />
        <ScoreMeter :value="trial.similarity_score" label="Similarity" />
      </div>
      <div>
        <div class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Best-matching clinical space (#{{ trial.clinical_space_number }})</div>
        <p class="mt-1">{{ trial.clinical_space_summary }}</p>
      </div>
      <div>
        <div class="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          General exclusion criteria · {{ trial.exclusion_criteria_pass === false ? 'possible exclusion' : 'passes' }}
        </div>
        <p class="mt-1 text-muted-foreground">{{ trial.general_exclusion_criteria }}</p>
      </div>
      <div v-if="trial.llm_match_quality_answer_text">
        <div class="text-xs font-medium uppercase tracking-wide text-muted-foreground">LLM review · score {{ trial.llm_match_quality_score }}/5</div>
        <pre class="mt-1 max-h-72 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 font-sans text-xs">{{ trial.llm_match_quality_answer_text }}</pre>
      </div>
      <div v-if="trial.llm_exclusion_criteria_answer_text">
        <div class="text-xs font-medium uppercase tracking-wide text-muted-foreground">LLM exclusion review</div>
        <pre class="mt-1 max-h-72 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 font-sans text-xs">{{ trial.llm_exclusion_criteria_answer_text }}</pre>
      </div>
    </template>

    <!-- Decision bucket -->
    <template v-else-if="kind === 'decision'">
      <div class="font-medium">{{ DECISIONS[key as Decision].icon }} {{ DECISIONS[key as Decision].label }}</div>
      <button
        v-for="d in decisionTrials"
        :key="d.trial_id"
        class="block w-full rounded-md border p-2 text-left hover:bg-muted"
        @click="selected = `trial:${d.trial_id}`"
      >
        <div class="text-xs text-muted-foreground">#{{ d.rank }} · {{ d.trial_id }}</div>
        <div class="line-clamp-2">{{ d.trial_title }}</div>
      </button>
      <p v-if="!decisionTrials.length" class="text-muted-foreground">No trials.</p>
    </template>

    <!-- Summary facets / patient (default) -->
    <template v-else-if="summary">
      <div v-if="kind === 'facet' && key === 'Biomarkers'">
        <div class="mb-1 font-medium">Biomarkers</div>
        <div class="flex flex-wrap gap-1">
          <Badge v-for="b in summary.parsed.biomarkers" :key="b" variant="secondary" class="h-auto whitespace-normal">{{ b }}</Badge>
        </div>
      </div>
      <div v-else-if="kind === 'facet' && key === 'Treatment history'">
        <div class="mb-1 font-medium">Treatment history</div>
        <ol class="space-y-1.5 border-l pl-3">
          <li v-for="(t, i) in summary.parsed.treatment_history" :key="i">
            <div class="text-xs text-muted-foreground">{{ t.when }}</div>
            <div>{{ t.what }}</div>
          </li>
        </ol>
      </div>
      <div v-else-if="kind === 'facet' && key === 'Exclusion evidence'">
        <div class="mb-1 font-medium">Evidence for general exclusion criteria</div>
        <p class="whitespace-pre-wrap text-muted-foreground">{{ summary.general_exclusion_criteria_evidence }}</p>
      </div>
      <template v-else>
        <p v-if="!selected" class="text-xs text-muted-foreground">Click any node in the flow to trace it. Showing the patient summary.</p>
        <dl class="space-y-2">
          <template v-for="(value, name) in fields" :key="name">
            <div v-if="name !== 'Treatment history' && value">
              <dt class="text-xs font-medium uppercase tracking-wide text-muted-foreground">{{ name }}</dt>
              <dd>{{ value }}</dd>
            </div>
          </template>
        </dl>
      </template>
    </template>
  </div>
</template>
