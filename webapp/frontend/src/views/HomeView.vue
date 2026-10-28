<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { useCatalogStore } from '@/stores/catalog'
import { useRunStore } from '@/stores/run'

const router = useRouter()
const catalog = useCatalogStore()
const runStore = useRunStore()

const mrn = ref('')
const topK = ref(20)
const llmReview = ref(false)
const includeJourney = ref(true)
const starting = ref(false)
const error = ref<string | null>(null)

onMounted(() => {
  catalog.load()
  runStore.loadRuns()
})

async function start() {
  if (!mrn.value.trim()) return
  starting.value = true
  error.value = null
  try {
    const id = await runStore.start(mrn.value.trim(), {
      top_k: topK.value,
      llm_review: llmReview.value,
      include_journey: includeJourney.value,
    })
    router.push({ name: 'run', params: { id } })
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    starting.value = false
  }
}

const when = (t: number) => new Date(t * 1000).toLocaleString()
</script>

<template>
  <div class="mx-auto grid max-w-5xl gap-6 p-6 md:grid-cols-[1fr_20rem]">
    <Card>
      <CardHeader>
        <CardTitle>Match a patient to clinical trials</CardTitle>
        <CardDescription>
          Notes → patient summary → TrialSpace retrieval → TrialChecker → BoilerplateChecker → decision.
        </CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <form class="flex gap-2" @submit.prevent="start">
          <Input v-model="mrn" placeholder="MRN" class="font-mono" autofocus />
          <Button type="submit" :disabled="starting || !mrn.trim()">{{ starting ? 'Starting…' : 'Run matching' }}</Button>
        </form>
        <div class="flex flex-wrap items-center gap-x-6 gap-y-3 text-sm">
          <label class="flex items-center gap-2">
            Top-k spaces
            <Input v-model.number="topK" type="number" min="1" max="100" class="h-8 w-20" />
          </label>
          <label class="flex items-center gap-2"><Switch v-model="includeJourney" /> Key-event journey</label>
          <label class="flex items-center gap-2"><Switch v-model="llmReview" /> LLM review (local Gemma)</label>
        </div>
        <p v-if="error" class="text-sm text-destructive">{{ error }}</p>

        <div v-if="catalog.config" class="rounded-md bg-muted/60 p-3 text-xs text-muted-foreground">
          <div>Summaries: <b>{{ catalog.config.models.patient_summary }}</b> (Apigee{{ catalog.config.apigee_configured ? '' : ' — not configured' }})</div>
          <div>Embedding / checkers: {{ catalog.config.models.embedding }}, {{ catalog.config.models.match_quality }}, {{ catalog.config.models.exclusion }}</div>
          <div>LLM review: {{ catalog.config.models.llm_review }} @ {{ catalog.config.llm_review_server.join(', ') }}</div>
          <div>Notes: {{ catalog.config.notes_sources.join(', ') }}</div>
        </div>
        <p v-if="catalog.error" class="text-sm text-destructive">Backend unavailable: {{ catalog.error }}</p>
      </CardContent>
    </Card>

    <div class="space-y-6">
      <Card>
        <CardHeader><CardTitle class="text-base">Patients in note sources</CardTitle></CardHeader>
        <CardContent class="max-h-72 space-y-1 overflow-auto">
          <button
            v-for="p in catalog.patients"
            :key="p.mrn"
            class="flex w-full justify-between rounded px-2 py-1 text-left text-sm hover:bg-muted"
            @click="mrn = p.mrn"
          >
            <span class="font-mono">{{ p.mrn }}</span>
            <span class="text-xs text-muted-foreground">{{ p.n_notes }} notes</span>
          </button>
        </CardContent>
      </Card>
      <Card v-if="runStore.runs.length">
        <CardHeader><CardTitle class="text-base">Recent runs</CardTitle></CardHeader>
        <CardContent class="space-y-1">
          <RouterLink
            v-for="r in runStore.runs"
            :key="r.id"
            :to="{ name: 'run', params: { id: r.id } }"
            class="flex justify-between rounded px-2 py-1 text-sm hover:bg-muted"
          >
            <span class="font-mono">{{ r.mrn }}</span>
            <span class="text-xs text-muted-foreground">{{ r.status }} · {{ when(r.created_at) }}</span>
          </RouterLink>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
