export interface ParamSchema {
  name: string
  type: 'string' | 'number' | 'date' | 'member_id_list' | 'boolean'
  description: string
  required: boolean
  default?: string
}

export type ExecType = 'trino_query' | 'davi_widget' | 'python_script' | 'claude_prompt'

export interface Automation {
  id: string
  name: string
  description: string
  category: string
  exec_type: ExecType
  exec_body: string
  exec_config: {
    headless_account?: string
    widget_name?: string
    timeout?: number
  }
  inputs: ParamSchema[]
  outputs: ParamSchema[]
  source_skill?: string
  created_at: string
  updated_at: string
}

export interface AutomationSummary {
  id: string
  name: string
  description: string
  category: string
  exec_type: ExecType
  input_count: number
  source_skill?: string
}

export interface ExecutionResult {
  success: boolean
  output: Record<string, unknown>
  error?: string
  duration_ms: number
  displays?: Array<{ type: string; data: string }>
}
