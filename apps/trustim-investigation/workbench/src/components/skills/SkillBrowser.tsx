import { useState, useEffect } from 'react'
import { miscApi } from '../../api'
import type { Skill } from '../../types'

interface Props {
  onClose: () => void
}

/** Skills browser drawer (R41-R46) */
export function SkillBrowser({ onClose }: Props) {
  const [skills, setSkills] = useState<{ investigation: Skill[]; action: Skill[] }>({
    investigation: [],
    action: [],
  })
  const [selectedSkill, setSelectedSkill] = useState<(Skill & { content?: string }) | null>(null)
  const [filter, setFilter] = useState('')
  const [tab, setTab] = useState<'investigation' | 'action'>('investigation')

  useEffect(() => {
    miscApi.listSkills()
      .then(setSkills)
      .catch(() => {})
  }, [])

  const loadSkillContent = (skill: Skill) => {
    miscApi.getSkill(skill.name)
      .then((data: any) => setSelectedSkill(data))
      .catch(() => {})
  }

  const filtered = skills[tab].filter(
    (s) =>
      s.name.toLowerCase().includes(filter.toLowerCase()) ||
      s.description.toLowerCase().includes(filter.toLowerCase())
  )

  return (
    <div className="absolute left-0 top-0 h-full w-[380px] bg-surface-1 border-r border-surface-3 shadow-2xl z-50 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-surface-3 flex-shrink-0">
        <h2 className="text-sm font-medium text-gray-200">Investigation Skills</h2>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-200 text-lg leading-none">
          {'\u2715'}
        </button>
      </div>

      {/* Filter */}
      <div className="px-4 py-2 border-b border-surface-3 flex-shrink-0">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search skills..."
          className="w-full bg-surface-2 border border-surface-4 rounded px-2 py-1.5 text-xs text-gray-200 placeholder-gray-500 focus:border-accent-blue focus:outline-none"
          autoFocus
        />
      </div>

      {/* Tabs */}
      <div className="flex border-b border-surface-3 flex-shrink-0">
        <button
          onClick={() => setTab('investigation')}
          className={`flex-1 px-4 py-2 text-xs transition-colors ${
            tab === 'investigation'
              ? 'text-gray-200 border-b-2 border-accent-blue'
              : 'text-gray-500 hover:text-gray-300'
          }`}
        >
          Investigation ({skills.investigation.length})
        </button>
        <button
          onClick={() => setTab('action')}
          className={`flex-1 px-4 py-2 text-xs transition-colors ${
            tab === 'action'
              ? 'text-gray-200 border-b-2 border-accent-blue'
              : 'text-gray-500 hover:text-gray-300'
          }`}
        >
          Actions ({skills.action.length})
        </button>
      </div>

      {/* Skill list or detail */}
      <div className="flex-1 overflow-y-auto">
        {selectedSkill ? (
          <div className="p-4">
            <button
              onClick={() => setSelectedSkill(null)}
              className="text-xs text-accent-blue hover:text-blue-400 mb-3"
            >
              {'\u2190'} Back to list
            </button>
            <h3 className="text-sm font-medium text-gray-200 mb-1">{selectedSkill.name}</h3>
            <p className="text-xs text-gray-400 mb-3">{selectedSkill.description}</p>
            {selectedSkill.allowed_tools.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-3">
                {selectedSkill.allowed_tools.map((t) => (
                  <span key={t} className="text-[10px] bg-surface-3 text-gray-400 px-1.5 py-0.5 rounded">
                    {t}
                  </span>
                ))}
              </div>
            )}
            {selectedSkill.content && (
              <>
                {/* Key tables extracted from skill */}
                {(() => {
                  const tables = (selectedSkill.content.match(/\| `([^`]+)` \|/g) || []).map((m: string) => m.match(/`([^`]+)`/)?.[1] || '').filter(t => t) as string[]
                  if (tables.length === 0) return null
                  return (
                    <div className="mb-3">
                      <h4 className="text-[10px] text-gray-500 uppercase mb-1">Key Tables</h4>
                      <div className="flex flex-wrap gap-1">
                        {tables.slice(0, 8).map((t: string) => (
                          <span key={t} className="text-[10px] bg-accent-cyan/10 text-accent-cyan px-1.5 py-0.5 rounded font-mono">{t}</span>
                        ))}
                      </div>
                    </div>
                  )
                })()}
                {/* SQL template count */}
                {(() => {
                  const sqlBlocks = (selectedSkill.content.match(/```sql/g) || []).length
                  if (sqlBlocks === 0) return null
                  return <p className="text-[10px] text-gray-500 mb-2">{sqlBlocks} SQL template(s) available</p>
                })()}
                <pre className="bg-surface-0 rounded-lg p-3 text-[11px] text-gray-300 overflow-auto max-h-[400px] whitespace-pre-wrap font-mono border border-surface-3">
                  {selectedSkill.content}
                </pre>
              </>
            )}
          </div>
        ) : (
          <div className="p-2 space-y-1">
            {filtered.length === 0 && (
              <p className="text-xs text-gray-500 text-center py-4">No skills found</p>
            )}
            {filtered.map((skill) => (
              <button
                key={skill.name}
                onClick={() => loadSkillContent(skill)}
                className="w-full text-left bg-surface-2 hover:bg-surface-3 rounded-lg px-3 py-2.5 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-gray-200">{skill.name}</span>
                  <span className="text-[10px] bg-surface-4 text-gray-500 px-1.5 py-0.5 rounded">
                    {skill.area}
                  </span>
                </div>
                {skill.description && (
                  <p className="text-[11px] text-gray-400 mt-1 line-clamp-2">{skill.description}</p>
                )}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
