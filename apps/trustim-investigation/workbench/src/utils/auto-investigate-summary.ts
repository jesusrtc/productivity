import { useGraphStore } from '../store/graph'
import { useSessionStore } from '../store/session'
import { INVESTIGATION_DIMENSIONS } from '../data/investigation-dimensions'

/** Generate and display summary when auto-investigate completes. */
export function handleAutoInvestigateComplete(): void {
  const graph = useGraphStore.getState()
  const allNodes = Object.values(graph.nodes)
  const completed = allNodes.filter(n => n.status === 'completed')
  const maxScore = Math.max(0, ...completed.map(n => n.confidence))
  const highScoreNodes = completed.filter(n => n.confidence > 0.5)
  const depth = allNodes.length > 0 ? Math.max(...allNodes.map(n => graph.getAncestors(n.node_id).length)) + 1 : 0

  const totalDuration = completed.reduce((sum, n) => sum + (n.duration_ms || 0), 0)
  const durationStr = totalDuration > 60000 ? `${(totalDuration / 60000).toFixed(1)}min` : `${(totalDuration / 1000).toFixed(1)}s`

  const parts = [
    `**Auto-investigation complete** in ${durationStr}.`,
    `${completed.length} nodes explored across ${depth} levels.`,
  ]

  if (highScoreNodes.length > 0) {
    parts.push(`\n\n### Key Findings (${highScoreNodes.length}):`)
    for (const n of highScoreNodes.sort((a, b) => b.confidence - a.confidence).slice(0, 5)) {
      const score = (n.confidence * 100).toFixed(0)
      parts.push(`- **${n.label}** (${score}%)${n.result_summary ? ': ' + n.result_summary.slice(0, 100) : ''}`)
    }
    if (highScoreNodes.length > 5) parts.push(`- ...and ${highScoreNodes.length - 5} more`)
  } else {
    parts.push('No high-score findings detected.')
  }

  // Overall assessment + checklist coverage
  const overallScore = maxScore > 0.7 ? 'Critical' : maxScore > 0.5 ? 'High' : maxScore > 0.3 ? 'Moderate' : 'Low'
  parts.push(`\n**Overall assessment:** ${overallScore} (max: ${(maxScore * 100).toFixed(0)}%)`)

  // Check investigation dimension coverage
  const nodeTexts = allNodes.map(n => [n.label, n.query, ...(n.tags || [])].join(' ').toLowerCase())
  const covered = INVESTIGATION_DIMENSIONS.filter(d => nodeTexts.some(t => d.keywords.some(kw => t.includes(kw))))
  const uncovered = INVESTIGATION_DIMENSIONS.filter(d => !covered.includes(d))
  parts.push(`\n**Checklist coverage:** ${covered.length}/8 dimensions`)
  if (uncovered.length > 0 && uncovered.length <= 4) {
    parts.push(`Unchecked: ${uncovered.map(d => d.label).join(', ')}`)
  }

  // Recommendation based on coverage + findings
  if (covered.length >= 6 && maxScore > 0.5) {
    parts.push(`\n**Recommendation:** Investigation is thorough with significant findings. Ready to publish (**Cmd+Shift+P**).`)
  } else if (covered.length >= 6 && maxScore <= 0.3) {
    parts.push(`\n**Recommendation:** Good coverage but no significant findings. Consider closing as benign or checking a different date range.`)
  } else if (uncovered.length > 0) {
    parts.push(`\nClick any node to continue, or open the **Checklist** (Cmd+Shift+I) to see remaining dimensions.`)
  } else {
    parts.push(`\nUse **Cmd+Shift+P** to publish the audit report.`)
  }

  // Link summary message to high-confidence nodes so they're clickable in chat
  const linkedNodeIds = highScoreNodes.sort((a, b) => b.confidence - a.confidence).slice(0, 5).map(n => n.node_id)
  useSessionStore.getState().addMessage('assistant', parts.join('\n'), { node_ids: linkedNodeIds })

  // Auto-prune: collapse low-scoring branches to focus attention on findings
  const lowScoreLeaves = completed.filter(n =>
    n.confidence < 0.2 &&
    !n.pinned &&
    graph.getChildren(n.node_id).length === 0
  )
  if (lowScoreLeaves.length > 3) {
    const parentsToCollapse = new Set<string>()
    for (const leaf of lowScoreLeaves) {
      if ((leaf.parent_ids || [])[0] && graph.nodes[(leaf.parent_ids || [])[0]]) {
        const parent = graph.nodes[(leaf.parent_ids || [])[0]]
        if (parent.confidence < 0.2 && !parent.pinned) {
          parentsToCollapse.add((leaf.parent_ids || [])[0])
        }
      }
    }
    for (const pid of parentsToCollapse) {
      graph.toggleSubtreeCollapse(pid)
    }
    if (parentsToCollapse.size > 0) {
      useSessionStore.getState().addMessage('system',
        `Auto-collapsed ${parentsToCollapse.size} low-scoring branch(es) to focus on key findings. Expand them from the graph.`
      )
    }
  }

  // Auto-select the highest-confidence node so the drawer opens with the key finding
  if (highScoreNodes.length > 0) {
    const topNode = highScoreNodes[0]
    setTimeout(() => {
      useGraphStore.getState().selectNode(topNode.node_id)
    }, 500)
  }
}
