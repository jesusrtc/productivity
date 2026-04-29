import { useState } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import type { InvestigationNode } from '../../types'
import type { ChatContext } from '../../store/session'

const syntaxTheme = oneDark

interface NotebookCellSectionProps {
  node: InvestigationNode
  nodeId: string
  setChatContext: (ctx: ChatContext | null) => void
  selectNode: (id: string | null) => void
}

/**
 * PRD Section 4.2: Notebook cell with edit-and-rerun capability.
 * Shows the node's query as an ipynb-style code cell with output.
 * The investigator can edit the query and re-execute it — the modified
 * execution becomes a new child node in the graph.
 */
export function NotebookCellSection({ node, nodeId, setChatContext, selectNode }: NotebookCellSectionProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [editedQuery, setEditedQuery] = useState(node.query)
  const [showFullOutput, setShowFullOutput] = useState(false)

  const isSQL = node.tool_name === 'execute_trino_query' || node.query.toLowerCase().includes('select')

  return (
    <section className="px-4 py-3 border-b border-surface-3">
      <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">Notebook Cell</h3>
      <div className="bg-surface-0 rounded-xl border border-white/[0.04] overflow-hidden">
        {/* Cell header */}
        <div className="flex items-center gap-2 px-3 py-1.5 border-b border-white/[0.04] bg-surface-2/30">
          <span className="text-[10px] text-gray-500 uppercase font-mono">{isSQL ? 'SQL' : 'Code'}</span>
          {node.duration_ms > 0 && (
            <>
              <span className="text-[10px] text-gray-600">|</span>
              <span className="text-[10px] text-gray-500 tabular-nums">{(node.duration_ms / 1000).toFixed(1)}s</span>
            </>
          )}
          <div className="ml-auto flex gap-1.5">
            <button
              onClick={() => navigator.clipboard.writeText(isEditing ? editedQuery : node.query)}
              className="text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
            >
              Copy
            </button>
            <button
              onClick={() => { setIsEditing(!isEditing); setEditedQuery(node.query) }}
              className={`text-[10px] transition-colors ${isEditing ? 'text-yellow-400' : 'text-gray-500 hover:text-gray-300'}`}
            >
              {isEditing ? 'Cancel edit' : 'Edit'}
            </button>
            {isEditing ? (
              <button
                onClick={() => {
                  // PRD 4.2: "The modified execution becomes a new child node"
                  const queryText = isSQL
                    ? `Run this modified query:\n\`\`\`sql\n${editedQuery}\n\`\`\``
                    : editedQuery
                  window.dispatchEvent(new CustomEvent('executeFromNode', {
                    detail: { query: queryText, parentNodeId: node.node_id, label: `Edit of: ${node.label}` }
                  }))
                  setIsEditing(false)
                  selectNode(null)
                }}
                className="text-[10px] bg-accent-cyan/20 text-accent-cyan hover:bg-accent-cyan/30 px-1.5 py-0.5 rounded font-medium transition-colors"
              >
                Run edited
              </button>
            ) : (
              <button
                onClick={() => {
                  // Direct execution — sends query to Claude and creates child node automatically
                  const queryText = isSQL
                    ? `Run this SQL query using execute_trino_query:\n\`\`\`sql\n${node.query}\n\`\`\``
                    : node.query
                  window.dispatchEvent(new CustomEvent('executeFromNode', {
                    detail: { query: queryText, parentNodeId: node.node_id, label: `Re-run: ${node.label}` }
                  }))
                  selectNode(null)
                }}
                className="text-[10px] bg-accent-cyan/20 text-accent-cyan hover:bg-accent-cyan/30 px-1.5 py-0.5 rounded font-medium transition-colors"
              >
                Execute
              </button>
            )}
          </div>
        </div>

        {/* Code cell — editable or read-only */}
        {isEditing ? (
          <textarea
            value={editedQuery}
            onChange={(e) => setEditedQuery(e.target.value)}
            className="w-full px-3 py-2 text-[11px] text-gray-200 font-mono leading-relaxed bg-surface-0 border-0 resize-y min-h-[80px] max-h-[200px] focus:outline-none focus:ring-1 focus:ring-accent-cyan/30"
            spellCheck={false}
          />
        ) : isSQL ? (
          <SyntaxHighlighter language="sql" style={syntaxTheme} customStyle={{ fontSize: '11px', padding: '8px 12px', margin: 0, maxHeight: '120px', overflow: 'auto', background: 'transparent' }}>
            {node.query}
          </SyntaxHighlighter>
        ) : (
          <pre className="px-3 py-2 text-[11px] text-gray-300 font-mono leading-relaxed overflow-x-auto max-h-[120px] overflow-y-auto">
            {node.query}
          </pre>
        )}

        {/* Output cell */}
        {node.result_raw && !isEditing && (
          <>
            <div className="border-t border-white/[0.04] px-3 py-1 bg-surface-2/20">
              <span className="text-[10px] text-gray-500 uppercase font-mono">Output</span>
            </div>
            <pre className={`px-3 py-2 text-[11px] text-gray-400 font-mono leading-relaxed overflow-x-auto ${showFullOutput ? 'max-h-[400px]' : 'max-h-[120px]'} overflow-y-auto`}>
              {showFullOutput ? node.result_raw : node.result_raw.slice(0, 2000)}
              {!showFullOutput && (node.result_raw || '').length > 2000 && '\n... (truncated)'}
            </pre>
            {(node.result_raw || '').length > 2000 && (
              <button
                onClick={() => setShowFullOutput(!showFullOutput)}
                className="w-full text-[10px] text-gray-500 hover:text-gray-300 py-1 border-t border-white/[0.04] transition-colors"
              >
                {showFullOutput ? 'Show less' : `Show all (${((node.result_raw || '').length / 1024).toFixed(1)}KB)`}
              </button>
            )}
          </>
        )}
      </div>
    </section>
  )
}
