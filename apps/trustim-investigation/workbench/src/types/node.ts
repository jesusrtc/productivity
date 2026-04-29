/** Action types that create graph nodes (R14) */
export type ActionType =
  | 'skill_invocation'
  | 'mcp_tool_call'
  | 'query_execution'
  | 'enrichment'
  | 'annotation'
  | 'recommendation'

/**
 * Maps a threat_score (0-1) to a continuous color gradient.
 *
 * PRD Section 3.2: "The gradient is continuous, not bucketed into levels.
 * A node at 0.3 looks different from 0.4."
 *
 * 0.0 = green (hue 120), 0.5 = yellow/orange (hue 40), 1.0 = red (hue 0)
 * Score of exactly 0 (no data) renders as gray.
 *
 * Uses HSL interpolation for a natural, perceptually smooth gradient.
 */
export function confidenceColor(score: number): string {
  if (score <= 0) return '#6b7280' // gray — no data / not computed
  // Clamp to 0-1
  const t = Math.max(0.01, Math.min(1, score))
  // Hue: 120 (green) → 40 (yellow) → 0 (red)
  // Use a slight curve so the yellow range is wider
  const hue = 120 * (1 - t)
  // Saturation: 70% at low, 85% at high for richer reds
  const sat = 70 + t * 15
  // Lightness: 45% throughout for consistent brightness
  const lit = 48 - t * 6
  return `hsl(${hue.toFixed(0)}, ${sat.toFixed(0)}%, ${lit.toFixed(0)}%)`
}

/** Node execution status. Q4: paused_for_input when skill needs investigator choice */
export type NodeStatus = 'running' | 'completed' | 'failed' | 'needs_review' | 'paused_for_input'

/** Edge relationship types (R15) */
export type EdgeRelation = 'led_to' | 'branched_from' | 'supports'

/** Display data from tool/query results */
export interface DisplayData {
  type: 'table' | 'json' | 'text' | 'html' | 'image'
  data: string
  metadata?: Record<string, unknown>
}

/**
 * Core node data model — matches PRD Section 5.2.2 exactly.
 * Every field from the spec is represented here.
 */
export interface InvestigationNode {
  node_id: string
  parent_ids: string[]
  action_type: ActionType
  skill_name: string | null
  tool_name: string | null
  source_tool: string | null
  query: string
  parameters: Record<string, unknown>
  result_summary: string
  result_raw: string
  displays: DisplayData[]
  confidence: number
  timestamp: string
  duration_ms: number
  status: NodeStatus
  investigator_notes: string
  ipynb_cell_ref: number | null

  /** Agent reasoning for why this action was taken (R38) */
  reasoning: string
  /** Q4: Prompt for investigator input when skill is paused */
  input_prompt: string | null
  /** Q4: Choices offered when paused (null = free text) */
  input_choices: string[] | null
  /** Why this threat score was assigned (agent reasoning or heuristic explanation) */
  confidence_reasoning: string
  /** Whether confidence was manually overridden by the investigator */
  confidence_override: boolean
  /** Whether this branch was marked as a dead end */
  is_dead_end: boolean
  /** Collapsed subtree flag for graph visualization */
  subtree_collapsed: boolean
  /** Short label for collapsed node view */
  label: string
  /** Custom investigator tags (e.g., "IOC", "escalate", "false-positive") */
  tags: string[]
  /** Pinned nodes stay visible even when parent subtree is collapsed */
  pinned: boolean
}

/** Edge in the investigation graph */
export interface InvestigationEdge {
  id: string
  source: string
  target: string
  relation: EdgeRelation
}


/** Action type icons (unicode for simplicity) */
export const ACTION_TYPE_ICONS: Record<ActionType, string> = {
  skill_invocation: '\u2699',   // gear
  mcp_tool_call: '\u26A1',     // lightning
  query_execution: '\u{1F50D}', // magnifying glass
  enrichment: '\u{1F4CA}',     // bar chart
  annotation: '\u{1F4DD}',     // memo
  recommendation: '\u{1F3AF}', // dart
}

/** Create a default/empty node */
export function createNode(overrides: Partial<InvestigationNode> & { node_id: string }): InvestigationNode {
  return {
    parent_ids: [],
    action_type: 'query_execution',
    skill_name: null,
    tool_name: null,
    source_tool: null,
    query: '',
    parameters: {},
    result_summary: '',
    result_raw: '',
    displays: [],
    confidence: 0,
    timestamp: new Date().toISOString(),
    duration_ms: 0,
    status: 'running',
    investigator_notes: '',
    ipynb_cell_ref: null,
    reasoning: '',
    input_prompt: null,
    input_choices: null,
    confidence_reasoning: '',
    confidence_override: false,
    is_dead_end: false,
    subtree_collapsed: false,
    label: '',
    tags: [],
    pinned: false,
    ...overrides,
  }
}
