/**
 * Server-side playbook execution engine.
 *
 * Uses a SINGLE persistent Claude bridge per playbook run so the LLM has full
 * context across all steps. Condition/note/prompt nodes are evaluated by the LLM
 * using the accumulated conversation context.
 */

import fs from 'fs'
import path from 'path'
import { ClaudeBridge, type BridgeEvent } from './bridge/claude-bridge.js'
import { evaluateConditions } from './condition-evaluator.js'
import type { PlaybookNode, PlaybookEdge, Playbook, PlaybookExecution } from '../src/types/playbook.js'

export type { PlaybookNode, PlaybookEdge, Playbook, PlaybookExecution }

type AutomationFinder = (id: string) => any | null
type BroadcastFn = (msg: object) => void

const activeExecutions = new Map<string, PlaybookExecution>()
const activeBridges = new Map<string, ClaudeBridge>()

export function getPlaybookExecutions(): PlaybookExecution[] {
  return Array.from(activeExecutions.values())
}

export function getPlaybookExecution(id: string): PlaybookExecution | null {
  return activeExecutions.get(id) || null
}

export function cancelPlaybookExecution(id: string): boolean {
  const exec = activeExecutions.get(id)
  if (!exec || exec.status !== 'running') return false
  exec.status = 'cancelled'
  exec.finished_at = new Date().toISOString()
  const bridge = activeBridges.get(id)
  if (bridge) { bridge.abort(); activeBridges.delete(id) }
  return true
}

/** Resolve {{node.field}} and {{input.field}} references */
function resolveInputs(
  node: PlaybookNode,
  nodeOutputs: Record<string, Record<string, unknown>>,
  playbookInputs: Record<string, unknown>,
): Record<string, unknown> {
  const resolved: Record<string, unknown> = { ...node.inputs }
  for (const [key, ref] of Object.entries(node.input_refs)) {
    // Check {{input.X}} FIRST — playbook-level inputs take priority
    if (ref.startsWith('{{input.')) {
      const field = ref.replace('{{input.', '').replace('}}', '')
      resolved[key] = playbookInputs[field] !== undefined ? String(playbookInputs[field]) : node.inputs[key] || ''
    } else {
      const match = ref.match(/^\{\{(\w+)\.([\w.]+)\}\}$/)
      if (match) {
        const [, nodeId, fieldPath] = match
        let val: unknown = nodeOutputs[nodeId] || {}
        for (const part of fieldPath.split('.')) {
          if (val && typeof val === 'object') val = (val as Record<string, unknown>)[part]
          else { val = undefined; break }
        }
        resolved[key] = val !== undefined ? String(val) : node.inputs[key] || ''
      }
    }
  }
  return resolved
}

/** Topological sort */
function topoSort(nodes: PlaybookNode[], edges: PlaybookEdge[]): string[] {
  const inDegree: Record<string, number> = {}
  const adj: Record<string, string[]> = {}
  for (const n of nodes) { inDegree[n.id] = 0; adj[n.id] = [] }
  for (const e of edges) {
    inDegree[e.target] = (inDegree[e.target] || 0) + 1
    adj[e.source] = adj[e.source] || []
    adj[e.source].push(e.target)
  }
  const queue = nodes.filter(n => inDegree[n.id] === 0).map(n => n.id)
  const sorted: string[] = []
  while (queue.length > 0) {
    const id = queue.shift()!
    sorted.push(id)
    for (const next of (adj[id] || [])) {
      inDegree[next]--
      if (inDegree[next] === 0) queue.push(next)
    }
  }
  return sorted
}

/** Build a text description of the playbook for the LLM system prompt */
function buildPlaybookPrompt(playbook: Playbook): string {
  const lines = [
    `You are executing a playbook: "${playbook.name}"`,
    playbook.description ? `Description: ${playbook.description}` : '',
    '',
    'Steps in this playbook:',
  ]
  const nodeMap = new Map(playbook.nodes.map(n => [n.id, n]))
  for (const n of playbook.nodes) {
    const type = n.ref_type === 'automation' ? `[Automation: ${n.ref_id}]` : `[${n.ref_type}]`
    lines.push(`  ${n.id}: ${n.label} ${type}`)
    if (n.body) lines.push(`    Text: ${n.body}`)
  }
  lines.push('')
  lines.push('Connections:')
  for (const e of playbook.edges) {
    const from = nodeMap.get(e.source)?.label || e.source
    const to = nodeMap.get(e.target)?.label || e.target
    lines.push(`  ${from} → ${to}${e.label ? ` (${e.label})` : ''}`)
  }
  lines.push('')
  lines.push('For each step, I will ask you to execute it. For automation steps, run the query. For condition steps, evaluate the condition based on previous results and respond with PASS or SKIP. For prompt steps, respond to the prompt. For note steps, acknowledge and continue.')
  return lines.filter(l => l !== undefined).join('\n')
}

/** Send a message to the bridge and collect the response (5 min timeout) */
function bridgeSend(bridge: ClaudeBridge, message: string): Promise<{ text: string; toolResult: string; error: string }> {
  return new Promise((resolve) => {
    let text = '', toolResult = '', error = ''
    const timer = setTimeout(() => {
      bridge.offEvent(handler)
      bridge.abort()
      resolve({ text, toolResult, error: error || 'Bridge timeout after 5 minutes' })
    }, 300000)
    const handler = (event: BridgeEvent) => {
      if (event.type === 'text' && event.data.text) text += event.data.text
      if (event.type === 'tool_end' && event.data.toolResult) toolResult = event.data.toolResult
      if (event.type === 'error' && event.data.error) error = event.data.error
      if (event.type === 'done') {
        clearTimeout(timer)
        bridge.offEvent(handler)
        resolve({ text, toolResult, error })
      }
    }
    bridge.onEvent(handler)
    bridge.send(message).catch(err => {
      clearTimeout(timer)
      bridge.offEvent(handler)
      resolve({ text, toolResult, error: String(err) })
    })
  })
}

/**
 * Run a playbook with a single persistent Claude bridge.
 */
export async function runPlaybook(
  playbook: Playbook,
  inputs: Record<string, unknown>,
  sessionId: string,
  sessionsDir: string,
  findAutomation: AutomationFinder,
  projectDir: string,
  broadcast: BroadcastFn,
  _depth = 0,
): Promise<PlaybookExecution> {
  if (_depth > 5) {
    const exec: PlaybookExecution = { id: `exec-depth-limit`, playbook_id: playbook.id, session_id: sessionId, status: 'failed', node_states: {}, resolved_inputs: inputs, started_at: new Date().toISOString(), finished_at: new Date().toISOString() }
    return exec
  }
  const execId = `exec-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
  const execution: PlaybookExecution = {
    id: execId,
    playbook_id: playbook.id,
    session_id: sessionId,
    status: 'running',
    node_states: {},
    resolved_inputs: inputs,
    started_at: new Date().toISOString(),
  }
  for (const n of playbook.nodes) execution.node_states[n.id] = { status: 'pending' }
  activeExecutions.set(execId, execution)

  // Single Claude bridge for the entire playbook
  const bridge = new ClaudeBridge(projectDir)
  bridge.maxTurns = 10 // enough for tool call + retries per step
  activeBridges.set(execId, bridge)

  broadcast({ type: 'playbook_started', payload: { executionId: execId, playbookId: playbook.id, sessionId } })

  // Session file helpers with simple file locking (mutex via lockfile)
  const sanitizedSessionId = sessionId.replace(/[^a-zA-Z0-9_-]/g, '')
  const sessionPath = path.resolve(sessionsDir, `${sanitizedSessionId}.json`)
  if (!sessionPath.startsWith(path.resolve(sessionsDir))) throw new Error('Invalid session ID')
  const lockPath = sessionPath + '.lock'
  const acquireLock = (retries = 10): boolean => {
    for (let i = 0; i < retries; i++) {
      try {
        fs.writeFileSync(lockPath, String(process.pid), { flag: 'wx' })
        return true
      } catch {
        // Lock exists — check if stale (>10s old)
        try {
          const stat = fs.statSync(lockPath)
          if (Date.now() - stat.mtimeMs > 10000) { fs.unlinkSync(lockPath); continue }
        } catch {}
        // Wait 100ms and retry
        const start = Date.now(); while (Date.now() - start < 100) {}
      }
    }
    return false
  }
  const releaseLock = () => { try { fs.unlinkSync(lockPath) } catch {} }
  const loadSession = () => {
    try { return JSON.parse(fs.readFileSync(sessionPath, 'utf-8')) }
    catch { return { id: sessionId, name: `Playbook: ${playbook.name}`, nodes: {}, edges: [], messages: [], skills_used: [], tools_used: [], created_at: new Date().toISOString(), updated_at: new Date().toISOString() } }
  }
  const saveSession = (session: any) => {
    if (acquireLock()) {
      try { fs.writeFileSync(sessionPath, JSON.stringify(session, null, 2)) } catch {}
      finally { releaseLock() }
    }
  }

  const nodeOutputs: Record<string, Record<string, unknown>> = {}
  const nodeMap = new Map(playbook.nodes.map(n => [n.id, n]))
  const sorted = topoSort(playbook.nodes, playbook.edges)
  let lastInvNodeId: string | null = null

  // Build context summary for the LLM as we go
  const stepResults: string[] = []

  for (const pbNodeId of sorted) {
    if (execution.status === 'cancelled') break

    const pbNode = nodeMap.get(pbNodeId)!
    const state = execution.node_states[pbNodeId]

    // Check incoming edge conditions
    const incomingEdges = playbook.edges.filter(e => e.target === pbNodeId)
    if (incomingEdges.length > 0) {
      const canRun = incomingEdges.some(e => {
        const parentOutput = nodeOutputs[e.source] || {}
        return evaluateConditions(e.conditions, parentOutput)
      })
      if (!canRun) {
        state.status = 'skipped'
        stepResults.push(`Step "${pbNode.label}": SKIPPED (conditions not met)`)
        broadcast({ type: 'playbook_node_skipped', payload: { executionId: execId, nodeId: pbNodeId } })
        continue
      }
    }

    const resolvedInputs = resolveInputs(pbNode, nodeOutputs, inputs)
    state.status = 'running'
    state.started_at = new Date().toISOString()

    // Create investigation node
    const invNodeId = `pb-${pbNodeId}-${Date.now()}`
    const session = loadSession()
    session.nodes[invNodeId] = {
      node_id: invNodeId,
      parent_ids: lastInvNodeId ? [lastInvNodeId] : [],
      children_ids: [],
      label: pbNode.label,
      query: pbNode.body || JSON.stringify(resolvedInputs),
      status: 'running',
      action_type: pbNode.ref_type === 'automation' ? 'skill_invocation' : 'annotation',
      skill_name: pbNode.ref_type === 'automation' ? pbNode.ref_id : null,
      tool_name: pbNode.ref_id,
      source_tool: 'playbook',
      parameters: resolvedInputs,
      confidence: 0,
      confidence_reasoning: '',
      confidence_override: false,
      result_summary: '',
      result_raw: '',
      displays: [],
      timestamp: new Date().toISOString(),
      duration_ms: 0,
      tags: ['playbook', playbook.name],
      reasoning: pbNode.body || `Playbook step: ${pbNode.label}`,
      investigator_notes: '',
      ipynb_cell_ref: null,
      input_prompt: null,
      input_choices: null,
      is_dead_end: false,
      subtree_collapsed: false,
      pinned: false,
    }
    if (lastInvNodeId && session.nodes[lastInvNodeId]) {
      if (!session.nodes[lastInvNodeId].children_ids) session.nodes[lastInvNodeId].children_ids = []
      session.nodes[lastInvNodeId].children_ids.push(invNodeId)
      session.edges.push({ id: `edge-${lastInvNodeId}-${invNodeId}`, source: lastInvNodeId, target: invNodeId, relation: 'led_to' })
    }
    // Add chat message
    session.messages = session.messages || []
    session.messages.push({ id: `msg-${Date.now()}-${Math.random().toString(36).slice(2,5)}`, role: 'system', content: `Running playbook step: **${pbNode.label}**`, timestamp: new Date().toISOString(), node_ids: [invNodeId] })
    saveSession(session)
    broadcast({ type: 'playbook_node_start', payload: { executionId: execId, nodeId: pbNodeId, invNodeId } })

    const startTime = Date.now()

    try {
      let result = '', error = '', success = true

      if (pbNode.ref_type === 'automation') {
        // Find the automation and build the prompt
        const auto = findAutomation(pbNode.ref_id)
        if (!auto) {
          error = `Automation "${pbNode.ref_id}" not found`
          success = false
        } else if (auto.exec_type === 'trino_query') {
          let sql = String(auto.exec_body || '')
          for (const [key, value] of Object.entries(resolvedInputs)) {
            sql = sql.replace(new RegExp(`\\{${key}\\}`, 'g'), String(value))
          }
          const account = auto.exec_config?.headless_account || 'trustim'
          const fullSql = `SET SESSION li_authorization_user = '${account}';\n${sql}`

          // Build context-aware prompt
          const contextSummary = stepResults.length > 0 ? `\n\nPrevious step results:\n${stepResults.join('\n')}` : ''
          const prompt = `Playbook step "${pbNode.label}": Run this Trino query and return the results.${contextSummary}\n\n\`\`\`sql\n${fullSql}\n\`\`\``

          const resp = await bridgeSend(bridge, prompt)
          result = resp.toolResult || resp.text || ''
          error = resp.error
          success = !error && !!result
        } else if (auto.exec_type === 'davi_widget') {
          const { spawn: spawnChild } = await import('child_process')
          let code = String(auto.exec_body || '')
          for (const [key, value] of Object.entries(resolvedInputs)) code = code.replace(new RegExp(`\\{${key}\\}`, 'g'), String(value))
          const daviPath = path.join(projectDir, 'tools', 'davi_runner.py')
          const timeout = auto.exec_config?.timeout || 300000
          try {
            result = await new Promise<string>((resolve, reject) => {
              const proc = spawnChild('python3', [daviPath, 'run', code, '--timeout', String(Math.floor(timeout / 1000))], { cwd: projectDir, timeout })
              let out = '', err2 = ''
              proc.stdout?.on('data', (d: Buffer) => { out += d.toString() })
              proc.stderr?.on('data', (d: Buffer) => { err2 += d.toString() })
              proc.on('close', (c) => c === 0 ? resolve(out) : reject(err2 || `Exit ${c}`))
              proc.on('error', reject)
            })
          } catch (e) { error = String(e).slice(0, 500); success = false }

        } else if (auto.exec_type === 'python_script') {
          const { spawn: spawnChild } = await import('child_process')
          let code = String(auto.exec_body || '')
          for (const [key, value] of Object.entries(resolvedInputs)) code = code.replace(new RegExp(`\\{${key}\\}`, 'g'), String(value))
          try {
            result = await new Promise<string>((resolve, reject) => {
              const proc = spawnChild('python3', ['-c', code], { cwd: projectDir, timeout: 60000 })
              let out = '', err2 = ''
              proc.stdout?.on('data', (d: Buffer) => { out += d.toString() })
              proc.stderr?.on('data', (d: Buffer) => { err2 += d.toString() })
              proc.on('close', (c) => c === 0 ? resolve(out) : reject(err2 || `Exit ${c}`))
              proc.on('error', reject)
            })
          } catch (e) { error = String(e).slice(0, 500); success = false }

        } else if (auto.exec_type === 'claude_prompt') {
          let prompt = String(auto.exec_body || '')
          for (const [key, value] of Object.entries(resolvedInputs)) prompt = prompt.replace(new RegExp(`\\{${key}\\}`, 'g'), String(value))
          const contextSummary = stepResults.length > 0 ? `\n\nContext:\n${stepResults.join('\n')}` : ''
          const resp = await bridgeSend(bridge, `${prompt}${contextSummary}`)
          result = resp.text || ''
          error = resp.error
          success = !error && !!result

        } else {
          error = `Unknown exec_type: ${auto.exec_type}`
          success = false
        }

      } else if (pbNode.ref_type === 'condition') {
        // Ask the LLM to evaluate the condition based on accumulated context
        const contextSummary = stepResults.join('\n')
        const prompt = `Playbook condition step "${pbNode.label}":\n\nCondition: ${pbNode.body || 'Evaluate if we should continue.'}\n\nPrevious results:\n${contextSummary}\n\nBased on the results above, should we CONTINUE (pass this condition) or SKIP the next steps? Respond with exactly "PASS" or "SKIP" followed by a one-line reason.`

        const resp = await bridgeSend(bridge, prompt)
        result = resp.text || ''
        const passed = result.toUpperCase().includes('PASS')
        success = true
        // Store as output so downstream edges can use it
        nodeOutputs[pbNodeId] = { result, passed: passed ? 'true' : 'false', decision: passed ? 'PASS' : 'SKIP' }

      } else if (pbNode.ref_type === 'prompt') {
        // Send the prompt body to the LLM with full context
        const contextSummary = stepResults.join('\n')
        const prompt = `Playbook prompt step "${pbNode.label}":\n\n${pbNode.body || 'Analyze the investigation results.'}\n\nContext from previous steps:\n${contextSummary}`

        const resp = await bridgeSend(bridge, prompt)
        result = resp.text || ''
        success = true

      } else if (pbNode.ref_type === 'note') {
        // Notes are informational — just record them
        result = pbNode.body || 'Note acknowledged'
        success = true

      } else if (pbNode.ref_type === 'playbook') {
        // Sub-playbook recursion — load and execute the referenced playbook
        const sanitizedRefId = pbNode.ref_id.replace(/[^a-zA-Z0-9_-]/g, '')
        const playbooksDir = path.resolve(sessionsDir, '..', '.playbooks')
        const subPbPath = path.resolve(playbooksDir, `${sanitizedRefId}.json`)
        if (!subPbPath.startsWith(path.resolve(playbooksDir))) { error = 'Invalid sub-playbook ref'; success = false }
        else if (fs.existsSync(subPbPath)) {
          const subPlaybook = JSON.parse(fs.readFileSync(subPbPath, 'utf-8'))
          const subExec = await runPlaybook(subPlaybook, resolvedInputs, sessionId, sessionsDir, findAutomation, projectDir, broadcast, _depth + 1)
          result = `Sub-playbook "${subPlaybook.name}" ${subExec.status}: ${Object.values(subExec.node_states).filter(s => s.status === 'completed').length}/${Object.keys(subExec.node_states).length} steps completed`
          success = subExec.status === 'completed'
          error = subExec.status === 'failed' ? 'Sub-playbook had failures' : ''
        } else {
          error = `Sub-playbook "${pbNode.ref_id}" not found`
          success = false
        }
      }

      // Update state
      state.status = success ? 'completed' : 'failed'
      state.output = { result }
      state.error = error || undefined
      state.finished_at = new Date().toISOString()
      if (pbNode.ref_type !== 'condition') {
        nodeOutputs[pbNodeId] = { result }
      }
      stepResults.push(`Step "${pbNode.label}" (${pbNode.ref_type}): ${success ? result.slice(0, 200) : `FAILED: ${error}`}`)

      // Update investigation node + add chat message
      const s2 = loadSession()
      if (s2.nodes[invNodeId]) {
        s2.nodes[invNodeId].status = success ? 'completed' : 'failed'
        s2.nodes[invNodeId].result_raw = result
        s2.nodes[invNodeId].result_summary = error || result.slice(0, 200) || 'Completed'
        s2.nodes[invNodeId].confidence = success ? 0.5 : 0
        s2.nodes[invNodeId].duration_ms = Date.now() - startTime
      }
      s2.messages = s2.messages || []
      s2.messages.push({ id: `msg-${Date.now()}-${Math.random().toString(36).slice(2,5)}`, role: 'assistant', content: `**${pbNode.label}** — ${success ? (result.slice(0, 300) || 'Completed') : `Failed: ${error}`}`, timestamp: new Date().toISOString(), node_ids: [invNodeId] })
      saveSession(s2)
      broadcast({ type: 'playbook_node_complete', payload: { executionId: execId, nodeId: pbNodeId, success } })
      lastInvNodeId = invNodeId

    } catch (err) {
      state.status = 'failed'
      state.error = String(err)
      state.finished_at = new Date().toISOString()
      stepResults.push(`Step "${pbNode.label}": FAILED: ${err}`)

      const s2 = loadSession()
      if (s2.nodes[invNodeId]) {
        s2.nodes[invNodeId].status = 'failed'
        s2.nodes[invNodeId].result_summary = `Error: ${err}`
        s2.nodes[invNodeId].duration_ms = Date.now() - startTime
      }
      saveSession(s2)
      broadcast({ type: 'playbook_node_complete', payload: { executionId: execId, nodeId: pbNodeId, success: false } })
    }
  }

  // Finalize
  execution.status = execution.status === 'cancelled' ? 'cancelled'
    : Object.values(execution.node_states).some(s => s.status === 'failed') ? 'failed'
    : 'completed'
  execution.finished_at = new Date().toISOString()

  // Clean up bridge
  bridge.abort()
  activeBridges.delete(execId)

  broadcast({ type: 'playbook_done', payload: { executionId: execId, status: execution.status } })
  // Keep execution visible for 10 minutes so the drawer can show final state
  setTimeout(() => activeExecutions.delete(execId), 600000)

  return execution
}
