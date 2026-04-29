import { ClaudeBridge } from '../../bridge/claude-bridge.js'
import { getCaptainClient } from '../../bridge/captain-client.js'
import path from 'path'

export interface AutomationRunResult {
  success: boolean
  output: { result?: string }
  error?: string
  duration_ms: number
}

/** Replace {PARAM} placeholders in a template string */
export function substituteParams(template: string, inputs: Record<string, string>): string {
  let result = template
  for (const [key, value] of Object.entries(inputs)) {
    result = result.replace(new RegExp(`\\{${key}\\}`, 'g'), String(value))
  }
  return result
}

async function runTrinoQuery(sql: string, account: string, _repoRoot: string): Promise<AutomationRunResult> {
  const preamble = `SET SESSION li_authorization_user = '${account}'`
  const startTime = Date.now()
  try {
    const captain = getCaptainClient()
    const raw = await captain.callTool('execute_trino_query', {
      query: sql,
      server: 'holdem',
      preamble_sql: preamble,
    })
    return {
      success: true,
      output: { result: raw || 'No results returned' },
      duration_ms: Date.now() - startTime,
    }
  } catch (err) {
    return {
      success: false,
      output: {},
      error: String(err).slice(0, 1000),
      duration_ms: Date.now() - startTime,
    }
  }
}

async function runDaviWidget(code: string, timeout: number, repoRoot: string): Promise<AutomationRunResult> {
  const { spawn: spawnChild } = await import('child_process')
  const startTime = Date.now()
  const daviPath = path.join(repoRoot, 'tools', 'davi_runner.py')
  try {
    const result = await new Promise<string>((resolve, reject) => {
      const proc = spawnChild('python3', [daviPath, 'run', code, '--timeout', String(Math.floor(timeout / 1000))], { cwd: repoRoot, timeout })
      let stdout = '', stderr = ''
      proc.stdout?.on('data', (d: Buffer) => { stdout += d.toString() })
      proc.stderr?.on('data', (d: Buffer) => { stderr += d.toString() })
      proc.on('close', (exitCode) => exitCode === 0 ? resolve(stdout) : reject(stderr || `Exit code ${exitCode}`))
      proc.on('error', reject)
    })
    return { success: true, output: { result }, duration_ms: Date.now() - startTime }
  } catch (err) {
    return { success: false, output: {}, error: String(err).slice(0, 500), duration_ms: Date.now() - startTime }
  }
}

async function runPythonScript(code: string, repoRoot: string): Promise<AutomationRunResult> {
  const { spawn: spawnChild } = await import('child_process')
  const startTime = Date.now()
  try {
    const result = await new Promise<string>((resolve, reject) => {
      const proc = spawnChild('python3', ['-c', code], { cwd: repoRoot, timeout: 60000 })
      let stdout = '', stderr = ''
      proc.stdout?.on('data', (d: Buffer) => { stdout += d.toString() })
      proc.stderr?.on('data', (d: Buffer) => { stderr += d.toString() })
      proc.on('close', (exitCode) => exitCode === 0 ? resolve(stdout) : reject(stderr || `Exit code ${exitCode}`))
      proc.on('error', reject)
    })
    return { success: true, output: { result }, duration_ms: Date.now() - startTime }
  } catch (err) {
    return { success: false, output: {}, error: String(err).slice(0, 500), duration_ms: Date.now() - startTime }
  }
}

async function runClaudePrompt(prompt: string, repoRoot: string): Promise<AutomationRunResult> {
  const startTime = Date.now()
  const execBridge = new ClaudeBridge(repoRoot)
  execBridge.maxTurns = 3
  let text = '', error = ''
  execBridge.onEvent((event) => {
    if (event.type === 'text' && event.data.text) text += event.data.text
    if (event.type === 'error' && event.data.error) error = event.data.error
  })
  try { await execBridge.send(prompt) } finally { execBridge.abort() }
  return {
    success: !error && !!text,
    output: { result: text || 'No response' },
    error: error || undefined,
    duration_ms: Date.now() - startTime,
  }
}

/** Run an automation by dispatching to the appropriate executor */
export async function runAutomation(automation: any, inputs: Record<string, string>, repoRoot: string): Promise<AutomationRunResult> {
  if (automation.exec_type === 'trino_query') {
    const sql = substituteParams(String(automation.exec_body || ''), inputs)
    const account = automation.exec_config?.headless_account || 'trustim'
    return runTrinoQuery(sql, account, repoRoot)
  }

  if (automation.exec_type === 'davi_widget') {
    const code = substituteParams(String(automation.exec_body || ''), inputs)
    const timeout = automation.exec_config?.timeout || 300000
    return runDaviWidget(code, timeout, repoRoot)
  }

  if (automation.exec_type === 'python_script') {
    const code = substituteParams(String(automation.exec_body || ''), inputs)
    return runPythonScript(code, repoRoot)
  }

  if (automation.exec_type === 'claude_prompt') {
    const prompt = substituteParams(String(automation.exec_body || ''), inputs)
    return runClaudePrompt(prompt, repoRoot)
  }

  return { success: false, output: {}, error: `Unknown exec_type: ${automation.exec_type}`, duration_ms: 0 }
}
