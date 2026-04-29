import { useState, useEffect } from 'react'
import { useGraphStore } from '../../store/graph'
import { useSessionStore } from '../../store/session'
import { miscApi } from '../../api'
import type { Skill } from '../../types'
import { SuggestedNextSteps } from './SuggestedNextSteps'
import { CohortSection } from './CohortSection'

interface NodeExploreTabProps {
  nodeId: string
}

export function NodeExploreTab({ nodeId }: NodeExploreTabProps) {
  const node = useGraphStore(s => s.nodes[nodeId])
  const selectNode = useGraphStore(s => s.selectNode)
  const setChatContext = useSessionStore(s => s.setChatContext)
  const [showSkillPicker, setShowSkillPicker] = useState(false)
  const [skills, setSkills] = useState<Skill[]>([])

  // Load skills for fan-out picker
  useEffect(() => {
    if (showSkillPicker && skills.length === 0) {
      miscApi.listSkills()
        .then((data: any) => setSkills([...data.investigation, ...data.action]))
        .catch(() => {})
    }
  }, [showSkillPicker, skills.length])

  if (!node) return null

  /** R22: Fan out with a specific skill from this node */
  const handleFanOutWithSkill = (skill: Skill) => {
    setChatContext({
      nodeId: node.node_id,
      label: node.label || node.action_type,
      query: node.query,
      result_summary: node.result_summary,
    })
    useSessionStore.getState().addMessage('system',
      `Skill **${skill.name}** selected for fan-out from node ${node.node_id.slice(0, 8)}. Context loaded.`
    )
    useSessionStore.getState().recordSkillUsed(skill.name)
    setShowSkillPicker(false)
    selectNode(null)
  }

  return (
    <>
      {/* Suggested next steps based on node content */}
      {node.status === 'completed' && node.confidence > 0 && (
        <div className="px-4 py-3 border-b border-surface-3">
          <SuggestedNextSteps node={node} onSelect={(prompt) => {
            setChatContext({
              nodeId: node.node_id,
              label: node.label || node.action_type,
              query: node.query,
              result_summary: node.result_summary,
              result_raw: node.result_raw,
            })
            useSessionStore.getState().addMessage('user', prompt)
            selectNode(null)
          }} />
        </div>
      )}

      {/* Extracted cohort entities */}
      {node.status === 'completed' && node.result_raw && (
        <CohortSection node={node} nodeId={nodeId} setChatContext={setChatContext} selectNode={selectNode} />
      )}

      {/* Fan-out skill picker (R22) */}
      <div className="px-4 py-3 border-b border-surface-3">
        <button
          onClick={() => setShowSkillPicker(!showSkillPicker)}
          className={`w-full text-xs py-2 rounded transition-colors ${
            showSkillPicker
              ? 'bg-accent-purple/30 text-accent-purple'
              : 'bg-accent-purple/20 text-accent-purple hover:bg-accent-purple/30'
          }`}
        >
          {showSkillPicker ? 'Hide skills' : 'Fan out with skill'}
        </button>
        {showSkillPicker && (
          <div className="mt-2">
            {skills.length === 0 ? (
              <p className="text-xs text-gray-500">Loading skills...</p>
            ) : (
              <div className="space-y-1 max-h-[200px] overflow-y-auto">
                {skills.map((skill) => (
                  <button
                    key={skill.name}
                    onClick={() => handleFanOutWithSkill(skill)}
                    className="w-full text-left bg-surface-2 hover:bg-surface-3 rounded px-2 py-1.5 transition-colors"
                  >
                    <div className="text-xs text-gray-200">{skill.name}</div>
                    {skill.description && (
                      <div className="text-[10px] text-gray-500 truncate">{skill.description}</div>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* R24: Auto-investigate from this node with depth control */}
      <div className="px-4 py-3">
        {(() => {
          const graph = useGraphStore.getState()
          const isAutoRunning = graph.autoInvestigateNodeId === nodeId
          const maxDepth = graph.maxAutoDepth
          return (
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  if (isAutoRunning) {
                    graph.stopAutoInvestigate()
                  } else {
                    graph.startAutoInvestigate(nodeId)
                    const estNodes = Math.min(15, Math.pow(2, maxDepth) - 1)
                    useSessionStore.getState().addMessage('system',
                      `Auto-investigate started from node ${nodeId.slice(0, 8)}. Depth: ${maxDepth}, ~${estNodes} nodes.`
                    )
                    selectNode(null)
                  }
                }}
                className={`flex-1 text-xs px-3 py-2 rounded transition-colors ${
                  isAutoRunning
                    ? 'bg-orange-900/30 text-orange-400 animate-pulse'
                    : 'bg-accent-cyan/20 text-accent-cyan hover:bg-accent-cyan/30'
                }`}
              >
                {isAutoRunning ? 'Stop auto-investigate' : 'Auto-investigate from here'}
              </button>
              {!isAutoRunning && (
                <select
                  value={maxDepth}
                  onChange={e => graph.setMaxAutoDepth(parseInt(e.target.value))}
                  className="bg-surface-3 text-[10px] text-gray-400 rounded px-1 py-1 focus:outline-none"
                  title="Investigation depth (levels)"
                >
                  {[3,5,8,10].map(d => <option key={d} value={d}>d{d}</option>)}
                </select>
              )}
            </div>
          )
        })()}
      </div>
    </>
  )
}
