import { useState } from 'react'
import { useGraphStore } from '../../store/graph'

interface NodeNotesTabProps {
  nodeId: string
}

export function NodeNotesTab({ nodeId }: NodeNotesTabProps) {
  const node = useGraphStore(s => s.nodes[nodeId])
  const addInvestigatorNote = useGraphStore(s => s.addInvestigatorNote)
  const [noteText, setNoteText] = useState('')

  if (!node) return null

  const handleAddNote = () => {
    if (noteText.trim()) {
      const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      addInvestigatorNote(nodeId, `[${timestamp}] ${noteText.trim()}`)
      setNoteText('')
    }
  }

  return (
    <>
      {/* Investigator Notes (R20 — add, edit, delete) */}
      <section className="px-4 py-3 border-b border-surface-3">
        <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">Investigator Notes</h3>
        {node.investigator_notes && (
          <div className="space-y-1 mb-2">
            {node.investigator_notes.split('\n\n').map((note, i) => (
              <div key={i} className="group flex items-start gap-1 bg-surface-0 rounded p-2 border border-surface-3">
                <p className="flex-1 text-xs text-gray-300 whitespace-pre-wrap">{note}</p>
                <button
                  onClick={() => {
                    const notes = node.investigator_notes.split('\n\n')
                    notes.splice(i, 1)
                    useGraphStore.getState().setInvestigatorNotes(nodeId, notes.join('\n\n'))
                  }}
                  className="opacity-0 group-hover:opacity-100 text-[10px] text-gray-500 hover:text-red-400 transition-opacity flex-shrink-0"
                  title="Delete note"
                >
                  {'\u2715'}
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="flex gap-2">
          <input
            type="text"
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAddNote()}
            placeholder="Add a note... (N)"
            data-note-input
            className="flex-1 bg-surface-2 border border-surface-4 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-500 focus:border-accent-blue focus:outline-none"
          />
          <button
            onClick={handleAddNote}
            disabled={!noteText.trim()}
            className="text-xs bg-surface-3 hover:bg-surface-4 disabled:opacity-30 text-gray-300 px-2 py-1 rounded transition-colors"
          >
            Add
          </button>
        </div>
        {/* Quick-note buttons */}
        <div className="flex gap-1 mt-1.5">
          {['Confirmed abuse', 'False positive', 'Needs deeper review', 'Escalate to team'].map(q => (
            <button
              key={q}
              onClick={() => {
                const ts = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                addInvestigatorNote(nodeId, `[${ts}] ${q}`)
              }}
              className="text-[9px] bg-surface-2 hover:bg-surface-3 text-gray-500 hover:text-gray-300 px-1.5 py-0.5 rounded transition-colors"
            >
              {q}
            </button>
          ))}
        </div>
      </section>
      {/* Tags — custom investigator labels */}
      <section className="px-4 py-3 border-b border-surface-3">
        <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">Tags</h3>
        <div className="flex flex-wrap gap-1 mb-2">
          {(node.tags || []).map(tag => (
            <span key={tag} className="group text-[11px] bg-accent-purple/15 text-accent-purple px-2 py-0.5 rounded-md flex items-center gap-1">
              {tag}
              <button
                onClick={() => useGraphStore.getState().removeTag(nodeId, tag)}
                className="opacity-0 group-hover:opacity-100 text-accent-purple/50 hover:text-accent-purple transition-opacity"
              >
                {'\u2715'}
              </button>
            </span>
          ))}
          {(node.tags || []).length === 0 && (
            <span className="text-[11px] text-gray-500">No tags</span>
          )}
        </div>
        <div className="flex gap-1 flex-wrap">
          {['IOC', 'escalate', 'false-positive', 'confirmed', 'needs-review'].map(tag => (
            !(node.tags || []).includes(tag) ? (
              <button
                key={tag}
                onClick={() => useGraphStore.getState().addTag(nodeId, tag)}
                className="text-[10px] bg-surface-3 hover:bg-surface-4 text-gray-400 px-1.5 py-0.5 rounded transition-colors"
              >
                + {tag}
              </button>
            ) : null
          ))}
        </div>
      </section>
    </>
  )
}
