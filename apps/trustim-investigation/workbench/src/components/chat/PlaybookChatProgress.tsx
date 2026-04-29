import { useState, useEffect } from 'react'
import { playbooksApi } from '../../api'

interface PlaybookChatProgressProps {
  sessionId: string
}

/** Inline playbook progress for the chat panel */
export function PlaybookChatProgress({ sessionId }: PlaybookChatProgressProps) {
  const [execs, setExecs] = useState<Array<{ id: string; status: string; playbook_id: string; node_states: Record<string, { status: string }> }>>([])

  useEffect(() => {
    const poll = () => {
      playbooksApi.listExecutions()
        .then((all: any) => setExecs(all.filter((e: any) => e.session_id === sessionId)))
        .catch(() => {})
    }
    poll()
    const timer = setInterval(poll, 3000)
    return () => clearInterval(timer)
  }, [sessionId])

  if (execs.length === 0) return null

  return (
    <>
      {execs.map(exec => {
        const states = Object.values(exec.node_states)
        const total = states.length
        const completed = states.filter(s => s.status === 'completed').length
        const failed = states.filter(s => s.status === 'failed').length
        const running = states.filter(s => s.status === 'running').length
        const done = completed + failed

        return (
          <div key={exec.id} className="bg-green-900/10 border border-green-900/20 rounded-xl p-2.5 flex items-center gap-2 animate-[fadeIn_0.2s_ease-out]">
            <span className="text-[10px] bg-green-600 text-white px-1.5 py-0.5 rounded font-medium">PB</span>
            <div className="flex-1 h-1.5 bg-surface-3 rounded-full overflow-hidden flex">
              <div className="h-full bg-green-500 transition-all" style={{ width: `${total > 0 ? (completed / total) * 100 : 0}%` }} />
              {failed > 0 && <div className="h-full bg-red-500/60" style={{ width: `${(failed / total) * 100}%` }} />}
            </div>
            <span className="text-[10px] text-gray-500 tabular-nums">{done}/{total}</span>
            {running > 0 && <span className="text-[10px] text-yellow-400">{running} active</span>}
            {exec.status !== 'running' && <span className="text-[10px] text-green-400">{exec.status}</span>}
          </div>
        )
      })}
    </>
  )
}
