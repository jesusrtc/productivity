import { useEffect, useRef } from 'react'
import { useGraphStore } from '../../store/graph'
import { confidenceColor } from '../../types'

interface Props {
  nodeId: string
  x: number
  y: number
  onClose: () => void
  onCompare?: () => void
}

/** Context menu for right-clicking graph nodes (Section 7.3) */
export function NodeContextMenu({ nodeId, x, y, onClose, onCompare }: Props) {
  const node = useGraphStore((s) => s.nodes[nodeId])
  const selectNode = useGraphStore((s) => s.selectNode)
  const toggleSubtreeCollapse = useGraphStore((s) => s.toggleSubtreeCollapse)
  const markDeadEnd = useGraphStore((s) => s.markDeadEnd)
  const overrideConfidence = useGraphStore((s) => s.overrideConfidence)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as HTMLElement)) {
        onClose()
      }
    }
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleEsc)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleEsc)
    }
  }, [onClose])

  if (!node) return null

  const items: { label: string; action: () => void; className?: string }[] = [
    {
      label: 'Branch from here',
      action: () => {
        // Actually set the chat context — not just select the node
        import('../../store/session').then(({ useSessionStore }) => {
          useSessionStore.getState().setChatContext({
            nodeId: node.node_id,
            label: node.label || node.action_type,
            query: node.query,
            result_summary: node.result_summary,
            result_raw: node.result_raw,
          })
        })
        selectNode(null) // Close drawer so chat is visible
        onClose()
        // Focus chat input
        setTimeout(() => {
          const textarea = document.querySelector('textarea') as HTMLTextAreaElement
          if (textarea) textarea.focus()
        }, 100)
      },
      className: 'text-accent-blue font-medium',
    },
    ...(node.status === 'completed' ? [{
      label: 'Auto-continue (dig deeper)',
      action: () => {
        const prompt = node.confidence > 0.5
          ? `Continue investigating "${node.label}". The previous step found high-confidence signals (${(node.confidence * 100).toFixed(0)}%). Dig deeper — confirm the pattern, check related signals, and assess impact.`
          : `Continue investigating from "${node.label}". Run a different angle — try a related query or check a different investigation dimension.`
        window.dispatchEvent(new CustomEvent('executeFromNode', {
          detail: { query: prompt, parentNodeId: nodeId, label: `Continue: ${node.label}` }
        }))
        onClose()
      },
      className: 'text-accent-cyan',
    }] : []),
    {
      label: node.subtree_collapsed ? 'Expand subtree' : 'Collapse subtree',
      action: () => { toggleSubtreeCollapse(nodeId); onClose() },
    },
    {
      label: node.is_dead_end
        ? 'Reopen branch'
        : useGraphStore.getState().autoInvestigateNodeId
          ? 'Stop this branch'
          : 'Mark as dead end',
      action: () => { markDeadEnd(nodeId); onClose() },
      className: node.is_dead_end ? 'text-green-400' : 'text-red-400',
    },
    {
      label: node.status === 'needs_review' ? 'Clear review flag' : 'Flag for review',
      action: () => {
        useGraphStore.getState().updateNodeStatus(
          nodeId,
          node.status === 'needs_review' ? 'completed' : 'needs_review'
        )
        onClose()
      },
      className: 'text-yellow-400',
    },
  ]

  // Copy investigation path as text
  items.push({
    label: 'Copy investigation path',
    action: () => {
      const graph = useGraphStore.getState()
      const ancestors = graph.getAncestors(nodeId)
      const path = [...ancestors.reverse(), nodeId]
      const text = path.map((id, i) => {
        const n = graph.nodes[id]
        if (!n) return `${i + 1}. [unknown]`
        const score = `${(n.confidence * 100).toFixed(0)}%`
        return `${i + 1}. ${n.label} [${score}]${n.result_summary ? ` — ${n.result_summary.slice(0, 80)}` : ''}`
      }).join('\n')
      navigator.clipboard.writeText(`Investigation Path:\n${text}`)
      onClose()
    },
  })

  // Copy this node's finding as text
  if (node.status === 'completed' && node.result_summary) {
    items.push({
      label: 'Copy finding',
      action: () => {
        const score = (node.confidence * 100).toFixed(0)
        const sevTag = (node.tags || []).find((t: string) => t.startsWith('SEV-'))
        const text = [
          `**${node.label}** (${score}%)${sevTag ? ` [${sevTag}]` : ''}`,
          node.result_summary,
          node.query ? `Query: ${node.query.slice(0, 200)}` : '',
        ].filter(Boolean).join('\n')
        navigator.clipboard.writeText(text)
        onClose()
      },
    })
  }

  // Pin/unpin
  items.push({
    label: node.pinned ? 'Unpin node' : 'Pin node (stays visible when collapsed)',
    action: () => { useGraphStore.getState().togglePin(nodeId); onClose() },
    className: node.pinned ? 'text-accent-cyan' : 'text-gray-300',
  })

  // Add "Compare with selected" if another node is selected
  if (onCompare) {
    items.push({
      label: 'Compare branches with selected',
      action: onCompare,
      className: 'text-accent-purple',
    })
  }

  return (
    <div
      ref={menuRef}
      className="fixed bg-surface-2 border border-surface-4 rounded-lg shadow-2xl py-1 z-[200] min-w-[180px]"
      style={{ left: x, top: y }}
    >
      {items.map((item, i) => (
        <button
          key={i}
          onClick={item.action}
          className={`w-full text-left px-3 py-1.5 text-xs hover:bg-surface-3 transition-colors ${item.className || 'text-gray-300'}`}
        >
          {item.label}
        </button>
      ))}

      <div className="border-t border-surface-4 my-1" />
      <div className="px-3 py-1 text-[10px] text-gray-500 uppercase">Override confidence</div>
      <div className="px-3 pb-1 flex gap-1">
        {[0, 0.2, 0.4, 0.6, 0.8, 1.0].map((c) => (
          <button
            key={c}
            onClick={() => { overrideConfidence(nodeId, c); onClose() }}
            className="px-1.5 py-0.5 text-[10px] rounded hover:opacity-80 transition-opacity"
            style={{
              backgroundColor: confidenceColor(c) + '30',
              color: confidenceColor(c),
            }}
            title={`${(c * 100).toFixed(0)}%`}
          >
            {(c * 100).toFixed(0)}%
          </button>
        ))}
      </div>

      <div className="border-t border-surface-4 my-1" />
      <button
        onClick={() => {
          // Export as a full standalone investigation (importable)
          const graph = useGraphStore.getState()
          const subtreeIds = graph.getSubtree(nodeId)
          // Also include ancestors up to root for full context chain
          const ancestors = graph.getAncestors(nodeId)
          const allIds = new Set([...ancestors, ...subtreeIds])
          const branchNodes: Record<string, typeof graph.nodes[string]> = {}
          for (const id of allIds) {
            if (graph.nodes[id]) branchNodes[id] = graph.nodes[id]
          }
          const branchEdges = graph.edges.filter(e => allIds.has(e.source) && allIds.has(e.target))

          const exported = {
            id: `branch-${nodeId.slice(0, 8)}-${Date.now()}`,
            name: `Branch: ${graph.nodes[nodeId]?.label || nodeId.slice(0, 8)}`,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            starting_input: graph.nodes[ancestors[ancestors.length - 1] || nodeId]?.query || '',
            starting_input_type: 'none' as const,
            nodes: branchNodes,
            edges: branchEdges,
            messages: [],
            skills_used: [],
            tools_used: [],
            mcp_tools: [],
          }

          const blob = new Blob([JSON.stringify(exported, null, 2)], { type: 'application/json' })
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = `investigation-branch-${nodeId.slice(0, 8)}.json`
          a.click()
          URL.revokeObjectURL(url)
          onClose()
        }}
        className="w-full text-left px-3 py-1.5 text-xs text-gray-300 hover:bg-surface-3 transition-colors"
      >
        Export this branch
      </button>

      {/* Convergence: create a synthesis node from this + siblings (Section 8.2) */}
      <button
        onClick={() => {
          const graph = useGraphStore.getState()
          const node = graph.nodes[nodeId]
          if (!node) { onClose(); return }

          // Find sibling leaf nodes (nodes with same parent that are completed)
          const siblings = node.parent_ids.length > 0
            ? Object.values(graph.nodes).filter(
                (n) => n.node_id !== nodeId
                  && n.parent_ids.some((pid) => node.parent_ids.includes(pid))
                  && n.status === 'completed'
              )
            : []

          const parentIds = [nodeId, ...siblings.map((s) => s.node_id)]
          const summaries = parentIds
            .map((id) => graph.nodes[id]?.result_summary || graph.nodes[id]?.label || id.slice(0, 8))
            .join('; ')

          const synthId = graph.addNode({
            action_type: 'recommendation',
            label: `Synthesis: ${parentIds.length} branches`,
            query: `Synthesize findings from: ${summaries}`,
            parent_ids: parentIds,
            status: 'completed',
            result_summary: `Merged findings from ${parentIds.length} investigation branches.`,
            result_raw: `Convergence node synthesizing:\n${parentIds.map((id) => `- ${graph.nodes[id]?.label || id}`).join('\n')}`,
            reasoning: 'Investigator-created convergence node to merge multiple investigation branches.',
            confidence: node.confidence,
          })

          for (const pid of parentIds) {
            graph.addEdge(pid, synthId, 'supports')
          }

          selectNode(synthId)
          onClose()
        }}
        className="w-full text-left px-3 py-1.5 text-xs text-accent-cyan hover:bg-surface-3 transition-colors"
      >
        Synthesize findings (merge branches)
      </button>
    </div>
  )
}
