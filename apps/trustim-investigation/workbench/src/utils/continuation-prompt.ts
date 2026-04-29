import { INVESTIGATION_DIMENSIONS } from '../data/investigation-dimensions'
import { extractCohort, formatCohortForSQL } from './cohort-extraction'
import { useGraphStore } from '../store/graph'

/**
 * Build a continuation prompt for auto-investigate based on:
 * 1. Parent node's findings and extracted entities
 * 2. Investigation checklist — routes to the highest-priority uncovered dimension
 */
export function buildContinuationPrompt(parent: { label: string; query: string; result_summary: string; result_raw: string; confidence: number; action_type: string; tags?: string[] }): string {
  const findings = parent.result_summary || parent.label
  const score = (parent.confidence * 100).toFixed(0)
  const tags = (parent.tags || []).length > 0 ? ` Tags: ${(parent.tags || []).join(', ')}.` : ''

  // Extract cohort entities for context
  const cohort = extractCohort(parent.result_raw)
  let cohortContext = ''
  if (cohort.memberIds.length > 0) cohortContext += ` Member IDs: ${formatCohortForSQL(cohort.memberIds.slice(0, 10), 'number')}.`
  if (cohort.ips.length > 0) cohortContext += ` IPs: ${cohort.ips.slice(0, 5).join(', ')}.`
  if (cohort.domains.length > 0) cohortContext += ` Domains: ${cohort.domains.slice(0, 5).join(', ')}.`

  // Check which investigation dimensions are already covered
  const allNodes = useGraphStore.getState().nodes
  const nodeTexts = Object.values(allNodes).map(n => [n.label, n.query, ...(n.tags || [])].join(' ').toLowerCase())
  const uncovered = INVESTIGATION_DIMENSIONS.filter(d =>
    !nodeTexts.some(t => d.keywords.some(kw => t.includes(kw)))
  )

  // Build prompt: use the most relevant uncovered dimension
  const context = `Previous step: "${parent.label}" (${score}%).${tags} Findings: ${findings}.${cohortContext}`

  if (uncovered.length > 0) {
    // Run up to 2 dimensions in parallel for faster coverage
    const toRun = uncovered.slice(0, Math.min(2, uncovered.length))
    if (toRun.length === 1) {
      return `${context}\n\nNext: ${toRun[0].prompt}\n\nUse execute_trino_query. Always SET SESSION li_authorization_user = 'trustim'.`
    }
    // Parallel: ask Claude to run both queries in the same turn (creates sibling nodes)
    return `${context}\n\nRun these 2 investigation steps IN PARALLEL (both in this response):\n1. ${toRun[0].prompt}\n2. ${toRun[1].prompt}\n\nUse execute_trino_query for each. Always SET SESSION li_authorization_user = 'trustim'.`
  }

  // All dimensions covered — focus on the strongest signal
  if (parent.confidence > 0.6) {
    return `${context}\n\nAll investigation dimensions are covered. Focus on the highest-confidence finding and assess overall impact. Summarize key signals for the audit trail.`
  }

  return `${context}\n\nAll investigation dimensions checked. Look for any remaining patterns or cross-correlations between findings.`
}
