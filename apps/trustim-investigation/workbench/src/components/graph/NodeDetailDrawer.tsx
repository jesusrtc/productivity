import { useState, useEffect } from 'react'
import { useGraphStore } from '../../store/graph'
import { useSessionStore } from '../../store/session'
import { api } from '../../api/client'
import { ACTION_TYPE_ICONS } from '../../types'
import { NodeOverviewTab } from './NodeOverviewTab'
import { NodeExploreTab } from './NodeExploreTab'
import { NodeNotesTab } from './NodeNotesTab'
import { ResultSection } from './ResultSection'

interface Props {
  nodeId: string
}

type DrawerTab = 'overview' | 'result' | 'notes' | 'explore'
const TABS: { key: DrawerTab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'result', label: 'Result' },
  { key: 'notes', label: 'Notes' },
  { key: 'explore', label: 'Explore' },
]

/** Expanded node view as a slide-out drawer (Section 7.2) */
export function NodeDetailDrawer({ nodeId }: Props) {
  const node = useGraphStore((s) => s.nodes[nodeId])
  const selectNode = useGraphStore((s) => s.selectNode)
  const toggleSubtreeCollapse = useGraphStore((s) => s.toggleSubtreeCollapse)
  const markDeadEnd = useGraphStore((s) => s.markDeadEnd)
  const setChatContext = useSessionStore((s) => s.setChatContext)
  const [activeTab, setActiveTab] = useState<DrawerTab>('overview')

  // Reset to overview when a different node is selected
  useEffect(() => { setActiveTab('overview') }, [nodeId])

  // Escape is handled by App.tsx Escape chain — no duplicate handler needed

  if (!node) return null

  /** R21: Continue investigating from this node */
  const handleContinueFromHere = () => {
    setChatContext({
      nodeId: node.node_id,
      label: node.label || node.action_type,
      query: node.query,
      result_summary: node.result_summary,
      result_raw: node.result_raw,
    })
    selectNode(null) // Close drawer so chat is visible
  }

  return (
    <div className="absolute right-0 top-0 h-full w-[420px] bg-surface-1 border-l border-surface-3 shadow-2xl z-50 flex flex-col overflow-hidden" role="complementary" aria-label={`Node details: ${node.label || node.action_type}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-surface-3 flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-lg">{ACTION_TYPE_ICONS[node.action_type]}</span>
          <div className="min-w-0">
            <div className="text-[14px] font-medium text-gray-100 truncate">{node.label || node.action_type}</div>
            {node.parent_ids?.[0] && (() => {
              const parent = useGraphStore.getState().nodes[(node.parent_ids || [])[0]]
              return parent ? <div className="text-[10px] text-gray-600 truncate">from: {parent.label?.slice(0, 40)}</div> : null
            })()}
            <div className="text-[11px] text-gray-500 flex items-center gap-1.5">
              <span className="tabular-nums">{new Date(node.timestamp).toLocaleTimeString()}</span>
              {node.duration_ms > 0 && (
                <>
                  <span className="text-gray-600">|</span>
                  <span className="tabular-nums">{(node.duration_ms / 1000).toFixed(1)}s</span>
                </>
              )}
              {node.tool_name && (
                <>
                  <span className="text-gray-600">|</span>
                  <span className="text-accent-cyan/70">{node.tool_name}</span>
                </>
              )}
            </div>
          </div>
        </div>
        <button
          onClick={() => selectNode(null)}
          className="text-gray-400 hover:text-gray-200 text-lg leading-none"
          title="Close (Esc)"
        >
          {'\u2715'}
        </button>
      </div>

      {/* Tab navigation */}
      <div className="flex border-b border-surface-3 flex-shrink-0">
        {TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex-1 text-[11px] py-2 transition-colors ${
              activeTab === tab.key
                ? 'text-accent-blue border-b-2 border-accent-blue font-medium'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content — scrollable */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'overview' && <NodeOverviewTab nodeId={nodeId} />}
        {activeTab === 'result' && <ResultSection node={node} />}
        {activeTab === 'notes' && <NodeNotesTab nodeId={nodeId} />}
        {activeTab === 'explore' && <NodeExploreTab nodeId={nodeId} />}
      </div>

      {/* Action bar */}
      <div className="px-4 py-3 border-t border-surface-3 flex-shrink-0">
        {/* Retry banner for failed nodes — PRD Section 11 */}
        {node.status === 'failed' && (
          <div className="flex items-center gap-2 mb-2 bg-red-900/20 border border-red-900/30 rounded-lg px-3 py-2">
            <span className="text-[12px] text-red-300 flex-1">
              This node failed{node.result_raw ? `: ${node.result_raw.slice(0, 80)}` : ''}
            </span>
            <button
              onClick={() => {
                setChatContext({
                  nodeId: (node.parent_ids || [])[0] || node.node_id,
                  label: node.label || node.action_type,
                  query: node.query,
                  result_summary: 'Retrying failed node',
                  result_raw: node.result_raw,
                })
                selectNode(null)
              }}
              className="text-[12px] bg-red-900/30 hover:bg-red-900/50 text-red-200 px-3 py-1 rounded-md transition-colors font-medium"
            >
              Retry
            </button>
            <button
              onClick={() => useGraphStore.getState().updateNodeStatus(nodeId, 'needs_review')}
              className="text-[12px] text-gray-400 hover:text-gray-200 px-2 py-1 transition-colors"
            >
              Dismiss
            </button>
          </div>
        )}
        {/* Terminate running node */}
        {node.status === 'running' && (
          <div className="flex items-center gap-2 mb-2 bg-yellow-900/20 border border-yellow-900/30 rounded-lg px-3 py-2">
            <span className="text-[12px] text-yellow-300 flex-1">This node is currently running</span>
            <button
              onClick={() => useGraphStore.getState().updateNode(nodeId, { status: 'failed', result_summary: 'Manually terminated by investigator' })}
              className="text-[12px] bg-red-900/30 hover:bg-red-900/50 text-red-200 px-3 py-1 rounded-md transition-colors font-medium"
            >
              Terminate
            </button>
          </div>
        )}
        {/* Primary actions row */}
        <div className="flex gap-2 mb-2">
          <button
            onClick={handleContinueFromHere}
            className="flex-1 text-[13px] bg-accent-blue/20 text-accent-blue hover:bg-accent-blue/30 py-2 rounded-lg transition-all active:scale-[0.98] font-medium"
          >
            Continue from here
          </button>
          {/* Re-run: send the same query through Claude again */}
          {node.query && node.status === 'completed' && (
            <button
              onClick={() => {
                setChatContext({
                  nodeId: node.node_id,
                  label: node.label || node.action_type,
                  query: node.query,
                  result_summary: node.result_summary,
                })
                useSessionStore.getState().addMessage('system',
                  `Re-running query from node ${node.node_id.slice(0, 8)}: ${node.label}`
                )
                selectNode(null)
              }}
              className="text-xs bg-surface-3 hover:bg-surface-4 text-gray-300 px-3 py-2 rounded-lg transition-all"
              title="Re-run this query as a new branch"
            >
              Re-run
            </button>
          )}
          {/* Save to notebook */}
          {node.query && (
            <button
              onClick={() => {
                const session = useSessionStore.getState().currentSession
                if (!session) return
                api.post('/api/notebook/append', {
                    sessionId: session.id,
                    sessionName: session.name,
                    nodeId: node.node_id,
                    label: node.label,
                    query: node.query,
                    resultRaw: node.result_raw,
                    severity: node.confidence > 0.6 ? 'high' : 'low',
                    timestamp: node.timestamp,
                  })
                  .then(() => {
                    useSessionStore.getState().addMessage('system', `Saved to investigation notebook.`)
                  })
                  .catch(() => {})
              }}
              className="text-xs bg-surface-3 hover:bg-surface-4 text-gray-300 px-3 py-2 rounded-lg transition-all"
              title="Save this query + result to the investigation notebook"
            >
              Save .ipynb
            </button>
          )}
        </div>
        {/* Secondary actions row */}
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={() => toggleSubtreeCollapse(nodeId)}
            className="text-xs bg-surface-3 hover:bg-surface-4 text-gray-400 px-2 py-1.5 rounded transition-colors"
          >
            {node.subtree_collapsed ? 'Expand' : 'Collapse'}
          </button>
          <button
            onClick={() => markDeadEnd(nodeId)}
            className={`text-xs px-2 py-1.5 rounded transition-colors ${
              node.is_dead_end
                ? 'bg-red-900/30 text-red-400'
                : 'bg-surface-3 hover:bg-surface-4 text-gray-400'
            }`}
          >
            {node.is_dead_end ? 'Reopen' : 'Dead end'}
          </button>
        </div>
        {/* Action buttons — for completed high-confidence nodes */}
        {node.status === 'completed' && node.confidence > 0.4 && (
          <div className="flex gap-2 mt-2 pt-2 border-t border-surface-3/50">
            <button
              onClick={() => {
                import('../../utils/export').then(({ exportJiraTicketDraft }) => {
                  import('../../store/session').then(({ useSessionStore: ss }) => {
                    const data = ss.getState().getSessionData()
                    if (data) {
                      navigator.clipboard.writeText(exportJiraTicketDraft(data))
                      import('../../store/toast').then(({ useToastStore }) =>
                        useToastStore.getState().addToast('Jira ticket draft copied', 'success', 2000)
                      )
                    }
                  })
                })
              }}
              className="text-[10px] bg-surface-3 hover:bg-surface-4 text-gray-400 px-2 py-1 rounded transition-colors"
              title="Copy Jira ticket draft from this investigation"
            >
              Create Jira
            </button>
            <button
              onClick={() => {
                setChatContext({
                  nodeId: node.node_id, label: node.label || '', query: node.query,
                  result_summary: node.result_summary, result_raw: node.result_raw,
                })
                window.dispatchEvent(new CustomEvent('prefillChat', {
                  detail: { text: `Based on these findings, create an audit trail Google Doc with title "Investigation: ${node.label}" and publish it using the publish-audit-trail skill.` }
                }))
                selectNode(null)
              }}
              className="text-[10px] bg-surface-3 hover:bg-surface-4 text-gray-400 px-2 py-1 rounded transition-colors"
              title="Publish findings as Google Doc audit trail"
            >
              Publish Doc
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
