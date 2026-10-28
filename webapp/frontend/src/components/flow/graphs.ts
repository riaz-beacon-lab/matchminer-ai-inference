// Pure builders: run result -> Vue Flow nodes/edges.
import { MarkerType, type Edge, type Node } from '@vue-flow/core'

import type { FlowCardData } from '@/components/flow/FlowCard.vue'
import { CATEGORY_GROUP, CATEGORY_LABEL, DECISIONS, GROUPS, NEUTRAL, type GroupKey } from '@/components/flow/palette'
import type { Decision, JourneyEvent, Note, RunResult } from '@/types'

export type CardNode = Node<FlowCardData>

const ROW = { note: 84, event: 92, facet: 118, trial: 118, decision: 110 }
// Long columns (notes, events) wrap into sub-columns of at most this many rows.
const MAX_ROWS = 10
const SUB_COL_GAP = 260
const STAGE_GAP = 340
// Above this many notes, the notes column groups by year + note type.
const MAX_INDIVIDUAL_NOTES = 30

const fmtDate = (iso: string) => iso.slice(0, 10)
const clip = (s: string | null | undefined, n = 140) => (!s ? '' : s.length > n ? `${s.slice(0, n - 1)}…` : s)

type Item = { id: string; data: FlowCardData }

/** Place a stage's items column-major from x, each sub-column centred on height. */
function stage(items: Item[], x: number, step: number, height: number, maxRows = MAX_ROWS) {
  const nodes: CardNode[] = items.map((item, i) => {
    const col = Math.floor(i / maxRows)
    const inCol = Math.min(maxRows, items.length - col * maxRows)
    const top = (height - inCol * step) / 2
    return { id: item.id, type: 'card', position: { x: x + col * SUB_COL_GAP, y: top + (i % maxRows) * step }, data: item.data }
  })
  const cols = Math.max(1, Math.ceil(items.length / maxRows))
  return { nodes, nextX: x + (cols - 1) * SUB_COL_GAP + STAGE_GAP }
}

function edge(source: string, target: string, opts: Partial<Edge> = {}): Edge {
  return { id: `${source}->${target}`, source, target, type: 'default', ...opts }
}

/** Note id -> node id (individual notes, or the year/type group they fall in). */
function noteNodes(notes: Note[]) {
  const byNote = new Map<string, string>()
  if (notes.length <= MAX_INDIVIDUAL_NOTES) {
    const items = notes.map((n) => {
      byNote.set(n.note_id, `note:${n.note_id}`)
      return {
        id: `note:${n.note_id}`,
        data: { eyebrow: `${n.note_id} · ${fmtDate(n.note_date)}`, title: n.event_type, subtitle: clip(n.note_text, 70), color: NEUTRAL, inputs: false },
      }
    })
    return { items, byNote }
  }
  const groups = new Map<string, Note[]>()
  for (const n of notes) {
    const key = `${n.note_date.slice(0, 4)} · ${n.event_type}`
    groups.set(key, [...(groups.get(key) ?? []), n])
  }
  const items = [...groups.entries()].map(([key, group]) => {
    const id = `notegrp:${key}`
    group.forEach((n) => byNote.set(n.note_id, id))
    return { id, data: { eyebrow: key.split(' · ')[0], title: key.split(' · ')[1], badge: `${group.length} notes`, color: NEUTRAL, inputs: false } }
  })
  return { items, byNote }
}

// Which summary facet each journey group feeds.
const GROUP_FACET: Record<GroupKey, string> = {
  diagnosis: 'Diagnosis',
  treatment: 'Treatment history',
  status: 'Current extent',
  other: 'Exclusion evidence',
}

export function buildDecisionGraph(result: RunResult, cutoff: number) {
  const notes = result.notes ?? []
  const events = result.journey?.events ?? []
  const summary = result.summary
  const decisions = result.decisions ?? []
  const nodes: CardNode[] = []
  const edges: Edge[] = []

  const { items: noteItems, byNote } = noteNodes(notes)
  const eventItems = events.map((e) => {
    const group = GROUPS[CATEGORY_GROUP[e.category] ?? 'other']
    return { id: `event:${e.id}`, data: { eyebrow: `${CATEGORY_LABEL[e.category] ?? e.category} · ${e.date}`, title: e.title, color: group.color } }
  })

  const f = summary?.parsed.fields ?? {}
  const facetItems = [
    { key: 'Diagnosis', title: f['Cancer type'] || '—', subtitle: f['Histology'], color: GROUPS.diagnosis.color },
    { key: 'Biomarkers', title: `${summary?.parsed.biomarkers.length ?? 0} biomarkers`, subtitle: summary?.parsed.biomarkers.slice(0, 4).join(' · '), color: GROUPS.diagnosis.color },
    { key: 'Treatment history', title: `${summary?.parsed.treatment_history.length ?? 0} treatment entries`, subtitle: summary?.parsed.treatment_history.at(-1)?.what, color: GROUPS.treatment.color },
    { key: 'Current extent', title: clip(f['Current extent'], 90) || '—', color: GROUPS.status.color },
    { key: 'Exclusion evidence', title: clip(summary?.general_exclusion_criteria_evidence, 90) || '—', color: GROUPS.other.color },
  ].map((x) => ({ id: `facet:${x.key}`, data: { eyebrow: x.key, title: x.title, subtitle: clip(x.subtitle, 110), color: x.color } }))

  const trialItems = decisions.map((d) => {
    const status = DECISIONS[d.decision]
    return {
      id: `trial:${d.trial_id}`,
      data: {
        eyebrow: `#${d.rank} · ${d.trial_id}`,
        title: d.trial_title ?? d.trial_id,
        color: status.color,
        icon: status.icon,
        badge: d.exclusion_criteria_pass === false ? 'exclusion flag' : undefined,
        score: d.match_quality_score,
        cutoff,
        scoreLabel: 'TrialChecker',
        width: 280,
      },
    }
  })

  const counts = decisions.reduce<Record<string, number>>((acc, d) => ({ ...acc, [d.decision]: (acc[d.decision] ?? 0) + 1 }), {})
  const decisionItems = (Object.keys(DECISIONS) as Decision[]).map((k) => ({
    id: `decision:${k}`,
    data: { eyebrow: 'Final decision', title: DECISIONS[k].label, icon: DECISIONS[k].icon, badge: `${counts[k] ?? 0} trials`, color: DECISIONS[k].color, outputs: false },
  }))

  const rows = (n: number, max = MAX_ROWS) => Math.min(n, max)
  const height = Math.max(
    rows(noteItems.length) * ROW.note,
    rows(eventItems.length) * ROW.event,
    facetItems.length * ROW.facet,
    rows(trialItems.length, 12) * ROW.trial,
    3 * ROW.decision,
  )
  const noteStage = stage(noteItems, 0, ROW.note, height)
  const eventStage = stage(eventItems, noteStage.nextX, ROW.event, height)
  const facetStage = stage(facetItems, eventStage.nextX, ROW.facet, height, facetItems.length)
  const patientX = facetStage.nextX
  const trialStage = stage(trialItems, patientX + STAGE_GAP, ROW.trial, height, 12)
  const decisionStage = stage(decisionItems, trialStage.nextX + 40, ROW.decision, height)
  nodes.push(...noteStage.nodes, ...eventStage.nodes, ...facetStage.nodes, ...trialStage.nodes, ...decisionStage.nodes)
  if (summary) {
    const age = f['Age'] ? `${f['Age']} y` : ''
    nodes.push({
      id: 'patient',
      type: 'card',
      position: { x: patientX, y: height / 2 - 60 },
      data: { eyebrow: ['Patient summary', age, f['Sex']].filter(Boolean).join(' · '), title: result.journey?.headline || f['Cancer type'] || summary.patient_id, subtitle: f['Histology'], color: NEUTRAL, width: 260 },
    })
  }

  const thin = { stroke: '#b8b7b1', strokeWidth: 1.25 }
  const seen = new Set<string>()
  for (const e of events) {
    for (const nid of e.note_ids) {
      const src = byNote.get(nid)
      const id = `${src}->event:${e.id}`
      if (src && !seen.has(id)) {
        seen.add(id)
        edges.push(edge(src, `event:${e.id}`, { style: thin }))
      }
    }
    const group = CATEGORY_GROUP[e.category] ?? 'other'
    const facet = e.category === 'biomarker' ? 'Biomarkers' : GROUP_FACET[group]
    edges.push(edge(`event:${e.id}`, `facet:${facet}`, { style: { ...thin, stroke: GROUPS[group].color } }))
  }
  if (summary) {
    for (const item of facetItems) edges.push(edge(item.id, 'patient', { style: thin }))
    for (const d of decisions) {
      const status = DECISIONS[d.decision]
      edges.push(
        edge('patient', `trial:${d.trial_id}`, {
          label: `sim ${d.similarity_score.toFixed(2)}`,
          labelStyle: { fontSize: '10px', fill: '#52514e' },
          style: { ...thin, strokeWidth: d.decision === 'not_matched' ? 1 : 2 },
        }),
        edge(`trial:${d.trial_id}`, `decision:${d.decision}`, {
          animated: d.decision === 'eligible',
          style: { stroke: status.color, strokeWidth: 2 },
          markerEnd: { type: MarkerType.ArrowClosed, color: status.color },
        }),
      )
    }
  }
  return { nodes, edges }
}

const LANES: GroupKey[] = ['diagnosis', 'treatment', 'status', 'other']

/** Year x lane grid: one column per year, one lane per event group; events
 * stack inside a cell and are chained chronologically. */
export function buildJourneyGraph(events: JourneyEvent[]) {
  const STEP = 84
  const YEAR_W = 250
  const LANE_GAP = 40
  const year = (e: JourneyEvent) => e.date.slice(0, 4) || '?'
  const group = (e: JourneyEvent) => CATEGORY_GROUP[e.category] ?? 'other'
  const years = [...new Set(events.map(year))].sort()
  const cell = new Map<string, number>()
  const laneRows = Object.fromEntries(LANES.map((g) => [g, 1])) as Record<GroupKey, number>
  for (const e of events) {
    const k = `${year(e)}|${group(e)}`
    cell.set(k, (cell.get(k) ?? 0) + 1)
    laneRows[group(e)] = Math.max(laneRows[group(e)], cell.get(k)!)
  }
  const laneTop = {} as Record<GroupKey, number>
  let y = 0
  for (const g of LANES) {
    laneTop[g] = y
    y += laneRows[g] * STEP + LANE_GAP
  }

  const fixed = { draggable: false, selectable: false }
  const nodes: CardNode[] = [
    ...LANES.map((g) => ({
      id: `lane:${g}`,
      type: 'card',
      position: { x: -200, y: laneTop[g] },
      ...fixed,
      data: { eyebrow: 'Lane', title: GROUPS[g].label, color: GROUPS[g].color, width: 150, inputs: false, outputs: false },
    })),
    ...years.map((yr, i) => ({
      id: `lane:year-${yr}`,
      type: 'card',
      position: { x: i * YEAR_W, y: -70 },
      ...fixed,
      data: { eyebrow: 'Year', title: yr, color: NEUTRAL, width: 210, inputs: false, outputs: false },
    })),
  ]
  const placed = new Map<string, number>()
  for (const e of events) {
    const k = `${year(e)}|${group(e)}`
    const row = placed.get(k) ?? 0
    placed.set(k, row + 1)
    nodes.push({
      id: `event:${e.id}`,
      type: 'card',
      position: { x: years.indexOf(year(e)) * YEAR_W, y: laneTop[group(e)] + row * STEP },
      data: { eyebrow: `${CATEGORY_LABEL[e.category] ?? e.category} · ${e.date}`, title: e.title, color: GROUPS[group(e)].color, width: 210 },
    })
  }
  const edges = events.slice(1).map((e, i) =>
    edge(`event:${events[i]!.id}`, `event:${e.id}`, {
      style: { stroke: '#b8b7b1', strokeWidth: 1.25 },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#b8b7b1' },
    }),
  )
  return { nodes, edges }
}

/** Dim everything except the selected node and its direct neighbours. */
export function focus(nodes: CardNode[], edges: Edge[], selected: string | null) {
  if (!selected || !nodes.some((n) => n.id === selected)) return { nodes, edges }
  const near = new Set([selected])
  for (const e of edges) {
    if (e.source === selected) near.add(e.target)
    if (e.target === selected) near.add(e.source)
  }
  return {
    nodes: nodes.map((n) => (n.id.startsWith('lane:') ? n : { ...n, data: { ...n.data, dimmed: !near.has(n.id) } })),
    edges: edges.map((e) => {
      const on = e.source === selected || e.target === selected
      return { ...e, style: { ...(e.style as object), opacity: on ? 1 : 0.12, strokeWidth: on ? 2.5 : 1 } }
    }),
  }
}
