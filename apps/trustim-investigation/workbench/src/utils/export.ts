import type { Session, InvestigationNode, InvestigationEdge, ChatMessage } from '../types'
import { extractCohort } from './cohort-extraction'
import { checkSevThresholds, formatSevAssessment } from './sev-checker'

/**
 * Extract Claude's analytical findings from chat messages.
 * These are the real investigation conclusions — not raw tool output summaries.
 * Filters out system messages, running indicators, and short replies.
 */
function extractAnalyticalFindings(messages: ChatMessage[]): string[] {
  return messages
    .filter(m => m.role === 'assistant' && m.content.length > 80)
    .filter(m =>
      !m.content.startsWith('Running:') &&
      !m.content.startsWith('**Investigation progress**') &&
      !m.content.includes('report published')
    )
    .map(m => m.content)
}

/** Full investigation export format (R52-R53) */
export interface InvestigationExport {
  version: '1.0'
  exported_at: string
  session: Session
  summary: string
  decision_path: DecisionPathStep[]
}

interface DecisionPathStep {
  step: number
  node_id: string
  action: string
  query: string
  result_summary: string
  confidence: number
  children_count: number
}

/** Export session as full JSON (R52) */
export function exportSessionJson(session: Session): string {
  const exp: InvestigationExport = {
    version: '1.0',
    exported_at: new Date().toISOString(),
    session,
    summary: generateSummary(session),
    decision_path: extractDecisionPath(session.nodes, session.edges),
  }
  return JSON.stringify(exp, null, 2)
}

/** Generate human-readable investigation summary (R55) */
export function generateSummary(session: Session): string {
  const nodes = Object.values(session.nodes)
  const completed = nodes.filter((n) => n.status === 'completed').length

  let summary = `# Investigation Summary: ${session.name}\n\n`
  summary += `**Date:** ${new Date(session.created_at).toLocaleDateString()}\n`
  summary += `**Starting Input:** ${session.starting_input || 'None'}\n\n`

  // Use Claude's analytical findings as the primary content
  const findings = extractAnalyticalFindings(session.messages || [])
  if (findings.length > 0) {
    summary += `## Findings\n\n`
    // Use the last finding (typically the conclusion) as primary
    summary += findings[findings.length - 1] + '\n\n'
    // Include earlier analysis as supporting detail
    if (findings.length > 1) {
      summary += `## Supporting Analysis\n\n`
      for (const f of findings.slice(0, -1).slice(-3)) {
        summary += f + '\n\n'
      }
    }
  } else {
    // Fallback to node summaries if no analytical messages
    const highConfNodes = nodes.filter((n) => n.confidence > 0.6)
    if (highConfNodes.length > 0) {
      summary += `## Findings\n\n`
      for (const node of highConfNodes) {
        summary += `- **${node.label}**: ${node.result_summary || ''}\n`
      }
      summary += '\n'
    }
  }

  summary += `## Investigation Path\n\n`
  summary += `${completed} queries completed.\n\n`
  const path = extractDecisionPath(session.nodes, session.edges)
  for (const step of path) {
    summary += `${step.step}. **${step.action}** — ${step.result_summary || 'No summary'}\n`
  }

  return summary
}

/** Generate a compact one-paragraph findings summary (for Slack/chat) */
export function generateQuickFindings(session: Session): string {
  // Use the last analytical finding as a compact summary
  const findings = extractAnalyticalFindings(session.messages || [])
  if (findings.length > 0) {
    const last = findings[findings.length - 1]
      .replace(/\*\*([^*]+)\*\*/g, '$1')
      .replace(/\n/g, ' ')
      .slice(0, 300)
    return `Investigation "${session.name}": ${last}`
  }

  const nodes = Object.values(session.nodes)
  const highNodes = nodes.filter(n => n.confidence > 0.5).sort((a, b) => b.confidence - a.confidence)
  if (highNodes.length === 0) {
    return `Investigation "${session.name}" (${nodes.length} nodes): No significant findings.`
  }

  const nodeFindings = highNodes.slice(0, 3).map(n => n.label).join(', ')
  return `Investigation "${session.name}": ${highNodes.length} finding(s) — ${nodeFindings}.`
}

/** Extract decision path from root to recommendations (R54) */
export function extractDecisionPath(
  nodes: Record<string, InvestigationNode>,
  edges: InvestigationEdge[],
): DecisionPathStep[] {
  const path: DecisionPathStep[] = []
  const nodeList = Object.values(nodes)

  // Find root nodes (no parents)
  const roots = nodeList.filter((n) => n.parent_ids.length === 0)
  if (roots.length === 0) return path

  // BFS from root, following highest-severity path
  const visited = new Set<string>()
  const queue: string[] = roots.map((r) => r.node_id)
  let step = 1

  while (queue.length > 0) {
    const nodeId = queue.shift()!
    if (visited.has(nodeId)) continue
    visited.add(nodeId)

    const node = nodes[nodeId]
    if (!node) continue

    const children = edges.filter((e) => e.source === nodeId).map((e) => e.target)

    path.push({
      step: step++,
      node_id: nodeId,
      action: node.label || node.action_type,
      query: node.query,
      result_summary: node.result_summary,
      confidence: node.confidence,
      children_count: children.length,
    })

    // Follow all children
    queue.push(...children)
  }

  return path
}

/** Export as ipynb for backward compatibility (R53) */
export function exportSessionIpynb(session: Session): string {
  const cells: object[] = []

  // Header cell
  cells.push({
    cell_type: 'markdown',
    metadata: {},
    source: [
      `# ${session.name}\n`,
      `\n`,
      `**Date:** ${new Date(session.created_at).toLocaleDateString()}\n`,
      `**Input:** ${session.starting_input || 'None'}\n`,
      `\n`,
      `Exported from Juniper\n`,
    ],
  })

  // One cell per node
  const sortedNodes = Object.values(session.nodes).sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  )

  for (const node of sortedNodes) {
    // Rich metadata for each cell pair
    const cellMeta = {
      node_id: node.node_id,
      action_type: node.action_type,
      threat_score: node.confidence,
      timestamp: node.timestamp,
      duration_ms: node.duration_ms,
      status: node.status,
      tool_name: node.tool_name,
      skill_name: node.skill_name,
      tags: node.tags || [],
      confidence_reasoning: node.confidence_reasoning || '',
    }

    // Markdown cell with summary + reasoning
    cells.push({
      cell_type: 'markdown',
      metadata: cellMeta,
      source: [
        `## ${node.label || node.action_type}\n`,
        `\n`,
        `**Threat Score:** ${(node.confidence * 100).toFixed(0)}% | **Status:** ${node.status} | **Duration:** ${(node.duration_ms / 1000).toFixed(1)}s | **Time:** ${new Date(node.timestamp).toLocaleTimeString()}\n`,
        node.confidence_reasoning ? `\n**Score Reasoning:** ${node.confidence_reasoning}\n` : '',
        node.reasoning ? `\n**Agent Reasoning:** ${node.reasoning}\n` : '',
        node.investigator_notes ? `\n**Investigator Notes:** ${node.investigator_notes}\n` : '',
        (node.tags || []).length > 0 ? `\n**Tags:** ${node.tags.join(', ')}\n` : '',
      ],
    })

    // Code cell with query
    if (node.query) {
      cells.push({
        cell_type: 'code',
        metadata: cellMeta,
        source: [node.query],
        outputs: node.result_raw
          ? [{ output_type: 'stream', name: 'stdout', text: [node.result_raw] }]
          : [],
        execution_count: null,
      })
    }
  }

  // Add summary cell at the end
  const maxConf = getMaxConfidence(sortedNodes)
  const highNodes = sortedNodes.filter(n => n.confidence > 0.5)
  const sevNodes = sortedNodes.filter(n => (n.tags || []).some(t => t.startsWith('SEV-')))
  cells.push({
    cell_type: 'markdown',
    metadata: { summary: true },
    source: [
      `---\n`,
      `# Investigation Summary\n`,
      `\n`,
      `**Nodes explored:** ${sortedNodes.length}\n`,
      `**Max confidence:** ${(maxConf * 100).toFixed(0)}%\n`,
      highNodes.length > 0 ? `**High-confidence findings:** ${highNodes.map(n => `${n.label} (${(n.confidence * 100).toFixed(0)}%)`).join(', ')}\n` : '',
      sevNodes.length > 0 ? `**SEV findings:** ${sevNodes.flatMap(n => (n.tags || []).filter(t => t.startsWith('SEV-'))).join(', ')}\n` : '',
      `**Skills used:** ${session.skills_used.join(', ') || 'None'}\n`,
      `\n`,
      `_Generated by Juniper at ${new Date().toISOString()}_\n`,
    ],
  })

  const notebook = {
    nbformat: 4,
    nbformat_minor: 5,
    metadata: {
      kernelspec: { display_name: 'Juniper', language: 'sql', name: 'workbench' },
      investigation_id: session.id,
      investigation_name: session.name,
      max_confidence: maxConf,
      sev_findings: sevNodes.flatMap(n => (n.tags || []).filter(t => t.startsWith('SEV-'))),
    },
    cells,
  }

  return JSON.stringify(notebook, null, 2)
}

/**
 * Export as playbook contribution (R54).
 * Extracts the decision path from root to final recommendation,
 * formatted as a playbook branch compatible with the living playbooks system.
 */
export function exportPlaybookContribution(session: Session): string {
  const path = extractDecisionPath(session.nodes, session.edges)
  const nodes = session.nodes
  const maxConf = getMaxConfidence(Object.values(nodes))

  // Find the highest-confidence leaf path (the "critical path" of the investigation)
  const criticalPath = findCriticalPath(nodes, session.edges)

  const playbook = {
    version: '1.0',
    type: 'playbook_contribution',
    exported_at: new Date().toISOString(),
    source_investigation: {
      id: session.id,
      name: session.name,
      date: session.created_at,
      starting_input: session.starting_input,
      starting_input_type: session.starting_input_type,
      verdict_confidence: maxConf,
    },
    decision_tree: criticalPath.map((nodeId, idx) => {
      const node = nodes[nodeId]
      if (!node) return null
      const children = session.edges.filter((e) => e.source === nodeId).map((e) => e.target)
      return {
        step: idx + 1,
        action_type: node.action_type,
        skill_used: node.skill_name,
        tool_used: node.tool_name,
        description: node.label || node.action_type,
        query_template: node.query,
        expected_signal: node.result_summary,
        severity_at_step: node.confidence,
        confidence: node.confidence,
        branches: children.length,
        investigator_notes: node.investigator_notes || null,
      }
    }).filter(Boolean),
    skills_sequence: session.skills_used,
    tools_required: session.tools_used,
    total_steps: path.length,
    critical_path_length: criticalPath.length,
  }

  return JSON.stringify(playbook, null, 2)
}

/** Find the path from root to the highest-confidence leaf */
function findCriticalPath(
  nodes: Record<string, InvestigationNode>,
  edges: InvestigationEdge[],
): string[] {
  const nodeList = Object.values(nodes)
  const roots = nodeList.filter((n) => n.parent_ids.length === 0)
  if (roots.length === 0) return []

  let bestLeaf: InvestigationNode | null = null
  let bestConf = -1
  for (const node of nodeList) {
    const children = edges.filter((e) => e.source === node.node_id)
    const isLeaf = children.length === 0
    if (isLeaf && node.confidence > bestConf) {
      bestConf = node.confidence
      bestLeaf = node
    }
  }

  if (!bestLeaf) return roots.map((r) => r.node_id)

  // Trace back from leaf to root
  const path: string[] = []
  let current: InvestigationNode | undefined = bestLeaf
  const visited = new Set<string>()
  while (current && !visited.has(current.node_id)) {
    visited.add(current.node_id)
    path.unshift(current.node_id)
    if ((current.parent_ids || []).length > 0) {
      current = nodes[(current.parent_ids || [])[0]]
    } else {
      break
    }
  }

  return path
}

function getMaxConfidence(nodes: InvestigationNode[]): number {
  let max = 0
  for (const node of nodes) {
    if (node.confidence > max) max = node.confidence
  }
  return max
}

/**
 * Export as Google Docs-ready text (no markdown syntax, clean prose).
 * Suitable for pasting into Google Docs, Confluence, or email.
 */
export function exportGoogleDocsText(session: Session): string {
  let doc = ''
  doc += `INVESTIGATION: ${session.name}\n`
  doc += `Date: ${new Date(session.created_at).toLocaleDateString()}\n`
  doc += `\n${'='.repeat(60)}\n\n`

  // Use Claude's analytical findings as primary content
  const findings = extractAnalyticalFindings(session.messages || [])
  if (findings.length > 0) {
    doc += `SUMMARY\n${'-'.repeat(40)}\n\n`
    // Strip markdown formatting for clean Google Docs text
    const clean = (s: string) => s.replace(/\*\*([^*]+)\*\*/g, '$1').replace(/\*([^*]+)\*/g, '$1').replace(/`([^`]+)`/g, '$1')
    doc += clean(findings[findings.length - 1]) + '\n\n'

    if (findings.length > 1) {
      doc += `DETAILED ANALYSIS\n${'-'.repeat(40)}\n\n`
      for (const f of findings.slice(0, -1).slice(-5)) {
        doc += clean(f) + '\n\n'
      }
    }
  }

  // Fallback: node-level details if no analytical findings
  if (findings.length === 0) {
    const path = extractDecisionPath(session.nodes, session.edges)
    for (const step of path) {
      const node = session.nodes[step.node_id]
      if (!node) continue

      doc += `${node.label || node.action_type}\n`
      doc += `-`.repeat(40) + '\n'
      if (node.result_summary) doc += `${node.result_summary}\n\n`
      if (node.reasoning) doc += `${node.reasoning}\n\n`
    }
  }

  doc += `${'='.repeat(60)}\n`
  doc += `Generated by Juniper\n`
  return doc
}

/**
 * Export as Slack-ready message using mrkdwn syntax.
 * Investigators can paste this directly into a Slack channel.
 */
export function exportSlackMessage(session: Session): string {
  const nodes = Object.values(session.nodes)
  const completed = nodes.filter(n => n.status === 'completed').length

  let msg = ''
  msg += `:mag: *Investigation: ${session.name}*\n`
  msg += `_${new Date(session.created_at).toLocaleDateString()} | ${completed} queries completed_\n\n`

  // Use Claude's analysis as primary content
  const findings = extractAnalyticalFindings(session.messages || [])
  if (findings.length > 0) {
    // Convert markdown bold to Slack bold, truncate for readability
    const slackify = (s: string) => s.replace(/\*\*([^*]+)\*\*/g, '*$1*').slice(0, 1500)
    msg += `:memo: *Findings:*\n${slackify(findings[findings.length - 1])}\n\n`
  } else {
    // Fallback to node summaries
    const highNodes = nodes.filter(n => n.confidence > 0.5)
    if (highNodes.length > 0) {
      msg += `:rotating_light: *Key Findings:*\n`
      for (const node of highNodes.sort((a, b) => b.confidence - a.confidence).slice(0, 5)) {
        msg += `> *${node.label}*: ${(node.result_summary || '').slice(0, 150)}\n`
      }
      msg += '\n'
    }
  }

  msg += `_Generated by Juniper_`
  return msg
}

/** Export investigation as a Jira ticket draft */
export function exportJiraTicketDraft(session: Session): string {
  const nodes = Object.values(session.nodes)
  const completed = nodes.filter(n => n.status === 'completed').length

  let ticket = ''
  ticket += `h2. Summary\n`
  ticket += `Investigation "${session.name}" — ${new Date(session.created_at).toLocaleDateString()}\n`
  ticket += `${completed} queries completed.\n\n`

  // Use Claude's analysis as primary content
  const findings = extractAnalyticalFindings(session.messages || [])
  if (findings.length > 0) {
    ticket += `h2. Findings\n`
    // Strip markdown for Jira wiki format
    const clean = (s: string) => s.replace(/\*\*([^*]+)\*\*/g, '*$1*').replace(/`([^`]+)`/g, '{{$1}}')
    ticket += clean(findings[findings.length - 1]) + '\n\n'
    if (findings.length > 1) {
      ticket += `h2. Detailed Analysis\n`
      for (const f of findings.slice(0, -1).slice(-3)) {
        ticket += clean(f) + '\n\n'
      }
    }
  } else {
    // Fallback to node summaries
    const highNodes = nodes.filter(n => n.confidence > 0.5).sort((a, b) => b.confidence - a.confidence)
    if (highNodes.length > 0) {
      ticket += `h2. Findings\n`
      for (const node of highNodes) {
        ticket += `* *${node.label}*: ${node.result_summary || ''}\n`
      }
      ticket += '\n'
    }
  }

  // SEV Assessment
  const sorted = nodes.filter(n => n.status === 'completed')
  const allSevs = sorted.flatMap(n => checkSevThresholds(n.result_raw, n.label))
  const topSev = allSevs.filter(s => s.sevLevel !== null).sort((a, b) => (a.sevLevel || 99) - (b.sevLevel || 99))
  if (topSev.length > 0) {
    ticket += `h2. SEV Assessment\n`
    ticket += `*Highest SEV detected: SEV-${topSev[0].sevLevel}*\n`
    for (const s of topSev.slice(0, 5)) {
      ticket += `* ${formatSevAssessment(s)}\n`
    }
    ticket += '\n'
  }

  ticket += `\n_Auto-generated by Juniper_\n`
  return ticket
}

/** Generate a handoff prompt that can continue this investigation in a new session */
export function generateHandoffPrompt(session: Session): string {
  const nodes = Object.values(session.nodes)
  const highNodes = nodes.filter(n => n.confidence > 0.4).sort((a, b) => b.confidence - a.confidence)
  const maxConf = getMaxConfidence(nodes)

  let prompt = `Continue the investigation "${session.name}" from ${new Date(session.created_at).toLocaleDateString()}.\n\n`
  prompt += `## Previous findings:\n`

  if (highNodes.length > 0) {
    for (const n of highNodes.slice(0, 5)) {
      prompt += `- ${n.label} (${(n.confidence * 100).toFixed(0)}%): ${n.result_summary || 'No summary'}\n`
      if (n.query) prompt += `  Query: ${n.query.slice(0, 150)}\n`
    }
  } else {
    prompt += `No high-confidence findings yet. Previous steps explored: ${nodes.map(n => n.label).slice(0, 5).join(', ')}\n`
  }

  prompt += `\n## Next steps:\n`
  if (maxConf > 0.5) {
    prompt += `The investigation found signals worth pursuing. Dig deeper into the high-confidence findings above.\n`
    prompt += `Consider: impact assessment, member restriction status, SEV assessment.\n`
  } else {
    prompt += `Previous investigation was inconclusive. Try different angles:\n`
    prompt += `- Different date ranges\n- Related abuse vectors\n- Alternative data sources\n`
  }

  prompt += `\nSkills used: ${session.skills_used.join(', ') || 'None'}\n`
  prompt += `Tools used: ${session.tools_used.join(', ') || 'None'}\n`

  return prompt
}

/** Export investigation as a chronological timeline narrative for incident reports */
export function exportTimelineNarrative(session: Session): string {
  const nodes = Object.values(session.nodes)
    .filter(n => n.status === 'completed')
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())

  const maxConf = getMaxConfidence(Object.values(session.nodes))
  const highNodes = nodes.filter(n => n.confidence > 0.5)

  let narrative = `# Investigation Timeline: ${session.name}\n`
  narrative += `**Date:** ${new Date(session.created_at).toLocaleDateString()} | **Nodes:** ${nodes.length} | **Max Score:** ${(maxConf * 100).toFixed(0)}%\n\n`
  narrative += `---\n\n`

  // Group nodes by time (5-minute buckets)
  let lastBucket = ''
  for (const node of nodes) {
    const ts = new Date(node.timestamp)
    const bucket = `${ts.getHours().toString().padStart(2, '0')}:${(Math.floor(ts.getMinutes() / 5) * 5).toString().padStart(2, '0')}`

    if (bucket !== lastBucket) {
      narrative += `## ${ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}\n\n`
      lastBucket = bucket
    }

    const score = (node.confidence * 100).toFixed(0)
    const scoreLabel = node.confidence > 0.6 ? ' [HIGH]' : node.confidence > 0.3 ? ' [MEDIUM]' : ''

    narrative += `**${node.label}**${scoreLabel} — ${score}%\n`
    if (node.reasoning) {
      narrative += `> Reasoning: ${node.reasoning.slice(0, 150)}\n`
    }
    if (node.result_summary) {
      narrative += `> Finding: ${node.result_summary}\n`
    }
    if (node.query && node.tool_name) {
      narrative += `> Tool: ${node.tool_name} (${(node.duration_ms / 1000).toFixed(1)}s)\n`
    }
    if ((node.tags || []).length > 0) {
      narrative += `> Tags: ${(node.tags || []).join(', ')}\n`
    }
    if (node.investigator_notes) {
      narrative += `> Notes: ${node.investigator_notes.split('\n\n')[0]}\n`
    }
    narrative += '\n'
  }

  // Conclusion
  narrative += `---\n\n## Assessment\n\n`
  if (highNodes.length > 0) {
    narrative += `Investigation identified **${highNodes.length} high-confidence finding(s)**:\n\n`
    for (const n of highNodes.sort((a, b) => b.confidence - a.confidence)) {
      narrative += `- **${n.label}** (${(n.confidence * 100).toFixed(0)}%): ${n.result_summary || 'See node details'}\n`
    }
  } else {
    narrative += `No high-confidence findings detected. Investigation may be inconclusive or require additional data.\n`
  }

  narrative += `\n---\n_Generated by Juniper at ${new Date().toISOString()}_\n`
  return narrative
}

/** Generate a complete investigation audit report (combines all findings) */
export function generateAuditReport(session: Session): string {
  const nodes = Object.values(session.nodes)
  const sorted = nodes
    .filter(n => n.status === 'completed')
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())

  // Calculate investigation duration
  const durationMs = new Date(session.updated_at).getTime() - new Date(session.created_at).getTime()
  const fmtDuration = (ms: number) => {
    const s = Math.floor(ms / 1000)
    if (s < 60) return `${s}s`
    const m = Math.floor(s / 60)
    return m < 60 ? `${m}m` : `${Math.floor(m / 60)}h ${m % 60}m`
  }

  let report = `# Investigation Audit Report\n\n`
  report += `**Investigation:** ${session.name}\n`
  report += `**Date:** ${new Date(session.created_at).toLocaleDateString()}\n`
  report += `**Duration:** ${fmtDuration(durationMs)}\n\n`

  // Primary content: Claude's analytical findings from messages
  const findings = extractAnalyticalFindings(session.messages || [])
  if (findings.length > 0) {
    report += `## Summary\n\n`
    report += findings[findings.length - 1] + '\n\n'

    if (findings.length > 1) {
      report += `## Detailed Analysis\n\n`
      for (const f of findings.slice(0, -1).slice(-5)) {
        report += f + '\n\n'
      }
    }
  }

  // SEV Assessment
  const allSevs = sorted.flatMap(n => checkSevThresholds(n.result_raw, n.label))
  const topSev = allSevs.filter(s => s.sevLevel !== null).sort((a, b) => (a.sevLevel || 99) - (b.sevLevel || 99))
  if (topSev.length > 0) {
    report += `## SEV Assessment\n\n`
    report += `**Highest SEV detected: SEV-${topSev[0].sevLevel}**\n\n`
    for (const s of topSev.slice(0, 5)) {
      report += `- ${formatSevAssessment(s)}\n`
    }
    report += '\n'
  }

  // Extracted IOCs
  const allCohort = sorted.reduce((acc, n) => {
    const c = extractCohort(n.result_raw)
    c.memberIds.forEach(id => acc.memberIds.add(id))
    c.ips.forEach(ip => acc.ips.add(ip))
    c.domains.forEach(d => acc.domains.add(d))
    return acc
  }, { memberIds: new Set<string>(), ips: new Set<string>(), domains: new Set<string>() })

  const hasEntities = allCohort.memberIds.size > 0 || allCohort.ips.size > 0 || allCohort.domains.size > 0
  if (hasEntities) {
    report += `## Extracted Entities\n\n`
    if (allCohort.memberIds.size > 0) report += `**Member IDs (${allCohort.memberIds.size}):** ${[...allCohort.memberIds].slice(0, 20).join(', ')}${allCohort.memberIds.size > 20 ? ' ...' : ''}\n\n`
    if (allCohort.ips.size > 0) report += `**IPs (${allCohort.ips.size}):** ${[...allCohort.ips].slice(0, 15).join(', ')}${allCohort.ips.size > 15 ? ' ...' : ''}\n\n`
    if (allCohort.domains.size > 0) report += `**Domains (${allCohort.domains.size}):** ${[...allCohort.domains].slice(0, 15).join(', ')}${allCohort.domains.size > 15 ? ' ...' : ''}\n\n`
  }

  // Fallback: if no analytical findings, show node-level details
  if (findings.length === 0 && sorted.length > 0) {
    report += `## Query Results\n\n`
    for (const n of sorted) {
      if (n.result_summary) {
        report += `**${n.label}:** ${n.result_summary}\n\n`
      }
    }
  }

  report += `---\n_Generated by Juniper_\n`
  return report
}

/** Export the investigation graph as a text tree (for quick sharing) */
export function exportGraphTree(session: Session): string {
  const nodes = session.nodes
  const edges = session.edges

  // Find root nodes
  const childIds = new Set(edges.map(e => e.target))
  const rootIds = Object.keys(nodes).filter(id => !childIds.has(id))

  let tree = `Investigation: ${session.name}\n`
  tree += `${'='.repeat(40)}\n\n`

  function renderNode(nodeId: string, prefix: string, isLast: boolean) {
    const node = nodes[nodeId]
    if (!node) return

    const connector = isLast ? '\u2514\u2500 ' : '\u251C\u2500 '
    const score = (node.confidence * 100).toFixed(0)
    const sevTag = (node.tags || []).find(t => t.startsWith('SEV-'))
    const sev = sevTag ? ` [${sevTag}]` : ''
    const summary = node.result_summary ? ` — ${node.result_summary.slice(0, 60)}` : ''

    tree += `${prefix}${connector}${node.label} (${score}%)${sev}${summary}\n`

    // Find children
    const children = edges.filter(e => e.source === nodeId).map(e => e.target)
    const childPrefix = prefix + (isLast ? '   ' : '\u2502  ')
    children.forEach((childId, i) => {
      renderNode(childId, childPrefix, i === children.length - 1)
    })
  }

  for (const rootId of rootIds) {
    renderNode(rootId, '', true)
  }

  return tree
}
