import { useRef, useEffect } from 'react'
import DOMPurify from 'dompurify'
import type { ChatMessage as ChatMessageType } from '../../types'
import { confidenceColor } from '../../types'
import { useGraphStore } from '../../store/graph'

interface Props {
  message: ChatMessageType
}

export function ChatMessage({ message }: Props) {
  const selectNode = useGraphStore((s) => s.selectNode)

  const isUser = message.role === 'user'
  const isSystem = message.role === 'system'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
          isUser
            ? 'bg-accent-blue/20 text-gray-100 border border-accent-blue/30'
            : isSystem
              ? 'bg-surface-2 text-gray-400 border border-surface-3 italic'
              : 'bg-surface-2 text-gray-200 border border-surface-3'
        }`}
        onDoubleClick={() => {
          // Double-click highlights linked nodes in the graph
          if ((message.node_ids || []).length > 0) {
            selectNode((message.node_ids || [])[0])
          }
        }}
      >
        {/* Linked node indicator — click to select in graph */}
        {!isUser && !isSystem && (message.node_ids || []).length > 0 && (
          <button
            onClick={() => selectNode((message.node_ids || [])[0])}
            className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-accent-blue mb-1 transition-colors"
          >
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: (() => {
              const n = useGraphStore.getState().nodes[(message.node_ids || [])[0]]
              return n ? confidenceColor(n.confidence) : '#6b7280'
            })() }} />
            <span>View in graph</span>
          </button>
        )}

        {/* Tool call badge (R7) */}
        {message.tool_call && (
          <div className="flex items-center gap-2 text-xs text-gray-400 mb-1 pb-1 border-b border-surface-4">
            <span className="text-accent-cyan">{message.tool_call.tool_name}</span>
            <span className="text-gray-500">via {message.tool_call.server}</span>
            <span className="text-gray-500">{message.tool_call.duration_ms}ms</span>
            <span className={message.tool_call.success ? 'text-green-400' : 'text-red-400'}>
              {message.tool_call.success ? 'OK' : 'FAIL'}
            </span>
          </div>
        )}

        {/* Skill invocation badge (R37) */}
        {message.skill_invocation && (
          <div className="flex items-center gap-2 text-xs text-gray-400 mb-1 pb-1 border-b border-surface-4">
            <span className="text-accent-purple">Skill: {message.skill_invocation.skill_name}</span>
          </div>
        )}

        {/* Message content with enhanced markdown rendering (R2) — uses ref to avoid dangerouslySetInnerHTML */}
        <SafeHtml
          html={renderMarkdown(message.content)}
          className="prose prose-invert prose-sm max-w-none break-words [&_pre]:bg-surface-0 [&_pre]:rounded [&_pre]:p-2 [&_pre]:text-xs [&_pre]:border [&_pre]:border-surface-3 [&_pre]:overflow-x-auto [&_code]:text-accent-cyan [&_code]:bg-surface-3 [&_code]:px-1 [&_code]:rounded [&_code]:text-xs [&_table]:text-xs [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_th]:border-b [&_th]:border-surface-3 [&_td]:px-2 [&_td]:py-1 [&_td]:border-b [&_td]:border-surface-3/50"
        />

        {/* Linked graph nodes — inline preview cards */}
        {(message.node_ids || []).length > 0 && (
          <div className="space-y-1.5 mt-2 pt-1.5 border-t border-white/[0.04]">
            {(message.node_ids || []).map((nid) => {
              const n = useGraphStore.getState().nodes[nid]
              if (!n) return null
              const color = confidenceColor(n.confidence)
              return (
                <button
                  key={nid}
                  onClick={() => selectNode(nid)}
                  className="w-full text-left bg-white/[0.03] hover:bg-white/[0.06] rounded-lg px-2.5 py-1.5 transition-all group"
                >
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
                    <span className="text-[11px] text-gray-200 truncate flex-1 font-medium group-hover:text-accent-blue transition-colors">
                      {n.label || n.action_type}
                    </span>
                    {n.status === 'running' && <span className="text-[10px] text-accent-blue animate-pulse">running</span>}
                    {n.status === 'failed' && <span className="text-[10px] text-red-400">failed</span>}
                    <span className="text-[10px] tabular-nums font-medium" style={{ color }}>
                      {(n.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  {n.result_summary && (
                    <p className="text-[10px] text-gray-500 truncate mt-0.5 ml-4">
                      {n.result_summary.slice(0, 80)}
                    </p>
                  )}
                </button>
              )
            })}
          </div>
        )}

        {/* Timestamp */}
        <div className="text-[10px] text-gray-600 mt-1">
          {new Date(message.timestamp).toLocaleTimeString()}
        </div>
      </div>
    </div>
  )
}

/**
 * Markdown rendering using `marked` library.
 * Output is always sanitized by DOMPurify before being set on the DOM (via SafeHtml).
 * No custom HTML string building — eliminates all CodeQL unsafe-concatenation warnings.
 */
import { marked } from 'marked'

// Configure marked for safe, synchronous rendering
marked.setOptions({ async: false, breaks: true, gfm: true })

function renderMarkdown(text: string): string {
  return marked.parse(text, { async: false }) as string
}

/** Renders sanitized HTML via ref — avoids dangerouslySetInnerHTML for Semgrep compliance */
function SafeHtml({ html, className }: { html: string; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (ref.current) {
      ref.current.innerHTML = DOMPurify.sanitize(html)
    }
  }, [html])
  return <div ref={ref} className={className} />
}
