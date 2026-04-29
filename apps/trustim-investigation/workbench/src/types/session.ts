import type { InvestigationNode, InvestigationEdge } from './node'

/** Chat message roles */
export type MessageRole = 'user' | 'assistant' | 'system'

/** A single chat message */
export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  timestamp: string
  /** Link to graph node(s) created by this message */
  node_ids: string[]
  /** Tool call metadata if applicable */
  tool_call?: {
    tool_name: string
    server: string
    parameters: Record<string, unknown>
    duration_ms: number
    success: boolean
  }
  /** Skill invocation metadata if applicable */
  skill_invocation?: {
    skill_name: string
    instructions_loaded: boolean
  }
}

/** MCP tool status */
export interface McpToolStatus {
  name: string
  server: string
  status: 'healthy' | 'degraded' | 'disconnected'
  last_checked: string
}

/** Session state — everything needed to save/restore (R31-R35) */
export interface Session {
  id: string
  name: string
  created_at: string
  updated_at: string
  starting_input: string
  starting_input_type: 'alert_id' | 'incident_id' | 'ioc' | 'natural_language' | 'raw_data' | 'none'
  nodes: Record<string, InvestigationNode>
  edges: InvestigationEdge[]
  messages: ChatMessage[]
  skills_used: string[]
  tools_used: string[]
  mcp_tools: McpToolStatus[]
  /** IDs of related investigation sessions */
  linked_sessions?: string[]
}

/** Session metadata for the session list (lightweight) */
export interface SessionSummary {
  id: string
  name: string
  created_at: string
  updated_at: string
  node_count: number
  max_severity: string
  max_confidence?: number
  completed_count?: number
  has_sev?: boolean
  skills_used?: string[]
  starting_input_type: string
}

/** Create a new empty session */
export function createSession(id: string, name: string, startingInput: string): Session {
  const inputType = detectInputType(startingInput)
  return {
    id,
    name,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    starting_input: startingInput,
    starting_input_type: inputType,
    nodes: {},
    edges: [],
    messages: [],
    skills_used: [],
    tools_used: [],
    mcp_tools: [],
  }
}

/** Detect the type of starting input (Section 4.5) */
function detectInputType(input: string): Session['starting_input_type'] {
  if (!input.trim()) return 'none'

  // Alert/incident ID patterns (numeric IDs)
  if (/^(alert|incident)\s*#?\s*\d+$/i.test(input.trim())) {
    return input.toLowerCase().includes('incident') ? 'incident_id' : 'alert_id'
  }
  if (/^\d{6,}$/.test(input.trim())) return 'alert_id'

  // IOC patterns: IP, email, domain, member ID
  if (/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/.test(input.trim())) return 'ioc'
  if (/^[a-f0-9]{32,}$/i.test(input.trim())) return 'ioc' // fingerprint hash
  if (/@/.test(input.trim()) && input.trim().split(/\s+/).length === 1) return 'ioc'

  // JSON or structured data
  if (input.trim().startsWith('{') || input.trim().startsWith('[')) return 'raw_data'

  return 'natural_language'
}
