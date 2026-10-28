import type { Decision, JourneyCategory } from '@/types'

// Categorical slots 1-3 of the dataviz reference palette (validated all-pairs,
// light mode); "Other" is neutral gray. Aqua is < 3:1 on the surface, so every
// node also shows its group as a text label (never color alone).
export const GROUPS = {
  diagnosis: { label: 'Diagnosis', color: '#2a78d6' },
  treatment: { label: 'Treatment', color: '#eb6834' },
  status: { label: 'Disease status', color: '#1baf7a' },
  other: { label: 'Other', color: '#8a8984' },
} as const

export type GroupKey = keyof typeof GROUPS

export const CATEGORY_GROUP: Record<JourneyCategory, GroupKey> = {
  presentation: 'diagnosis',
  diagnosis: 'diagnosis',
  pathology: 'diagnosis',
  biomarker: 'diagnosis',
  surgery: 'treatment',
  systemic_therapy: 'treatment',
  radiation: 'treatment',
  imaging: 'status',
  response: 'status',
  progression: 'status',
  toxicity: 'other',
  other: 'other',
}

export const CATEGORY_LABEL: Record<JourneyCategory, string> = {
  presentation: 'Presentation',
  diagnosis: 'Diagnosis',
  pathology: 'Pathology',
  biomarker: 'Biomarker',
  surgery: 'Surgery',
  systemic_therapy: 'Systemic therapy',
  radiation: 'Radiation',
  imaging: 'Imaging',
  response: 'Response',
  progression: 'Progression',
  toxicity: 'Toxicity',
  other: 'Other',
}

// Status palette (reserved for state). Always paired with an icon + label.
export const DECISIONS: Record<Decision, { label: string; color: string; icon: string }> = {
  eligible: { label: 'Potentially eligible', color: '#0ca30c', icon: '✓' },
  needs_review: { label: 'Needs review', color: '#fab219', icon: '!' },
  not_matched: { label: 'Not matched', color: '#8a8984', icon: '–' },
}

export const NEUTRAL = '#52514e'
export const METER_FILL = '#2a78d6'
