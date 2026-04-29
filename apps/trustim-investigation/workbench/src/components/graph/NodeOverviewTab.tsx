import { useState } from 'react'
import { useGraphStore } from '../../store/graph'
import { useSessionStore } from '../../store/session'
import { confidenceColor } from '../../types'
import { checkSevThresholds, formatSevAssessment } from '../../utils/sev-checker'
import { NotebookCellSection } from './NotebookCellSection'

interface NodeOverviewTabProps {
  nodeId: string
}

export function NodeOverviewTab({ nodeId }: NodeOverviewTabProps) {
  const node = useGraphStore(s => s.nodes[nodeId])
  const selectNode = useGraphStore(s => s.selectNode)
  const overrideConfidence = useGraphStore(s => s.overrideConfidence)
  const setChatContext = useSessionStore(s => s.setChatContext)
  const [showConfidencePicker, setShowConfidencePicker] = useState(false)

  if (!node) return null

  return (
    <>
      {/* Breadcrumb trail — shows path from root to this node */}
      {(node.parent_ids || []).length > 0 && (
        <div className="px-4 py-2 border-b border-surface-3/50 flex items-center gap-1 text-[11px] text-gray-500 overflow-x-auto flex-shrink-0">
          {useGraphStore.getState().getAncestors(nodeId).reverse().map((pid, i) => {
            const parent = useGraphStore.getState().nodes[pid]
            return (
              <span key={pid} className="flex items-center gap-1 flex-shrink-0">
                {i > 0 && <span className="text-gray-600">{'\u203A'}</span>}
                <button
                  onClick={() => selectNode(pid)}
                  className="hover:text-accent-blue transition-colors truncate max-w-[100px]"
                  title={parent?.label}
                >
                  {parent?.label?.slice(0, 20) || pid.slice(0, 8)}
                </button>
              </span>
            )
          })}
          <span className="text-gray-600">{'\u203A'}</span>
          <span className="text-gray-300 font-medium truncate max-w-[100px]">{node.label?.slice(0, 20) || 'Current'}</span>
        </div>
      )}

      {/* Threat Score — PRD Section 3.2 */}
      <section className="px-4 py-3 border-b border-surface-3">
        <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">Threat Score</h3>
        <div className="flex items-center gap-3 mb-2">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center text-[13px] font-bold"
            style={{
              backgroundColor: confidenceColor(node.confidence),
              color: '#fff',
              textShadow: '0 1px 2px rgba(0,0,0,0.3)',
            }}
          >
            {(node.confidence * 100).toFixed(0)}
          </div>
          <div className="flex-1">
            <div className="text-[13px] text-gray-200 font-medium">
              {node.confidence <= 0 ? 'Not assessed' : `${(node.confidence * 100).toFixed(0)}%`}
              {node.confidence_override && (
                <span className="text-[10px] text-yellow-400 ml-2">manually set</span>
              )}
            </div>
            <div className="text-[11px] text-gray-500">
              {node.confidence_reasoning || (node.confidence <= 0 ? 'Agent has not scored this node' : 'Agent threat assessment')}
            </div>
          </div>
          <button
            onClick={() => setShowConfidencePicker(!showConfidencePicker)}
            className="text-xs text-gray-400 hover:text-gray-200"
          >
            {showConfidencePicker ? 'Done' : 'Override'}
          </button>
        </div>
        {/* PRD: "slider 0.0 to 1.0" for manual override */}
        {showConfidencePicker && (
          <div className="mt-1">
            <input
              type="range"
              min="0"
              max="100"
              value={Math.round(node.confidence * 100)}
              onChange={(e) => overrideConfidence(nodeId, parseInt(e.target.value) / 100)}
              className="w-full h-2 rounded-lg appearance-none cursor-pointer"
              style={{
                background: `linear-gradient(to right, hsl(120, 70%, 45%), hsl(60, 80%, 45%), hsl(0, 85%, 42%))`,
              }}
            />
            <div className="flex justify-between text-[10px] text-gray-500 mt-1">
              <span>0% — Nothing notable</span>
              <span>100% — Most concerning</span>
            </div>
          </div>
        )}
        {showConfidencePicker && (
          <div className="flex gap-1 mt-2">
            {[0, 0.2, 0.4, 0.6, 0.8, 1.0].map((c) => (
              <button
                key={c}
                onClick={() => { overrideConfidence(nodeId, c); setShowConfidencePicker(false) }}
                className="px-2 py-1 text-xs rounded hover:opacity-80 transition-opacity"
                style={{
                  backgroundColor: confidenceColor(c) + '30',
                  color: confidenceColor(c),
                }}
              >
                {(c * 100).toFixed(0)}%
              </button>
            ))}
          </div>
        )}
      </section>

      {/* Automated SEV assessment when WoW data is present */}
      {node.status === 'completed' && node.result_raw && (() => {
        const sevResults = checkSevThresholds(node.result_raw, node.label)
        if (sevResults.length === 0) return null
        return (
          <section className="px-4 py-2.5 border-b border-surface-3 bg-surface-2/20">
            <h3 className="text-xs font-medium text-gray-400 uppercase mb-1.5">SEV Assessment</h3>
            <div className="space-y-1">
              {sevResults.map((s, i) => (
                <div key={i} className="flex items-center gap-2 text-[11px]">
                  {s.sevLevel ? (
                    <span className={`font-bold px-1.5 py-0.5 rounded text-[10px] ${
                      s.sevLevel === 1 ? 'bg-red-900/40 text-red-300' :
                      s.sevLevel === 2 ? 'bg-orange-900/40 text-orange-300' :
                      s.sevLevel === 3 ? 'bg-yellow-900/40 text-yellow-300' :
                      'bg-surface-3 text-gray-400'
                    }`}>SEV-{s.sevLevel}</span>
                  ) : (
                    <span className="text-[10px] text-gray-500 px-1.5 py-0.5 bg-surface-3 rounded">No SEV</span>
                  )}
                  <span className="text-gray-300">{formatSevAssessment(s)}</span>
                </div>
              ))}
            </div>
          </section>
        )
      })()}

      {/* Q4: Paused for input — skill needs investigator choice */}
      {node.status === 'paused_for_input' && node.input_prompt && (
        <section className="px-4 py-3 border-b border-yellow-900/30 bg-yellow-900/10">
          <h3 className="text-xs font-medium text-yellow-400 uppercase mb-2">Input Required</h3>
          <p className="text-sm text-gray-200 mb-3">{node.input_prompt}</p>
          {node.input_choices && node.input_choices.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {node.input_choices.map((choice) => (
                <button
                  key={choice}
                  onClick={() => {
                    useGraphStore.getState().updateNode(nodeId, {
                      status: 'running',
                      input_prompt: null,
                      input_choices: null,
                      result_raw: node.result_raw
                        ? `${node.result_raw}\n\nInvestigator chose: ${choice}`
                        : `Investigator chose: ${choice}`,
                    })
                    useSessionStore.getState().addMessage('user', `Selected: ${choice}`)
                  }}
                  className="text-xs bg-yellow-900/30 hover:bg-yellow-900/50 text-yellow-300 border border-yellow-900/40 px-3 py-1.5 rounded-lg transition-colors"
                >
                  {choice}
                </button>
              ))}
            </div>
          ) : (
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="Type your response..."
                className="flex-1 bg-surface-2 border border-yellow-900/40 rounded px-2 py-1.5 text-xs text-gray-200 placeholder-gray-500 focus:border-yellow-400 focus:outline-none"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.target as HTMLInputElement).value.trim()) {
                    const val = (e.target as HTMLInputElement).value.trim()
                    useGraphStore.getState().updateNode(nodeId, {
                      status: 'running',
                      input_prompt: null,
                      result_raw: node.result_raw
                        ? `${node.result_raw}\n\nInvestigator input: ${val}`
                        : `Investigator input: ${val}`,
                    })
                    useSessionStore.getState().addMessage('user', val)
                  }
                }}
              />
            </div>
          )}
        </section>
      )}

      {/* Query Section */}
      <section className="px-4 py-3 border-b border-surface-3">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-medium text-gray-400 uppercase">Query / Instruction</h3>
          <div className="flex gap-2">
            {/* Copy as executable SQL (strips comments, adds SET SESSION) */}
            {node.query && (node.tool_name === 'execute_trino_query' || node.query.toLowerCase().includes('select')) && (
              <button
                onClick={() => {
                  const sql = node.query.replace(/^--.*$/gm, '').trim()
                  const withAuth = `SET SESSION li_authorization_user = 'trustim';\n\n${sql}`
                  navigator.clipboard.writeText(withAuth)
                }}
                className="text-[10px] text-accent-cyan hover:text-cyan-300 transition-colors"
              >
                Copy SQL
              </button>
            )}
            <button
              onClick={() => navigator.clipboard.writeText(node.query)}
              className="text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
            >
              Copy
            </button>
          </div>
        </div>
        <pre className="bg-surface-0 rounded-xl p-3 text-[12px] text-gray-300 overflow-x-auto whitespace-pre-wrap font-mono border border-white/[0.04] max-h-[200px] overflow-y-auto leading-relaxed">
          {node.query || '(no query)'}
        </pre>
        {Object.keys(node.parameters || {}).length > 0 && (
          <details className="mt-2">
            <summary className="text-[10px] text-gray-500 cursor-pointer">Parameters</summary>
            <pre className="bg-surface-0 rounded p-2 text-[10px] text-gray-400 mt-1 overflow-auto max-h-[100px]">
              {JSON.stringify(node.parameters, null, 2)}
            </pre>
          </details>
        )}
      </section>

      {/* Agent Reasoning (R38) */}
      {node.reasoning && (
        <section className="px-4 py-3 border-b border-surface-3">
          <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">Agent Reasoning</h3>
          <p className="text-xs text-gray-300 leading-relaxed whitespace-pre-wrap">{node.reasoning}</p>
        </section>
      )}

      {/* ipynb Cells — PRD Section 4 */}
      {node.query && node.status === 'completed' && (
        <NotebookCellSection node={node} nodeId={nodeId} setChatContext={setChatContext} selectNode={selectNode} />
      )}

      {/* Metadata */}
      <section className="px-4 py-3 border-b border-surface-3">
        <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">Metadata</h3>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div>
            <span className="text-gray-500">Action Type</span>
            <div className="text-gray-300">{node.action_type.replace(/_/g, ' ')}</div>
          </div>
          <div>
            <span className="text-gray-500">Status</span>
            <div className={`${
              node.status === 'completed' ? 'text-green-400' :
              node.status === 'failed' ? 'text-red-400' :
              node.status === 'running' ? 'text-blue-400' :
              'text-yellow-400'
            }`}>{node.status}</div>
          </div>
          {node.skill_name && (
            <div>
              <span className="text-gray-500">Skill</span>
              <div className="text-accent-purple">{node.skill_name}</div>
            </div>
          )}
          {node.tool_name && (
            <div>
              <span className="text-gray-500">Tool</span>
              <div className="text-accent-cyan">{node.tool_name}</div>
            </div>
          )}
          {node.source_tool && (
            <div>
              <span className="text-gray-500">Source</span>
              <div className="text-gray-300">{node.source_tool}</div>
            </div>
          )}
          <div>
            <span className="text-gray-500">Parents</span>
            <div className="text-gray-300">{(node.parent_ids || []).length === 0 ? 'Root' : (node.parent_ids || []).map(id => id.slice(0, 8)).join(', ')}</div>
          </div>
        </div>
      </section>
    </>
  )
}
