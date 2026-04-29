import { useState, useEffect, useMemo } from 'react'
import { sessionsApi } from '../../api'
import { confidenceColor } from '../../types'
import type { Session, SessionSummary } from '../../types'

interface Props {
  onClose: () => void
}

/** Compare two investigation sessions side-by-side */
export function SessionComparePanel({ onClose }: Props) {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [selectedA, setSelectedA] = useState<string>('')
  const [selectedB, setSelectedB] = useState<string>('')
  const [sessionA, setSessionA] = useState<Session | null>(null)
  const [sessionB, setSessionB] = useState<Session | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    sessionsApi.list()
      .then(setSessions)
      .catch(() => {})
  }, [])

  const loadBoth = () => {
    if (!selectedA || !selectedB) return
    setLoading(true)
    Promise.all([
      sessionsApi.get(selectedA),
      sessionsApi.get(selectedB),
    ])
      .then(([a, b]) => { setSessionA(a); setSessionB(b) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[100]" onClick={onClose}>
      <div className="glass-panel rounded-2xl p-6 w-[960px] max-h-[85vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-medium text-gray-200">Compare Investigations</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-200">{'\u2715'}</button>
        </div>

        {/* Session selectors */}
        <div className="flex gap-3 mb-4">
          <select
            value={selectedA}
            onChange={e => { setSelectedA(e.target.value); setSessionA(null) }}
            className="flex-1 bg-surface-2/60 border border-white/[0.06] rounded-lg px-3 py-2 text-[13px] text-gray-200 focus:outline-none focus:border-accent-blue/50"
          >
            <option value="">Select Session A...</option>
            {sessions.map(s => (
              <option key={s.id} value={s.id} disabled={s.id === selectedB}>
                {s.name} ({s.node_count} nodes, {new Date(s.updated_at).toLocaleDateString()})
              </option>
            ))}
          </select>
          <select
            value={selectedB}
            onChange={e => { setSelectedB(e.target.value); setSessionB(null) }}
            className="flex-1 bg-surface-2/60 border border-white/[0.06] rounded-lg px-3 py-2 text-[13px] text-gray-200 focus:outline-none focus:border-accent-blue/50"
          >
            <option value="">Select Session B...</option>
            {sessions.map(s => (
              <option key={s.id} value={s.id} disabled={s.id === selectedA}>
                {s.name} ({s.node_count} nodes, {new Date(s.updated_at).toLocaleDateString()})
              </option>
            ))}
          </select>
          <button
            onClick={loadBoth}
            disabled={!selectedA || !selectedB || loading}
            className="bg-accent-blue hover:bg-blue-500 disabled:bg-surface-3 disabled:text-gray-600 text-white text-[13px] font-medium px-4 py-2 rounded-lg transition-colors"
          >
            {loading ? 'Loading...' : 'Compare'}
          </button>
        </div>

        {/* Comparison content */}
        {sessionA && sessionB ? (
          <ComparisonView a={sessionA} b={sessionB} />
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
            Select two investigations and click Compare
          </div>
        )}
      </div>
    </div>
  )
}

function ComparisonView({ a, b }: { a: Session; b: Session }) {
  const statsA = useMemo(() => computeStats(a), [a])
  const statsB = useMemo(() => computeStats(b), [b])

  return (
    <div className="flex-1 overflow-y-auto space-y-4">
      {/* Header row */}
      <div className="grid grid-cols-[1fr_auto_1fr] gap-4 items-start">
        <div className="text-center">
          <div className="text-[13px] font-medium text-accent-blue truncate">{a.name}</div>
          <div className="text-[11px] text-gray-500">{new Date(a.created_at).toLocaleDateString()}</div>
        </div>
        <div className="text-[11px] text-gray-600 px-2 pt-1">vs</div>
        <div className="text-center">
          <div className="text-[13px] font-medium text-accent-purple truncate">{b.name}</div>
          <div className="text-[11px] text-gray-500">{new Date(b.created_at).toLocaleDateString()}</div>
        </div>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-[1fr_auto_1fr] gap-4">
        <MetricCard label="Nodes" valueA={statsA.nodeCount} valueB={statsB.nodeCount} />
        <MetricCard label="Edges" valueA={a.edges.length} valueB={b.edges.length} />
        <MetricCard label="Max Depth" valueA={statsA.maxDepth} valueB={statsB.maxDepth} />
        <MetricCard label="Dead Ends" valueA={statsA.deadEnds} valueB={statsB.deadEnds} />
        <MetricCard label="Failed" valueA={statsA.failed} valueB={statsB.failed} />
        <MetricCard label="Avg Score" valueA={statsA.avgScore} valueB={statsB.avgScore} format="pct" />
        <MetricCard label="Max Score" valueA={statsA.maxScore} valueB={statsB.maxScore} format="pct" />
        <MetricCard label="Total Time" valueA={statsA.totalTimeMs} valueB={statsB.totalTimeMs} format="time" />
        <MetricCard label="IOCs Found" valueA={statsA.iocCount} valueB={statsB.iocCount} />
      </div>

      {/* Score distribution comparison */}
      <div className="bg-surface-2/40 rounded-xl p-4">
        <h3 className="text-[12px] font-medium text-gray-300 mb-3 uppercase tracking-wider">Score Distribution</h3>
        <div className="grid grid-cols-2 gap-6">
          <ScoreBar label="A" high={statsA.high} medium={statsA.medium} low={statsA.low} total={statsA.nodeCount} />
          <ScoreBar label="B" high={statsB.high} medium={statsB.medium} low={statsB.low} total={statsB.nodeCount} />
        </div>
      </div>

      {/* Action type breakdown */}
      <div className="bg-surface-2/40 rounded-xl p-4">
        <h3 className="text-[12px] font-medium text-gray-300 mb-3 uppercase tracking-wider">Action Types</h3>
        <div className="grid grid-cols-2 gap-6">
          <ActionBreakdown stats={statsA.actionTypes} color="accent-blue" />
          <ActionBreakdown stats={statsB.actionTypes} color="accent-purple" />
        </div>
      </div>

      {/* Skills & tools overlap */}
      <div className="grid grid-cols-2 gap-4">
        <OverlapSection title="Skills Used" itemsA={a.skills_used} itemsB={b.skills_used} />
        <OverlapSection title="Tools Used" itemsA={a.tools_used} itemsB={b.tools_used} />
      </div>

      {/* Common IOCs */}
      {(statsA.iocs.size > 0 || statsB.iocs.size > 0) && (
        <div className="bg-surface-2/40 rounded-xl p-4">
          <h3 className="text-[12px] font-medium text-gray-300 mb-3 uppercase tracking-wider">IOC Overlap</h3>
          <IocOverlap iocsA={statsA.iocs} iocsB={statsB.iocs} />
        </div>
      )}
    </div>
  )
}

interface Stats {
  nodeCount: number
  maxDepth: number
  deadEnds: number
  failed: number
  avgScore: number
  maxScore: number
  high: number
  medium: number
  low: number
  totalTimeMs: number
  iocCount: number
  iocs: Set<string>
  actionTypes: Record<string, number>
}

function computeStats(session: Session): Stats {
  const nodes = Object.values(session.nodes)
  const nodeCount = nodes.length
  let maxDepth = 0
  let deadEnds = 0
  let failed = 0
  let scoreSum = 0
  let maxScore = 0
  let high = 0, medium = 0, low = 0
  let totalTimeMs = 0
  const iocs = new Set<string>()
  const actionTypes: Record<string, number> = {}

  for (const n of nodes) {
    // Depth via parent chain
    let depth = 0
    let cur = n
    const visited = new Set<string>()
    while ((cur.parent_ids || [])[0] && !visited.has((cur.parent_ids || [])[0])) {
      visited.add((cur.parent_ids || [])[0])
      cur = session.nodes[(cur.parent_ids || [])[0]]
      if (!cur) break
      depth++
    }
    if (depth > maxDepth) maxDepth = depth

    if (n.is_dead_end) deadEnds++
    if (n.status === 'failed') failed++
    scoreSum += n.confidence
    if (n.confidence > maxScore) maxScore = n.confidence
    if (n.confidence > 0.6) high++
    else if (n.confidence > 0.2) medium++
    else low++
    totalTimeMs += n.duration_ms || 0

    actionTypes[n.action_type] = (actionTypes[n.action_type] || 0) + 1

    // Extract IOCs from result_raw
    const raw = n.result_raw || ''
    const ipRe = /\b(?:\d{1,3}\.){3}\d{1,3}\b/g
    const hashRe = /\b[a-f0-9]{32,64}\b/gi
    const domainRe = /\b[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.[a-z]{2,}\b/gi
    for (const m of raw.match(ipRe) || []) iocs.add(m)
    for (const m of raw.match(hashRe) || []) iocs.add(m)
    for (const m of raw.match(domainRe) || []) {
      if (!['github.com', 'linkedin.com', 'google.com'].includes(m)) iocs.add(m)
    }
  }

  return {
    nodeCount,
    maxDepth,
    deadEnds,
    failed,
    avgScore: nodeCount > 0 ? scoreSum / nodeCount : 0,
    maxScore,
    high, medium, low,
    totalTimeMs,
    iocCount: iocs.size,
    iocs,
    actionTypes,
  }
}

function MetricCard({ label, valueA, valueB, format }: { label: string; valueA: number; valueB: number; format?: 'pct' | 'time' }) {
  const fmt = (v: number) => {
    if (format === 'pct') return `${(v * 100).toFixed(0)}%`
    if (format === 'time') return `${(v / 1000).toFixed(1)}s`
    return String(v)
  }
  const diff = valueA === 0 && valueB === 0 ? 0 : valueB - valueA
  const diffColor = diff === 0 ? 'text-gray-500' : diff > 0 ? 'text-red-400' : 'text-green-400'

  return (
    <>
      <div className="bg-surface-2/40 rounded-lg px-3 py-2 text-right">
        <div className="text-[15px] font-medium text-accent-blue tabular-nums">{fmt(valueA)}</div>
        <div className="text-[10px] text-gray-500">{label}</div>
      </div>
      <div className={`flex items-center text-[11px] ${diffColor} tabular-nums`}>
        {diff !== 0 && (format === 'pct' ? `${diff > 0 ? '+' : ''}${(diff * 100).toFixed(0)}%` : format === 'time' ? `${diff > 0 ? '+' : ''}${(diff / 1000).toFixed(1)}s` : `${diff > 0 ? '+' : ''}${diff}`)}
      </div>
      <div className="bg-surface-2/40 rounded-lg px-3 py-2">
        <div className="text-[15px] font-medium text-accent-purple tabular-nums">{fmt(valueB)}</div>
        <div className="text-[10px] text-gray-500">{label}</div>
      </div>
    </>
  )
}

function ScoreBar({ label, high, medium, low, total }: { label: string; high: number; medium: number; low: number; total: number }) {
  if (total === 0) return <div className="text-[11px] text-gray-500">No nodes</div>
  const pct = (n: number) => `${((n / total) * 100).toFixed(0)}%`
  return (
    <div>
      <div className="text-[11px] text-gray-400 mb-1">{label}</div>
      <div className="flex h-5 rounded-md overflow-hidden">
        {high > 0 && <div style={{ width: pct(high), backgroundColor: confidenceColor(0.8) }} className="transition-all" title={`High: ${high}`} />}
        {medium > 0 && <div style={{ width: pct(medium), backgroundColor: confidenceColor(0.4) }} className="transition-all" title={`Medium: ${medium}`} />}
        {low > 0 && <div style={{ width: pct(low), backgroundColor: confidenceColor(0.1) }} className="transition-all" title={`Low: ${low}`} />}
      </div>
      <div className="flex justify-between text-[10px] text-gray-500 mt-1">
        <span style={{ color: confidenceColor(0.8) }}>{high} high</span>
        <span style={{ color: confidenceColor(0.4) }}>{medium} med</span>
        <span style={{ color: confidenceColor(0.1) }}>{low} low</span>
      </div>
    </div>
  )
}

function ActionBreakdown({ stats, color }: { stats: Record<string, number>; color: string }) {
  const entries = Object.entries(stats).sort((a, b) => b[1] - a[1])
  if (entries.length === 0) return <div className="text-[11px] text-gray-500">No actions</div>
  const max = entries[0][1]
  const barColor = color === 'accent-blue' ? 'rgb(59,130,246)' : 'rgb(168,85,247)'
  return (
    <div className="space-y-1">
      {entries.map(([type, count]) => (
        <div key={type} className="flex items-center gap-2">
          <span className="text-[11px] text-gray-400 w-20 truncate">{type}</span>
          <div className="flex-1 h-3 bg-surface-3 rounded-full overflow-hidden">
            <div className="h-full rounded-full" style={{ width: `${(count / max) * 100}%`, backgroundColor: barColor }} />
          </div>
          <span className="text-[10px] text-gray-500 tabular-nums w-6 text-right">{count}</span>
        </div>
      ))}
    </div>
  )
}

function OverlapSection({ title, itemsA, itemsB }: { title: string; itemsA: string[]; itemsB: string[] }) {
  const setA = new Set(itemsA)
  const setB = new Set(itemsB)
  const common = itemsA.filter(i => setB.has(i))
  const onlyA = itemsA.filter(i => !setB.has(i))
  const onlyB = itemsB.filter(i => !setA.has(i))

  return (
    <div className="bg-surface-2/40 rounded-xl p-4">
      <h3 className="text-[12px] font-medium text-gray-300 mb-2 uppercase tracking-wider">{title}</h3>
      {common.length > 0 && (
        <div className="mb-2">
          <span className="text-[10px] text-gray-500">Shared: </span>
          <span className="text-[11px] text-gray-300">{common.join(', ')}</span>
        </div>
      )}
      {onlyA.length > 0 && (
        <div className="mb-1">
          <span className="text-[10px] text-accent-blue">Only A: </span>
          <span className="text-[11px] text-gray-400">{onlyA.join(', ')}</span>
        </div>
      )}
      {onlyB.length > 0 && (
        <div>
          <span className="text-[10px] text-accent-purple">Only B: </span>
          <span className="text-[11px] text-gray-400">{onlyB.join(', ')}</span>
        </div>
      )}
      {common.length === 0 && onlyA.length === 0 && onlyB.length === 0 && (
        <div className="text-[11px] text-gray-500">None used</div>
      )}
    </div>
  )
}

function IocOverlap({ iocsA, iocsB }: { iocsA: Set<string>; iocsB: Set<string> }) {
  const common = [...iocsA].filter(i => iocsB.has(i))
  const onlyA = [...iocsA].filter(i => !iocsB.has(i))
  const onlyB = [...iocsB].filter(i => !iocsA.has(i))

  return (
    <div className="space-y-2">
      {common.length > 0 && (
        <div>
          <span className="text-[10px] text-yellow-400 font-medium">Shared ({common.length}): </span>
          <span className="text-[11px] text-gray-300 font-mono break-all">{common.slice(0, 20).join(', ')}{common.length > 20 ? ` +${common.length - 20} more` : ''}</span>
        </div>
      )}
      {onlyA.length > 0 && (
        <div>
          <span className="text-[10px] text-accent-blue">Only A ({onlyA.length}): </span>
          <span className="text-[11px] text-gray-400 font-mono break-all">{onlyA.slice(0, 10).join(', ')}{onlyA.length > 10 ? ` +${onlyA.length - 10} more` : ''}</span>
        </div>
      )}
      {onlyB.length > 0 && (
        <div>
          <span className="text-[10px] text-accent-purple">Only B ({onlyB.length}): </span>
          <span className="text-[11px] text-gray-400 font-mono break-all">{onlyB.slice(0, 10).join(', ')}{onlyB.length > 10 ? ` +${onlyB.length - 10} more` : ''}</span>
        </div>
      )}
      {common.length === 0 && onlyA.length === 0 && onlyB.length === 0 && (
        <div className="text-[11px] text-gray-500">No IOCs extracted</div>
      )}
    </div>
  )
}
