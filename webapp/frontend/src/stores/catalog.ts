import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/lib/api'
import type { AppConfig, PatientListing } from '@/types'

export const useCatalogStore = defineStore('catalog', () => {
  const config = ref<AppConfig | null>(null)
  const patients = ref<PatientListing[]>([])
  const error = ref<string | null>(null)

  async function load() {
    try {
      ;[config.value, patients.value] = await Promise.all([api.config(), api.patients()])
      error.value = null
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  return { config, patients, error, load }
})
