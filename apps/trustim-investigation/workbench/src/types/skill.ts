/** Skill metadata parsed from SKILL.md frontmatter */
export interface Skill {
  name: string
  description: string
  allowed_tools: string[]
  file_path: string
  /** Derived category from directory structure */
  category: 'investigation' | 'action'
  /** Attack vector or functional area */
  area: string
}

/** Skills organized by category for the browser */
export interface SkillInventory {
  investigation: Skill[]
  action: Skill[]
}

/** Trace event for the log view (R36-R40) */
export interface TraceEvent {
  id: string
  timestamp: string
  type: 'tool_call' | 'skill_invocation' | 'query' | 'enrichment' | 'reasoning' | 'error'
  node_id: string | null
  summary: string
  detail: string
  duration_ms: number
  success: boolean
}

/** Graph view mode */
export type ViewMode = 'graph' | 'log' | 'heatmap' | 'timeline'
