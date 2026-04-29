import { useState } from 'react'

interface ChatFilterProps {
  messages: { id: string; content: string; role: string }[]
  onJumpTo: (id: string) => void
}

/** Compact chat filter for long investigations */
export function ChatFilter({ messages, onJumpTo }: ChatFilterProps) {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="text-[10px] text-gray-500 hover:text-gray-300 transition-colors" title="Search chat messages">
        {'\u{1F50D}'}
      </button>
    )
  }

  const lf = filter.toLowerCase()
  const matches = lf.length >= 2
    ? messages.filter(m => m.content.toLowerCase().includes(lf)).slice(0, 8)
    : []

  return (
    <div className="relative">
      <input
        type="text"
        value={filter}
        onChange={e => setFilter(e.target.value)}
        placeholder="Filter chat..."
        className="bg-surface-2 border border-surface-4 rounded px-2 py-0.5 text-[10px] text-gray-200 w-[120px] focus:outline-none focus:border-accent-blue/50"
        autoFocus
        onKeyDown={e => { if (e.key === 'Escape') { setOpen(false); setFilter('') } }}
      />
      {matches.length > 0 && (
        <div className="absolute right-0 top-full mt-1 bg-surface-2 border border-surface-4 rounded-lg shadow-xl z-50 w-[250px] max-h-[200px] overflow-y-auto py-1">
          {matches.map(m => (
            <button
              key={m.id}
              onClick={() => { onJumpTo(m.id); setOpen(false); setFilter('') }}
              className="w-full text-left px-2 py-1 text-[10px] text-gray-300 hover:bg-surface-3 transition-colors truncate"
            >
              <span className={m.role === 'user' ? 'text-accent-blue' : m.role === 'system' ? 'text-gray-500' : 'text-gray-300'}>
                {m.content.slice(0, 80)}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
