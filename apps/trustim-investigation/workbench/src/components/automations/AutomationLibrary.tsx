import { useState, useEffect } from 'react'
import { useAutomationStore } from '../../store/automation'
import type { Automation, ExecType } from '../../types/automation'

const EXEC_TYPE_LABELS: Record<ExecType, string> = {
  trino_query: 'Trino Query',
  davi_widget: 'DAVI Widget',
  python_script: 'Python Script',
  claude_prompt: 'Claude Prompt',
}

const EXEC_TYPE_COLORS: Record<ExecType, string> = {
  trino_query: 'bg-blue-900/30 text-blue-400',
  davi_widget: 'bg-purple-900/30 text-purple-400',
  python_script: 'bg-green-900/30 text-green-400',
  claude_prompt: 'bg-orange-900/30 text-orange-400',
}

export function AutomationLibrary() {
  const automations = useAutomationStore((s) => s.automations)
  const loading = useAutomationStore((s) => s.loading)
  const fetchAutomations = useAutomationStore((s) => s.fetchAutomations)
  const deleteAutomation = useAutomationStore((s) => s.deleteAutomation)
  const setFilters = useAutomationStore((s) => s.setFilters)

  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<Automation | null>(null)
  const [showEditor, setShowEditor] = useState(false)
  const [runResult, setRunResult] = useState<{ success: boolean; output: any; error?: string; duration_ms: number } | null>(null)
  const [runInputs, setRunInputs] = useState<Record<string, string>>({})
  const [running, setRunning] = useState(false)

  useEffect(() => { fetchAutomations() }, [])

  useEffect(() => {
    if (!selectedId) { setDetail(null); return }
    // Clear previous run state when switching automations
    setRunResult(null)
    setRunInputs({})
    useAutomationStore.getState().fetchAutomation(selectedId).then(setDetail)
  }, [selectedId])

  const categories = [...new Set(automations.map(a => a.category))].sort()

  const displayed = automations
    .filter(a => categoryFilter === 'all' || a.category === categoryFilter)
    .filter(a => typeFilter === 'all' || a.exec_type === typeFilter)
    .filter(a => !search || a.name.toLowerCase().includes(search.toLowerCase()) || a.description?.toLowerCase().includes(search.toLowerCase()))


  const handleRun = async () => {
    if (!detail) return
    setRunning(true)
    setRunResult(null)
    const result = await useAutomationStore.getState().runAutomation(detail.id, runInputs)
    setRunResult(result)
    setRunning(false)
  }

  return (
    <div className="h-full flex">
      {/* Main list */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-3 flex-shrink-0">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-medium text-gray-200">Automations</h2>
            <span className="text-[12px] text-gray-500 tabular-nums">{automations.length} total</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowEditor(true)}
              className="text-[11px] bg-accent-blue/20 hover:bg-accent-blue/30 text-accent-blue px-3 py-1.5 rounded-md transition-colors"
            >
              + Create
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="px-6 py-3 border-b border-surface-3 space-y-2 flex-shrink-0">
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search automations..."
            className="w-full bg-surface-2/60 border border-white/[0.06] rounded-lg px-3 py-2 text-[13px] text-gray-200 placeholder-gray-500 focus:outline-none focus:border-accent-blue/50"
          />
          <div className="flex gap-1 flex-wrap">
            {['all', ...categories].map(c => (
              <button
                key={c}
                onClick={() => setCategoryFilter(c)}
                className={`text-[11px] px-2.5 py-1 rounded-md transition-colors ${
                  categoryFilter === c ? 'bg-accent-blue/20 text-accent-blue' : 'text-gray-500 hover:text-gray-300 hover:bg-surface-3'
                }`}
              >
                {c === 'all' ? 'All' : c}
              </button>
            ))}
          </div>
          <div className="flex gap-1 flex-wrap">
            {(['all', 'trino_query', 'davi_widget', 'python_script', 'claude_prompt'] as const).map(t => (
              <button
                key={t}
                onClick={() => setTypeFilter(t)}
                className={`text-[11px] px-2.5 py-1 rounded-md transition-colors ${
                  typeFilter === t ? 'bg-accent-purple/20 text-accent-purple' : 'text-gray-500 hover:text-gray-300 hover:bg-surface-3'
                }`}
              >
                {t === 'all' ? 'All Types' : EXEC_TYPE_LABELS[t]}
              </button>
            ))}
          </div>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          {loading ? (
            <div className="p-6 space-y-2">
              {[1,2,3].map(i => <div key={i} className="bg-white/[0.02] rounded-lg px-4 py-3 animate-pulse"><div className="h-3 bg-surface-3 rounded w-3/4 mb-2" /><div className="h-2 bg-surface-3 rounded w-1/2" /></div>)}
            </div>
          ) : displayed.length === 0 ? (
            <div className="p-6 text-center py-20">
              <div className="text-3xl mb-3 opacity-20">{'\u2699'}</div>
              <p className="text-[14px] text-gray-400 mb-1">No automations yet</p>
              <p className="text-[12px] text-gray-500">Click "Migrate Skills" to import action skills as automations.</p>
            </div>
          ) : (
            displayed.map(a => (
              <div
                key={a.id}
                onClick={() => setSelectedId(selectedId === a.id ? null : a.id)}
                className={`flex items-center gap-3 px-4 py-3 rounded-lg cursor-pointer transition-colors ${
                  selectedId === a.id
                    ? 'bg-accent-blue/10 border border-accent-blue/20'
                    : 'bg-white/[0.02] hover:bg-white/[0.05] border border-transparent'
                }`}
              >
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] text-gray-200 truncate">{a.name}</div>
                  <div className="flex items-center gap-2 text-[11px] text-gray-500 mt-0.5">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${EXEC_TYPE_COLORS[a.exec_type]}`}>{EXEC_TYPE_LABELS[a.exec_type]}</span>
                    <span>{a.category}</span>
                    <span className="text-gray-600">|</span>
                    <span>{a.input_count} inputs</span>
                    {a.source_skill && <><span className="text-gray-600">|</span><span className="text-gray-600">from: {a.source_skill}</span></>}
                  </div>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); if (confirm(`Delete "${a.name}"?`)) deleteAutomation(a.id) }}
                  className="text-gray-600 hover:text-red-400 transition-colors flex-shrink-0"
                >{'\u2715'}</button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Detail panel */}
      {selectedId && detail && (
        <div className="w-[460px] border-l border-surface-3 flex-shrink-0 overflow-y-auto">
          <div className="px-5 py-4 border-b border-surface-3">
            <div className="flex items-center justify-between mb-2">
              <span className={`text-[10px] px-2 py-0.5 rounded ${EXEC_TYPE_COLORS[detail.exec_type]}`}>{EXEC_TYPE_LABELS[detail.exec_type]}</span>
              <button onClick={() => setSelectedId(null)} className="text-gray-400 hover:text-gray-200">{'\u2715'}</button>
            </div>
            <h3 className="text-[15px] font-medium text-gray-200">{detail.name}</h3>
            <p className="text-[12px] text-gray-500 mt-1">{detail.description}</p>
          </div>

          <div className="px-5 py-4 space-y-4">
            {/* Inputs */}
            {detail.inputs.length > 0 && (
              <div>
                <h4 className="text-[11px] text-gray-500 uppercase tracking-wider mb-2">Inputs ({detail.inputs.length})</h4>
                <div className="space-y-2">
                  {detail.inputs.map(inp => (
                    <div key={inp.name}>
                      <label className="text-[11px] text-gray-400 block mb-0.5">{inp.name} <span className="text-gray-600">({inp.type})</span></label>
                      <input
                        type="text"
                        value={runInputs[inp.name] || ''}
                        onChange={e => setRunInputs(prev => ({ ...prev, [inp.name]: e.target.value }))}
                        placeholder={inp.default || inp.description}
                        className="w-full bg-surface-2 border border-surface-4 rounded px-2 py-1.5 text-[12px] text-gray-200 placeholder-gray-600 focus:outline-none focus:border-accent-blue/50"
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Run button */}
            <button
              onClick={handleRun}
              disabled={running}
              className="w-full text-[12px] bg-accent-blue hover:bg-blue-600 text-white py-2 rounded-md transition-colors disabled:opacity-50"
            >
              {running ? 'Running...' : 'Test Run'}
            </button>

            {/* Result */}
            {runResult && <RunResultDisplay result={runResult} />}

            {/* SQL body */}
            {detail.exec_body && (
              <div>
                <h4 className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">Query Template</h4>
                <pre className="bg-surface-0 rounded-lg p-3 text-[11px] text-gray-300 overflow-auto max-h-[300px] border border-surface-3 whitespace-pre-wrap font-mono">
                  {detail.exec_body}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Create modal placeholder */}
      {showEditor && <AutomationEditorModal onClose={() => { setShowEditor(false); fetchAutomations() }} />}
    </div>
  )
}

function AutomationEditorModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('')
  const [execType, setExecType] = useState<ExecType>('trino_query')
  const [execBody, setExecBody] = useState('')
  const [headlessAccount, setHeadlessAccount] = useState('trustim')

  const handleSave = async () => {
    if (!name.trim() || !execBody.trim()) return
    await useAutomationStore.getState().createAutomation({
      name: name.trim(),
      description: description.trim(),
      category: category.trim() || 'custom',
      exec_type: execType,
      exec_body: execBody,
      exec_config: { headless_account: headlessAccount },
      inputs: [],
      outputs: [],
    })
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[110]" onClick={onClose}>
      <div className="bg-surface-1 border border-surface-3 rounded-xl p-6 w-[520px] max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <h3 className="text-sm font-medium text-gray-200 mb-4">Create Automation</h3>
        <div className="space-y-3">
          <input type="text" value={name} onChange={e => setName(e.target.value)} placeholder="Name"
            className="w-full bg-surface-2 border border-surface-4 rounded-lg px-3 py-2 text-[13px] text-gray-200 placeholder-gray-500 focus:outline-none focus:border-accent-blue/50" autoFocus />
          <input type="text" value={description} onChange={e => setDescription(e.target.value)} placeholder="Description"
            className="w-full bg-surface-2 border border-surface-4 rounded-lg px-3 py-2 text-[13px] text-gray-200 placeholder-gray-500 focus:outline-none" />
          <div className="flex gap-2">
            <input type="text" value={category} onChange={e => setCategory(e.target.value)} placeholder="Category"
              className="flex-1 bg-surface-2 border border-surface-4 rounded-lg px-3 py-2 text-[12px] text-gray-200 placeholder-gray-500 focus:outline-none" />
            <select value={execType} onChange={e => setExecType(e.target.value as ExecType)}
              className="bg-surface-2 border border-surface-4 rounded-lg px-2 py-2 text-[12px] text-gray-300 focus:outline-none">
              <option value="trino_query">Trino Query</option>
              <option value="davi_widget">DAVI Widget</option>
              <option value="python_script">Python Script</option>
              <option value="claude_prompt">Claude Prompt</option>
            </select>
            <input type="text" value={headlessAccount} onChange={e => setHeadlessAccount(e.target.value)} placeholder="Account"
              className="w-24 bg-surface-2 border border-surface-4 rounded-lg px-2 py-2 text-[12px] text-gray-200 placeholder-gray-500 focus:outline-none" />
          </div>
          <textarea value={execBody} onChange={e => setExecBody(e.target.value)} placeholder="SQL query / Python code / Prompt..." rows={10}
            className="w-full bg-surface-2 border border-surface-4 rounded-lg px-3 py-2 text-[12px] text-gray-200 placeholder-gray-500 focus:outline-none resize-none font-mono" />
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="text-[12px] text-gray-400 hover:text-gray-200 px-3 py-1.5 rounded-md transition-colors">Cancel</button>
          <button onClick={handleSave} disabled={!name.trim() || !execBody.trim()}
            className="text-[12px] bg-accent-blue hover:bg-blue-600 text-white px-4 py-1.5 rounded-md transition-colors disabled:opacity-50">Create</button>
        </div>
      </div>
    </div>
  )
}

/** Deep-parse nested JSON strings and render results as table or formatted JSON */
function RunResultDisplay({ result }: { result: { success: boolean; output: any; error?: string; duration_ms: number } }) {
  // Recursively unwrap nested JSON strings
  const unwrap = (v: unknown, depth = 0): unknown => {
    if (depth > 10) return v
    if (typeof v === 'string') {
      try { return unwrap(JSON.parse(v), depth + 1) } catch { return v }
    }
    if (Array.isArray(v)) return v.map(unwrap)
    if (v && typeof v === 'object') {
      const out: Record<string, unknown> = {}
      for (const [k, val] of Object.entries(v as Record<string, unknown>)) out[k] = unwrap(val)
      return out
    }
    return v
  }

  const parsed = unwrap(result.output) as Record<string, unknown>
  // Extract rows array if present (Trino results have { result: { results: [...] } })
  const findRows = (obj: unknown): Record<string, unknown>[] | null => {
    if (Array.isArray(obj) && obj.length > 0 && typeof obj[0] === 'object') return obj as Record<string, unknown>[]
    if (obj && typeof obj === 'object') {
      for (const val of Object.values(obj as Record<string, unknown>)) {
        const found = findRows(val)
        if (found) return found
      }
    }
    return null
  }
  const rows = findRows(parsed)
  // Extract query URL if present
  const findString = (obj: unknown, key: string): string | null => {
    if (obj && typeof obj === 'object') {
      const rec = obj as Record<string, unknown>
      if (typeof rec[key] === 'string') return rec[key] as string
      for (const val of Object.values(rec)) {
        const found = findString(val, key)
        if (found) return found
      }
    }
    return null
  }
  const queryUrl = findString(parsed, 'query_url')
  const queryId = findString(parsed, 'query_id')

  return (
    <div className={`rounded-lg text-[12px] ${result.success ? 'bg-green-900/20 border border-green-900/30' : 'bg-red-900/20 border border-red-900/30'}`}>
      <div className="flex items-center justify-between px-3 pt-2 pb-1">
        <span className={result.success ? 'text-green-400' : 'text-red-400'}>
          {result.success ? 'Success' : 'Failed'}
          {rows && ` — ${rows.length} row${rows.length !== 1 ? 's' : ''}`}
        </span>
        <div className="flex items-center gap-2">
          {queryId && <span className="text-[10px] text-gray-600 font-mono">{queryId}</span>}
          {queryUrl && <a href={queryUrl} target="_blank" rel="noopener" className="text-[10px] text-accent-blue hover:text-blue-400">Trino UI</a>}
          <span className="text-gray-500 tabular-nums">{(result.duration_ms / 1000).toFixed(1)}s</span>
        </div>
      </div>
      {result.error && <p className="text-red-300 text-[11px] px-3 pb-1">{result.error}</p>}

      {/* Table view for row results */}
      {rows && rows.length > 0 ? (
        <div className="overflow-auto max-h-[300px] px-1 pb-2">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-white/[0.06]">
                {Object.keys(rows[0]).map(col => (
                  <th key={col} className="text-left text-gray-500 px-2 py-1 font-medium whitespace-nowrap">{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-b border-white/[0.03] hover:bg-white/[0.02]">
                  {Object.values(row).map((val, j) => (
                    <td key={j} className="text-gray-300 px-2 py-1 whitespace-nowrap font-mono">{String(val)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <pre className="text-gray-300 text-[10px] overflow-auto max-h-[200px] whitespace-pre-wrap px-3 pb-2">
          {typeof parsed === 'string' ? parsed : JSON.stringify(parsed, null, 2)}
        </pre>
      )}
    </div>
  )
}
