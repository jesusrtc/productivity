import { useState, useEffect } from 'react'
import { miscApi } from '../../api'
import type { McpToolStatus, Skill } from '../../types'

interface Props {
  onClose: () => void
}

/**
 * MCP Tool Discovery and Status Panel (R57-R60)
 * Shows connected MCP tools, their status, and which tools each skill expects.
 */
export function McpStatusPanel({ onClose }: Props) {
  const [tools, setTools] = useState<McpToolStatus[]>([])
  const [skills, setSkills] = useState<Skill[]>([])
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null)

  useEffect(() => {
    // R57: Discover MCP tools from Claude Code config via server API
    miscApi.mcpTools()
      .then(setTools)
      .catch(() => {})

    miscApi.listSkills()
      .then((data: any) => setSkills([...data.investigation, ...data.action]))
      .catch(() => {})
  }, [])

  const statusColor = (status: McpToolStatus['status']) =>
    status === 'healthy' ? 'bg-green-400' :
    status === 'degraded' ? 'bg-yellow-400' :
    'bg-red-400'

  const statusText = (status: McpToolStatus['status']) =>
    status === 'healthy' ? 'text-green-400' :
    status === 'degraded' ? 'text-yellow-400' :
    'text-red-400'

  // R60: Check which tools a skill expects
  const getSkillToolWarnings = (skill: Skill) => {
    const missing: string[] = []
    const toolNames = tools.map(t => t.name)
    for (const required of skill.allowed_tools) {
      if (required === 'Bash') continue // Bash is always available
      // Check if any MCP tool matches
      if (!toolNames.some(t => t.toLowerCase().includes(required.toLowerCase()))) {
        missing.push(required)
      }
    }
    return missing
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[100]" onClick={onClose}>
      <div className="bg-surface-1 border border-surface-3 rounded-xl p-6 w-[500px] max-h-[80vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-medium text-gray-200">MCP Tools Status</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-200">
            {'\u2715'}
          </button>
        </div>

        {/* Connected tools (R57, R58) */}
        <div className="mb-4">
          <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">
            Connected Tools ({tools.length})
          </h3>
          <div className="space-y-1 max-h-[200px] overflow-y-auto">
            {tools.map((tool) => (
              <div key={tool.name} className="flex items-center gap-2 bg-surface-2 rounded px-3 py-1.5">
                <div className={`w-1.5 h-1.5 rounded-full ${statusColor(tool.status)}`} />
                <span className="text-xs text-gray-200 flex-1 font-mono">{tool.name}</span>
                <span className="text-[10px] text-gray-500">{tool.server}</span>
                <span className={`text-[10px] ${statusText(tool.status)}`}>{tool.status}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Skill tool compatibility (R60) */}
        <div>
          <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">
            Skill Tool Requirements
          </h3>
          <p className="text-[10px] text-gray-500 mb-2">
            Select a skill to check if required tools are available
          </p>
          <select
            className="w-full bg-surface-2 border border-surface-4 rounded px-2 py-1.5 text-xs text-gray-200 mb-2 focus:outline-none focus:border-accent-blue"
            value={selectedSkill?.name || ''}
            onChange={(e) => {
              const s = skills.find(sk => sk.name === e.target.value)
              setSelectedSkill(s || null)
            }}
          >
            <option value="">Select a skill...</option>
            {skills.map(s => (
              <option key={s.name} value={s.name}>{s.name}</option>
            ))}
          </select>

          {selectedSkill && (
            <div className="bg-surface-2 rounded-lg p-3">
              <div className="text-xs text-gray-200 mb-1">{selectedSkill.name}</div>
              <div className="text-[10px] text-gray-400 mb-2">{selectedSkill.description}</div>
              {selectedSkill.allowed_tools.length === 0 ? (
                <div className="text-[10px] text-gray-500">No specific tools required</div>
              ) : (
                <div className="space-y-1">
                  <div className="text-[10px] text-gray-500 uppercase">Required tools:</div>
                  {selectedSkill.allowed_tools.map(tool => {
                    const isAvailable = tools.some(t =>
                      t.name.toLowerCase().includes(tool.toLowerCase())
                    ) || tool === 'Bash'
                    return (
                      <div key={tool} className="flex items-center gap-2 text-[10px]">
                        <div className={`w-1.5 h-1.5 rounded-full ${isAvailable ? 'bg-green-400' : 'bg-red-400'}`} />
                        <span className={isAvailable ? 'text-gray-300' : 'text-red-400'}>
                          {tool}
                          {!isAvailable && ' (not connected)'}
                        </span>
                      </div>
                    )
                  })}
                  {getSkillToolWarnings(selectedSkill).length > 0 && (
                    <div className="mt-2 bg-red-900/20 border border-red-900/30 rounded px-2 py-1 text-[10px] text-red-400">
                      Warning: {getSkillToolWarnings(selectedSkill).length} required tool(s) not connected.
                      The skill may not function correctly.
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* R59: Graceful degradation notice */}
        <div className="mt-4 pt-4 border-t border-surface-3">
          <p className="text-[10px] text-gray-500">
            The Workbench functions without MCP tools as a structured chat with graph tracing.
            Tool-dependent features will show errors on graph nodes when tools are unavailable.
          </p>
        </div>
      </div>
    </div>
  )
}
