import type { ParamSchema } from './automation'

export interface PlaybookCondition {
  field: string
  operator: 'gt' | 'lt' | 'eq' | 'neq' | 'contains' | 'exists' | 'not_empty'
  value: unknown
}

export interface PlaybookNode {
  id: string
  ref_id: string
  ref_type: 'automation' | 'playbook' | 'condition' | 'note' | 'prompt'
  label: string
  /** Literal input values */
  inputs: Record<string, string>
  /** References to parent node outputs: e.g. { MEMBER_IDS: '{{node1.result}}' } */
  input_refs: Record<string, string>
  /** Free text body — used by condition/note/prompt blocks, passed to LLM as context */
  body?: string
  position: { x: number; y: number }
}

export interface PlaybookEdge {
  id: string
  source: string
  target: string
  conditions?: PlaybookCondition[]
  label?: string
}

export interface Playbook {
  id: string
  name: string
  description: string
  category: string
  inputs: ParamSchema[]
  nodes: PlaybookNode[]
  edges: PlaybookEdge[]
  entry_node_ids: string[]
  version: number
  created_at: string
  updated_at: string
}

export interface PlaybookExecution {
  id: string
  playbook_id: string
  session_id: string
  status: 'running' | 'completed' | 'failed' | 'cancelled'
  node_states: Record<string, {
    status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
    output?: Record<string, unknown>
    error?: string
    started_at?: string
    finished_at?: string
  }>
  resolved_inputs: Record<string, unknown>
  started_at: string
  finished_at?: string
}
