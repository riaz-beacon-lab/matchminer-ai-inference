import axios, { AxiosError } from 'axios'

import type { AppConfig, Note, PatientListing, Run, RunOptions } from '@/types'

// Same origin in production (Flask serves dist/); Vite proxies /api in dev.
export const http = axios.create({ baseURL: '/api', timeout: 60_000 })

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: string }>) => {
    const detail = error.response?.data?.detail
    return Promise.reject(new Error(detail ?? error.message))
  },
)

export const api = {
  config: () => http.get<AppConfig>('/config').then((r) => r.data),
  patients: () => http.get<PatientListing[]>('/notes/patients').then((r) => r.data),
  notes: (mrn: string) =>
    http.get<{ mrn: string; notes: Note[] }>(`/notes/patients/${encodeURIComponent(mrn)}`).then((r) => r.data),
  startRun: (mrn: string, options: Partial<RunOptions>) =>
    http.post<Run>('/pipeline/runs', { mrn, options }).then((r) => r.data),
  runs: () => http.get<Run[]>('/pipeline/runs').then((r) => r.data),
  run: (id: string) => http.get<Run>(`/pipeline/runs/${id}`).then((r) => r.data),
}
