import { useState, useEffect } from 'react'
import { playbooksApi } from '../../api'
import { usePlaybookStore } from '../../store/playbook'
import type { Playbook } from '../../types/playbook'

interface Props {
  onOpenEditor: (playbook?: Playbook) => void
}

export function PlaybookLibrary({ onOpenEditor }: Props) {
  const playbooks = usePlaybookStore((s) => s.playbooks)
  const loading = usePlaybookStore((s) => s.loading)
  const fetchPlaybooks = usePlaybookStore((s) => s.fetchPlaybooks)
  const deletePlaybook = usePlaybookStore((s) => s.deletePlaybook)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<Playbook | null>(null)
  const [search, setSearch] = useState('')
  const [showRunForm, setShowRunForm] = useState(false)

  useEffect(() => { fetchPlaybooks() }, [])
  useEffect(() => {
    if (!selectedId) { setDetail(null); return }
    usePlaybookStore.getState().fetchPlaybook(selectedId).then(setDetail)
  }, [selectedId])

  const displayed = playbooks.filter(p =>
    !search || p.name.toLowerCase().includes(search.toLowerCase()) || p.description?.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="h-full flex">
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-3 flex-shrink-0">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-medium text-gray-200">Playbooks</h2>
            <span className="text-[12px] text-gray-500 tabular-nums">{playbooks.length} total</span>
          </div>
          <button
            onClick={() => onOpenEditor()}
            className="text-[11px] bg-accent-blue/20 hover:bg-accent-blue/30 text-accent-blue px-3 py-1.5 rounded-md transition-colors"
          >
            + Create Playbook
          </button>
        </div>

        {/* Search */}
        <div className="px-6 py-3 border-b border-surface-3 flex-shrink-0">
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search playbooks..."
            className="w-full bg-surface-2/60 border border-white/[0.06] rounded-lg px-3 py-2 text-[13px] text-gray-200 placeholder-gray-500 focus:outline-none focus:border-accent-blue/50"
          />
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          {loading ? (
            <div className="p-6 space-y-2">
              {[1,2,3].map(i => <div key={i} className="bg-white/[0.02] rounded-lg px-4 py-3 animate-pulse"><div className="h-3 bg-surface-3 rounded w-3/4 mb-2" /><div className="h-2 bg-surface-3 rounded w-1/2" /></div>)}
            </div>
          ) : displayed.length === 0 ? (
            <div className="p-6 text-center py-20">
              <div className="text-3xl mb-3 opacity-20">{'\u{1F4CB}'}</div>
              <p className="text-[14px] text-gray-400 mb-1">No playbooks yet</p>
              <p className="text-[12px] text-gray-500">Click "+ Create Playbook" to build a visual DAG workflow from automations.</p>
            </div>
          ) : (
            displayed.map(p => (
              <div
                key={p.id}
                onClick={() => setSelectedId(selectedId === p.id ? null : p.id)}
                className={`flex items-center gap-3 px-4 py-3 rounded-lg cursor-pointer transition-colors ${
                  selectedId === p.id
                    ? 'bg-accent-blue/10 border border-accent-blue/20'
                    : 'bg-white/[0.02] hover:bg-white/[0.05] border border-transparent'
                }`}
              >
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] text-gray-200 truncate">{p.name}</div>
                  <div className="flex items-center gap-2 text-[11px] text-gray-500 mt-0.5">
                    <span>{p.category || 'uncategorized'}</span>
                    <span className="text-gray-600">|</span>
                    <span>{(p.nodes || []).length} steps</span>
                    <span className="text-gray-600">|</span>
                    <span>v{p.version || 1}</span>
                  </div>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); if (confirm(`Delete "${p.name}"?`)) deletePlaybook(p.id) }}
                  className="text-gray-600 hover:text-red-400 transition-colors flex-shrink-0"
                >{'\u2715'}</button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Detail panel */}
      {selectedId && detail && (
        <div className="w-[420px] border-l border-surface-3 flex-shrink-0 overflow-y-auto">
          <div className="px-5 py-4 border-b border-surface-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] bg-green-900/30 text-green-400 px-2 py-0.5 rounded">v{detail.version || 1}</span>
              <button onClick={() => setSelectedId(null)} className="text-gray-400 hover:text-gray-200">{'\u2715'}</button>
            </div>
            <h3 className="text-[15px] font-medium text-gray-200">{detail.name}</h3>
            <p className="text-[12px] text-gray-500 mt-1">{detail.description}</p>
          </div>

          <div className="px-5 py-4 space-y-4">
            {/* Actions */}
            <div className="flex gap-2">
              <button
                onClick={() => onOpenEditor(detail)}
                className="text-[12px] bg-accent-blue hover:bg-blue-600 text-white px-4 py-1.5 rounded-md transition-colors"
              >
                Edit
              </button>
              <button
                onClick={() => setShowRunForm(true)}
                className="text-[12px] bg-green-600 hover:bg-green-700 text-white px-4 py-1.5 rounded-md transition-colors"
              >
                Run
              </button>
            </div>

            {/* Run form with inputs */}
            {showRunForm && <PlaybookRunForm playbook={detail} onClose={() => setShowRunForm(false)} />}

            {/* Mini DAG preview */}
            <div>
              <h4 className="text-[11px] text-gray-500 uppercase tracking-wider mb-2">Steps ({detail.nodes.length})</h4>
              <div className="space-y-1">
                {detail.nodes.map(n => (
                  <div key={n.id} className="flex items-center gap-2 px-3 py-2 bg-surface-2/40 rounded-lg">
                    <span className="w-2 h-2 rounded-full bg-accent-blue flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-[12px] text-gray-200 truncate">{n.label}</div>
                      <div className="text-[10px] text-gray-500">{n.ref_type}: {n.ref_id}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Edges */}
            {detail.edges.length > 0 && (
              <div>
                <h4 className="text-[11px] text-gray-500 uppercase tracking-wider mb-2">Connections ({detail.edges.length})</h4>
                <div className="space-y-1 text-[11px] text-gray-400">
                  {detail.edges.map(e => {
                    const from = detail.nodes.find(n => n.id === e.source)?.label || e.source
                    const to = detail.nodes.find(n => n.id === e.target)?.label || e.target
                    return (
                      <div key={e.id} className="flex items-center gap-1">
                        <span className="truncate">{from}</span>
                        <span className="text-gray-600">{'\u2192'}</span>
                        <span className="truncate">{to}</span>
                        {e.label && <span className="text-[10px] text-accent-purple ml-1">({e.label})</span>}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Execution history */}
            <ExecutionHistory playbookId={detail.id} />

            {/* Inputs */}
            {detail.inputs?.length > 0 && (
              <div>
                <h4 className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">Inputs</h4>
                <div className="space-y-1">
                  {detail.inputs.map(inp => (
                    <div key={inp.name} className="text-[11px] text-gray-400">
                      <span className="text-gray-300 font-mono">{inp.name}</span> <span className="text-gray-600">({inp.type})</span>
                      {inp.description && <span className="text-gray-600"> — {inp.description}</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function PlaybookRunForm({ playbook, onClose }: { playbook: Playbook; onClose: () => void }) {
  const [inputs, setInputs] = useState<Record<string, string>>({})
  const [running, setRunning] = useState(false)

  const handleRun = async () => {
    setRunning(true)
    const sessionId = crypto.randomUUID()
    await usePlaybookStore.getState().runPlaybook(playbook.id, inputs, sessionId)
    window.dispatchEvent(new CustomEvent('openInvestigationTab', { detail: { sessionId, name: `Playbook: ${playbook.name}` } }))
    setRunning(false)
    onClose()
  }

  return (
    <div className="mt-3 bg-surface-2/40 rounded-lg p-3 border border-white/[0.06]">
      <h4 className="text-[11px] text-gray-500 uppercase tracking-wider mb-2">Run: {playbook.name}</h4>
      {(playbook.inputs || []).length > 0 ? (
        <div className="space-y-2 mb-3">
          {playbook.inputs.map(inp => (
            <div key={inp.name}>
              <label className="text-[10px] text-gray-400 block mb-0.5">
                {inp.name} <span className="text-gray-600">({inp.type})</span>
                {inp.required && <span className="text-red-400 ml-0.5">*</span>}
              </label>
              <input
                type="text"
                value={inputs[inp.name] || ''}
                onChange={e => setInputs(prev => ({ ...prev, [inp.name]: e.target.value }))}
                placeholder={inp.default || inp.description}
                className="w-full bg-surface-2 border border-surface-4 rounded px-2 py-1.5 text-[11px] text-gray-200 placeholder-gray-600 focus:outline-none focus:border-accent-blue/50"
              />
            </div>
          ))}
        </div>
      ) : (
        <p className="text-[11px] text-gray-500 mb-3">No inputs required.</p>
      )}
      <div className="flex gap-2">
        <button onClick={handleRun} disabled={running} className="text-[11px] bg-green-600 hover:bg-green-700 text-white px-4 py-1.5 rounded-md disabled:opacity-50">{running ? 'Starting...' : 'Run Playbook'}</button>
        <button onClick={onClose} className="text-[11px] text-gray-400 hover:text-gray-200 px-3 py-1.5">Cancel</button>
      </div>
    </div>
  )
}

function ExecutionHistory({ playbookId }: { playbookId: string }) {
  const [execs, setExecs] = useState<Array<{ id: string; status: string; session_id: string; started_at: string; finished_at?: string; node_states: Record<string, { status: string }> }>>([])

  useEffect(() => {
    playbooksApi.listExecutions()
      .then(all => setExecs(all.filter((e: any) => e.playbook_id === playbookId)))
      .catch(() => {})
  }, [playbookId])

  if (execs.length === 0) return null

  return (
    <div>
      <h4 className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">Execution History</h4>
      <div className="space-y-1">
        {execs.map(ex => {
          const states = Object.values(ex.node_states)
          const completed = states.filter(s => s.status === 'completed').length
          const failed = states.filter(s => s.status === 'failed').length
          return (
            <div
              key={ex.id}
              className="flex items-center gap-2 px-2 py-1.5 rounded bg-surface-2/40 cursor-pointer hover:bg-white/[0.04]"
              onClick={() => {
                window.dispatchEvent(new CustomEvent('openInvestigationTab', { detail: { sessionId: ex.session_id, name: `Playbook run` } }))
              }}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${
                ex.status === 'running' ? 'bg-yellow-400 animate-pulse'
                : ex.status === 'completed' ? 'bg-green-400'
                : ex.status === 'failed' ? 'bg-red-400'
                : 'bg-gray-500'
              }`} />
              <span className="text-[10px] text-gray-400">{ex.status}</span>
              <span className="text-[10px] text-gray-600 tabular-nums">{completed}/{states.length}{failed > 0 ? ` (${failed} failed)` : ''}</span>
              <span className="text-[10px] text-gray-600 ml-auto">{new Date(ex.started_at).toLocaleTimeString()}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
