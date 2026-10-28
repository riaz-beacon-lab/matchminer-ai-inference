import { useIntervalFn } from '@vueuse/core'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api } from '@/lib/api'
import type { Run, RunOptions } from '@/types'

export const useRunStore = defineStore('run', () => {
  const run = ref<Run | null>(null)
  const error = ref<string | null>(null)
  const runs = ref<Run[]>([])

  const finished = computed(() => run.value?.status === 'done' || run.value?.status === 'error')

  async function refresh() {
    if (!run.value) return
    try {
      run.value = await api.run(run.value.id)
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    }
    if (finished.value) poller.pause()
  }

  const poller = useIntervalFn(refresh, 2000, { immediate: false })

  async function load(id: string) {
    poller.pause()
    error.value = null
    try {
      run.value = await api.run(id)
    } catch (e) {
      run.value = null
      error.value = (e as Error).message
      return
    }
    if (!finished.value) poller.resume()
  }

  async function start(mrn: string, options: Partial<RunOptions>) {
    const created = await api.startRun(mrn, options)
    await load(created.id)
    return created.id
  }

  async function loadRuns() {
    runs.value = await api.runs()
  }

  return { run, runs, error, finished, load, start, loadRuns }
})
