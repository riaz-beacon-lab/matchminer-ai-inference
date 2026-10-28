// Shapes returned by the Flask API (webapp/backend/src/mmai_web/api).

export interface Note {
  note_id: string
  patient_id: string
  note_date: string
  event_type: string
  note_text: string
}

export interface ParsedSummary {
  fields: Record<string, string>
  biomarkers: string[]
  treatment_history: { when: string; what: string }[]
}

export interface PatientSummary {
  patient_id: string
  cancer_history_summary: string
  general_exclusion_criteria_evidence: string
  parsed: ParsedSummary
  qc: { metric: string; value: number; denominator?: number; percent?: number }[]
  ok: boolean
}

export type JourneyCategory =
  | 'presentation'
  | 'diagnosis'
  | 'pathology'
  | 'biomarker'
  | 'imaging'
  | 'surgery'
  | 'systemic_therapy'
  | 'radiation'
  | 'response'
  | 'progression'
  | 'toxicity'
  | 'other'

export interface JourneyEvent {
  id: string
  date: string
  category: JourneyCategory
  title: string
  detail: string
  note_ids: string[]
}

export interface Journey {
  headline: string
  events: JourneyEvent[]
}

export type Decision = 'eligible' | 'needs_review' | 'not_matched'

export interface TrialDecision {
  rank: number
  trial_id: string
  trial_title: string | null
  space_trial_id: string
  clinical_space_number: number
  clinical_space_summary: string
  general_exclusion_criteria: string
  similarity_score: number
  match_quality_score: number
  match_quality_pass: boolean
  exclusion_score?: number
  exclusion_criteria_pass?: boolean
  llm_match_quality_score?: number | null
  llm_match_quality_answer_text?: string | null
  llm_exclusion_criteria_pass?: boolean | null
  llm_exclusion_criteria_answer_text?: string | null
  decision: Decision
  decision_reasons: string[]
}

export interface Candidate {
  space_trial_id: string
  trial_id: string
  trial_title: string | null
  clinical_space_summary: string
  similarity_score: number
  match_quality_score: number
  match_quality_pass: boolean
}

export type StepStatus = 'pending' | 'running' | 'done' | 'error' | 'skipped'

export interface RunStep {
  key: string
  label: string
  status: StepStatus
  seconds?: number
  detail?: string
}

export interface RunOptions {
  top_k: number
  llm_review: boolean
  llm_review_top_n: number
  include_journey: boolean
}

export interface RunResult {
  models?: Record<string, string>
  notes?: Note[]
  summary?: PatientSummary
  journey?: Journey
  candidates?: Candidate[]
  decisions?: TrialDecision[]
  score_cutoff?: number
}

export interface Run {
  id: string
  mrn: string
  status: 'queued' | 'running' | 'done' | 'error'
  created_at: number
  options: RunOptions
  steps: RunStep[]
  error: string | null
  result?: RunResult
}

export interface PatientListing {
  mrn: string
  n_notes: number
  first_date: string
  last_date: string
}

export interface AppConfig {
  models: Record<string, string>
  llm_review_server: string[]
  apigee_configured: boolean
  notes_sources: string[]
  score_cutoff: number
}
