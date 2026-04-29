import { useMemo } from 'react'
import { useGraphStore } from '../../store/graph'
import { useSessionStore } from '../../store/session'
import { confidenceColor } from '../../types'
import { detectPatterns } from '../../utils/pattern-detection'

interface Props {
  onClose: () => void
}

/** Investigation statistics summary panel */
export function InvestigationStats({ onClose }: Props) {
  const nodes = useGraphStore((s) => s.nodes)
  const edges = useGraphStore((s) => s.edges)
  const session = useSessionStore((s) => s.currentSession)

  const stats = useMemo(() => {
    const nodeList = Object.values(nodes)
    const confBuckets: Record<string, number> = { '0%': 0, '1-20%': 0, '21-40%': 0, '41-60%': 0, '61-80%': 0, '81-100%': 0 }
    const confBucketThresholds: [string, number, number][] = [
      ['0%', 0, 0], ['1-20%', 0.01, 0.2], ['21-40%', 0.21, 0.4],
      ['41-60%', 0.41, 0.6], ['61-80%', 0.61, 0.8], ['81-100%', 0.81, 1.0],
    ]
    const typeCounts: Record<string, number> = {}
    const allIOCs = new Set<string>()
    let totalDuration = 0
    let completed = 0
    let failed = 0
    let running = 0
    let needsReview = 0
    let deadEnds = 0
    let withNotes = 0
    let maxDepth = 0

    for (const node of nodeList) {
      for (const [label, lo, hi] of confBucketThresholds) {
        if (node.confidence >= lo && node.confidence <= hi) { confBuckets[label]++; break }
      }
      typeCounts[node.action_type] = (typeCounts[node.action_type] || 0) + 1
      totalDuration += node.duration_ms
      if (node.status === 'completed') completed++
      if (node.status === 'failed') failed++
      if (node.status === 'running') running++
      if (node.status === 'needs_review') needsReview++
      if (node.is_dead_end) deadEnds++
      if (node.investigator_notes) withNotes++
      // Count unique IOCs across all nodes
      if (node.result_raw) {
        const ips = node.result_raw.match(/\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/g)
        if (ips) ips.forEach(ip => allIOCs.add(ip))
        const hashes = node.result_raw.match(/0x[a-f0-9]{6,}/gi)
        if (hashes) hashes.forEach(h => allIOCs.add(h))
      }
    }

    // Calculate max depth via BFS
    const roots = nodeList.filter((n) => n.parent_ids.length === 0)
    for (const root of roots) {
      const queue: [string, number][] = [[root.node_id, 1]]
      const visited = new Set<string>()
      while (queue.length > 0) {
        const [id, depth] = queue.shift()!
        if (visited.has(id)) continue
        visited.add(id)
        maxDepth = Math.max(maxDepth, depth)
        const children = edges.filter((e) => e.source === id).map((e) => e.target)
        for (const cid of children) queue.push([cid, depth + 1])
      }
    }

    // Count branches (nodes with >1 child)
    const branchPoints = nodeList.filter((n) =>
      edges.filter((e) => e.source === n.node_id).length > 1
    ).length

    return {
      totalNodes: nodeList.length,
      totalEdges: edges.length,
      completed, failed, running, needsReview, deadEnds, withNotes, iocCount: allIOCs.size,
      confBuckets, confBucketThresholds, typeCounts,
      totalDuration,
      maxDepth,
      branchPoints,
      startedAt: session?.created_at,
      duration: session ? new Date().getTime() - new Date(session.created_at).getTime() : 0,
    }
  }, [nodes, edges, session])

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[100]" onClick={onClose}>
      <div className="bg-surface-1 border border-surface-3 rounded-xl p-6 w-[480px] max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-medium text-gray-200">Investigation Statistics</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-200">{'\u2715'}</button>
        </div>

        {/* Overall investigation score */}
        <InvestigationScore nodes={nodes} />

        {/* Overview */}
        <div className="grid grid-cols-3 gap-3 mb-4">
          <StatCard label="Nodes" value={stats.totalNodes} />
          <StatCard label="Edges" value={stats.totalEdges} />
          <StatCard label="Max Depth" value={stats.maxDepth} />
          <StatCard label="Branch Points" value={stats.branchPoints} />
          <StatCard label="Dead Ends" value={stats.deadEnds} />
          <StatCard label="IOCs Found" value={stats.iocCount} />
          <StatCard label="With Notes" value={stats.withNotes} />
          <StatCard label="Failed" value={stats.failed} />
        </div>

        {/* Status breakdown */}
        <div className="mb-4">
          <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">Status</h3>
          <div className="flex gap-2 text-xs">
            <span className="text-green-400">{stats.completed} completed</span>
            {stats.running > 0 && <span className="text-blue-400">{stats.running} running</span>}
            {stats.failed > 0 && <span className="text-red-400">{stats.failed} failed</span>}
            {stats.needsReview > 0 && <span className="text-yellow-400">{stats.needsReview} needs review</span>}
          </div>
          {stats.failed > 0 && (
            <button
              onClick={() => {
                // Reset all failed nodes to running so they can be retried
                const graph = useGraphStore.getState()
                for (const node of Object.values(graph.nodes)) {
                  if (node.status === 'failed') {
                    graph.updateNode(node.node_id, { status: 'needs_review' })
                  }
                }
              }}
              className="mt-2 text-[11px] bg-red-900/20 hover:bg-red-900/30 text-red-300 px-3 py-1 rounded-md transition-colors"
            >
              Mark all {stats.failed} failed nodes for review
            </button>
          )}
        </div>

        {/* Confidence distribution */}
        <div className="mb-4">
          <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">Confidence Distribution</h3>
          <div className="flex gap-1 h-6">
            {stats.confBucketThresholds.map(([label, lo]) => {
              const count = stats.confBuckets[label]
              if (count === 0) return null
              const pct = (count / stats.totalNodes) * 100
              const color = confidenceColor(lo)
              return (
                <div
                  key={label}
                  className="rounded flex items-center justify-center text-[9px] font-bold"
                  style={{
                    width: `${Math.max(pct, 8)}%`,
                    backgroundColor: color + '30',
                    color,
                  }}
                  title={`${label}: ${count} (${pct.toFixed(0)}%)`}
                >
                  {count}
                </div>
              )
            })}
          </div>
          <div className="flex gap-2 mt-1 text-[10px] text-gray-500">
            {stats.confBucketThresholds.map(([label, lo]) =>
              stats.confBuckets[label] > 0 ? (
                <span key={label} style={{ color: confidenceColor(lo) }}>
                  {label}: {stats.confBuckets[label]}
                </span>
              ) : null
            )}
          </div>
        </div>

        {/* Confidence trend over time */}
        <ConfidenceTrend nodes={nodes} />

        {/* Confidence calibration — agent vs investigator */}
        <ConfidenceCalibration nodes={nodes} />

        {/* Action type breakdown */}
        <div className="mb-4">
          <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">Action Types</h3>
          <div className="space-y-1">
            {Object.entries(stats.typeCounts).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
              <div key={type} className="flex items-center gap-2 text-xs">
                <span className="text-gray-400 w-[140px]">{type.replace(/_/g, ' ')}</span>
                <div className="flex-1 bg-surface-3 rounded-full h-2">
                  <div
                    className="bg-accent-blue rounded-full h-2"
                    style={{ width: `${(count / stats.totalNodes) * 100}%` }}
                  />
                </div>
                <span className="text-gray-500 w-6 text-right">{count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Timing */}
        <div className="mb-4">
          <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">Timing</h3>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-gray-500">Total query time</span>
              <div className="text-gray-300">{(stats.totalDuration / 1000).toFixed(1)}s</div>
            </div>
            <div>
              <span className="text-gray-500">Session duration</span>
              <div className="text-gray-300">{formatDuration(stats.duration)}</div>
            </div>
            <div>
              <span className="text-gray-500">Skills used</span>
              <div className="text-gray-300">{session?.skills_used.length || 0}</div>
            </div>
            <div>
              <span className="text-gray-500">Tools used</span>
              <div className="text-gray-300">{session?.tools_used.length || 0}</div>
            </div>
          </div>
        </div>

        {/* Detected patterns */}
        <DetectedPatterns nodes={nodes} />

        {/* Investigation coverage map */}
        <div className="mb-4">
          <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">Coverage Map</h3>
          <InvestigationCoverage nodes={nodes} />
        </div>

        {/* Key findings */}
        <KeyFindings nodes={nodes} />

        {/* Auto-investigate settings moved to Agent dropdown in SessionBar */}
      </div>
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-surface-2 rounded-lg px-3 py-2 text-center">
      <div className="text-lg font-bold text-gray-200">{value}</div>
      <div className="text-[10px] text-gray-500">{label}</div>
    </div>
  )
}

function formatDuration(ms: number): string {
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${s % 60}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

/** Weighted overall investigation score with rubric breakdown */
function InvestigationScore({ nodes }: { nodes: Record<string, import('../../types').InvestigationNode> }) {
  const score = useMemo(() => {
    const nodeList = Object.values(nodes)
    if (nodeList.length === 0) return null

    // Rubric: weighted average of multiple factors
    const maxConf = Math.max(0, ...nodeList.map(n => n.confidence))
    const avgConf = nodeList.reduce((s, n) => s + n.confidence, 0) / nodeList.length
    const completionRate = nodeList.filter(n => n.status === 'completed').length / nodeList.length
    const coverageScore = Math.min(1, nodeList.length / 10) // More nodes = better coverage, up to 10
    const highFindingsBonus = Math.min(1, nodeList.filter(n => n.confidence > 0.5).length / 3)

    // Weighted composite
    const composite = (
      maxConf * 0.35 +        // 35%: highest single finding
      avgConf * 0.15 +        // 15%: average across all nodes
      completionRate * 0.2 +  // 20%: investigation completion rate
      coverageScore * 0.15 +  // 15%: breadth of investigation
      highFindingsBonus * 0.15 // 15%: number of high-confidence findings
    )

    return {
      composite,
      maxConf,
      avgConf,
      completionRate,
      coverageScore,
      highFindingsBonus,
    }
  }, [nodes])

  if (!score) return null

  const label = score.composite > 0.7 ? 'Critical'
    : score.composite > 0.5 ? 'High'
    : score.composite > 0.3 ? 'Medium'
    : score.composite > 0.1 ? 'Low'
    : 'Benign'

  return (
    <div className="mb-4 bg-surface-2/40 rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-medium text-gray-400 uppercase">Investigation Score</h3>
        <div className="flex items-center gap-2">
          <span className="text-[20px] font-bold tabular-nums" style={{ color: confidenceColor(score.composite) }}>
            {(score.composite * 100).toFixed(0)}%
          </span>
          <span className="text-[11px] font-medium" style={{ color: confidenceColor(score.composite) }}>
            {label}
          </span>
        </div>
      </div>
      {/* Rubric breakdown */}
      <div className="grid grid-cols-5 gap-1 text-[10px]">
        {[
          { label: 'Max finding', value: score.maxConf, weight: '35%' },
          { label: 'Avg score', value: score.avgConf, weight: '15%' },
          { label: 'Completion', value: score.completionRate, weight: '20%' },
          { label: 'Coverage', value: score.coverageScore, weight: '15%' },
          { label: 'High finds', value: score.highFindingsBonus, weight: '15%' },
        ].map(r => (
          <div key={r.label} className="text-center">
            <div className="h-1 bg-surface-3 rounded-full mb-1 overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${r.value * 100}%`, backgroundColor: confidenceColor(r.value) }} />
            </div>
            <div className="text-gray-500">{r.label}</div>
            <div className="text-gray-400 tabular-nums">{(r.value * 100).toFixed(0)}%</div>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Aggregated key findings from high-confidence nodes */
function KeyFindings({ nodes }: { nodes: Record<string, import('../../types').InvestigationNode> }) {
  const findings = useMemo(() => {
    return Object.values(nodes)
      .filter(n => n.confidence > 0.5 && n.status === 'completed' && n.result_summary)
      .sort((a, b) => b.confidence - a.confidence)
      .slice(0, 8)
  }, [nodes])

  if (findings.length === 0) return null

  return (
    <div className="mb-4">
      <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">Key Findings</h3>
      <div className="space-y-1.5 max-h-[160px] overflow-y-auto">
        {findings.map(n => (
          <div key={n.node_id} className="bg-surface-2/40 rounded-lg px-3 py-2">
            <div className="flex items-center gap-2 mb-0.5">
              <span className="text-[10px] font-bold tabular-nums" style={{ color: confidenceColor(n.confidence) }}>
                {(n.confidence * 100).toFixed(0)}%
              </span>
              <span className="text-[11px] text-gray-200 truncate">{n.label}</span>
            </div>
            <p className="text-[10px] text-gray-400 line-clamp-2">{n.result_summary}</p>
            {(n.tags || []).length > 0 && (
              <div className="flex gap-1 mt-1">
                {(n.tags || []).map(t => (
                  <span key={t} className="text-[9px] bg-accent-purple/10 text-accent-purple px-1.5 py-0.5 rounded">{t}</span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

/** Shows nodes where investigator overrode agent confidence — calibration insights */
function ConfidenceCalibration({ nodes }: { nodes: Record<string, import('../../types').InvestigationNode> }) {
  const overridden = useMemo(() => {
    return Object.values(nodes).filter(n => n.confidence_override)
  }, [nodes])

  if (overridden.length === 0) return null

  return (
    <div className="mb-4">
      <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">Calibration ({overridden.length} overrides)</h3>
      <div className="space-y-1 max-h-[120px] overflow-y-auto">
        {overridden.map(n => (
          <div key={n.node_id} className="flex items-center gap-2 text-[11px]">
            <span className="text-gray-400 truncate w-[160px]">{n.label}</span>
            <span className="font-bold tabular-nums" style={{ color: confidenceColor(n.confidence) }}>
              {(n.confidence * 100).toFixed(0)}%
            </span>
            <span className="text-gray-600">(overridden)</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** SVG sparkline showing confidence scores in chronological order */
function ConfidenceTrend({ nodes }: { nodes: Record<string, import('../../types').InvestigationNode> }) {
  const data = useMemo(() => {
    return Object.values(nodes)
      .filter(n => n.timestamp)
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
      .map(n => n.confidence)
  }, [nodes])

  if (data.length < 2) return null

  const w = 420
  const h = 48
  const stepX = w / (data.length - 1)

  const points = data.map((v, i) => `${i * stepX},${h - v * h}`).join(' ')
  const areaPoints = `0,${h} ${points} ${(data.length - 1) * stepX},${h}`

  return (
    <div className="mb-4">
      <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">Confidence Trend</h3>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-12 rounded-lg bg-surface-2/40">
        <polygon points={areaPoints} fill="url(#trendGrad)" opacity="0.3" />
        <polyline points={points} fill="none" stroke="rgb(59,130,246)" strokeWidth="1.5" strokeLinejoin="round" />
        {data.map((v, i) => (
          <circle key={i} cx={i * stepX} cy={h - v * h} r="2" fill={confidenceColor(v)} />
        ))}
        <defs>
          <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgb(59,130,246)" />
            <stop offset="100%" stopColor="transparent" />
          </linearGradient>
        </defs>
      </svg>
      <div className="flex justify-between text-[10px] text-gray-500 mt-1">
        <span>{data.length} nodes</span>
        <span>avg {(data.reduce((a, b) => a + b, 0) / data.length * 100).toFixed(0)}%</span>
      </div>
    </div>
  )
}

/** Shows which skills, tools, and Trino tables were queried */
/** Shows automatically detected abuse patterns across the investigation */
function DetectedPatterns({ nodes }: { nodes: Record<string, import('../../types').InvestigationNode> }) {
  const patterns = useMemo(() => detectPatterns(nodes), [nodes])

  if (patterns.length === 0) return null

  const PATTERN_ICONS: Record<string, string> = {
    ip_clustering: '\u{1F310}',
    geo_concentration: '\u{1F30D}',
    temporal_burst: '\u{23F0}',
    device_reuse: '\u{1F4F1}',
    domain_family: '\u{1F4E7}',
    high_volume_entity: '\u{1F4CA}',
  }

  return (
    <div className="mb-4">
      <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">Detected Patterns ({patterns.length})</h3>
      <div className="space-y-2">
        {patterns.map((p, i) => (
          <div key={i} className="bg-surface-2/40 rounded-lg px-3 py-2">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm">{PATTERN_ICONS[p.type] || '\u2022'}</span>
              <span className="text-[11px] text-gray-200 flex-1">{p.description}</span>
              <span className="text-[10px] font-bold tabular-nums" style={{ color: confidenceColor(p.confidence) }}>
                {(p.confidence * 100).toFixed(0)}%
              </span>
            </div>
            {p.evidence.length > 0 && (
              <div className="text-[10px] text-gray-500 ml-6 font-mono">
                {p.evidence.slice(0, 3).join(' | ')}
                {p.evidence.length > 3 && ` +${p.evidence.length - 3} more`}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function InvestigationCoverage({ nodes }: { nodes: Record<string, import('../../types').InvestigationNode> }) {
  const coverage = useMemo(() => {
    const skills = new Set<string>()
    const tools = new Set<string>()
    const tableNodes = new Map<string, string[]>() // table → node labels

    for (const node of Object.values(nodes)) {
      if (node.skill_name) skills.add(node.skill_name)
      if (node.tool_name) tools.add(node.tool_name)
      if (node.query) {
        const tableMatches = node.query.matchAll(/FROM\s+(\S+)/gi)
        for (const m of tableMatches) {
          const table = m[1].replace(/[()]/g, '')
          if (table && !table.startsWith('(') && !table.startsWith("'")) {
            if (!tableNodes.has(table)) tableNodes.set(table, [])
            tableNodes.get(table)!.push(node.label.slice(0, 30))
          }
        }
        const joinMatches = node.query.matchAll(/JOIN\s+(\S+)/gi)
        for (const m of joinMatches) {
          const table = m[1].replace(/[()]/g, '')
          if (table && !table.startsWith('(')) {
            if (!tableNodes.has(table)) tableNodes.set(table, [])
            tableNodes.get(table)!.push(node.label.slice(0, 30))
          }
        }
      }
    }
    return { skills: [...skills], tools: [...tools], tableNodes }
  }, [nodes])

  if (coverage.skills.length === 0 && coverage.tools.length === 0 && coverage.tableNodes.size === 0) {
    return <p className="text-[11px] text-gray-500">No queries or skills used yet</p>
  }

  return (
    <div className="space-y-2">
      {coverage.tableNodes.size > 0 && (
        <div>
          <span className="text-[10px] text-gray-500 uppercase">Tables queried ({coverage.tableNodes.size})</span>
          <div className="flex flex-wrap gap-1 mt-1">
            {[...coverage.tableNodes.entries()].map(([t, nodeLabels]) => (
              <span
                key={t}
                className="text-[10px] bg-accent-cyan/10 text-accent-cyan px-1.5 py-0.5 rounded font-mono"
                title={`Used by: ${[...new Set(nodeLabels)].join(', ')}`}
              >
                {t} ({new Set(nodeLabels).size})
              </span>
            ))}
          </div>
        </div>
      )}
      {coverage.tools.length > 0 && (
        <div>
          <span className="text-[10px] text-gray-500 uppercase">Tools ({coverage.tools.length})</span>
          <div className="flex flex-wrap gap-1 mt-1">
            {coverage.tools.map(t => (
              <span key={t} className="text-[10px] bg-accent-blue/10 text-accent-blue px-1.5 py-0.5 rounded">
                {t}
              </span>
            ))}
          </div>
        </div>
      )}
      {coverage.skills.length > 0 && (
        <div>
          <span className="text-[10px] text-gray-500 uppercase">Skills ({coverage.skills.length})</span>
          <div className="flex flex-wrap gap-1 mt-1">
            {coverage.skills.map(s => (
              <span key={s} className="text-[10px] bg-accent-purple/10 text-accent-purple px-1.5 py-0.5 rounded">
                {s}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
