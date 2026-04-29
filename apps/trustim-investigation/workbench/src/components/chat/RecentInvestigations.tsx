import { useSessionStore } from '../../store/session'
import { sessionsApi } from '../../api'

/** Shows recent past investigations below the example prompts */
export function RecentInvestigations() {
  const sessionList = useSessionStore((s) => s.sessionList)

  if (sessionList.length === 0) return null

  return (
    <div className="mt-6 w-full max-w-[400px]">
      <p className="text-[11px] text-gray-500 uppercase tracking-wider mb-2 text-center">Recent Investigations</p>
      <div className="space-y-1">
        {sessionList.slice(0, 4).map((s) => (
          <div key={s.id} className="flex items-center gap-1 group">
            <button
              onClick={() => {
                window.dispatchEvent(new CustomEvent('openInvestigationTab', { detail: { sessionId: s.id, name: s.name } }))
              }}
              className="flex-1 text-left bg-white/[0.02] hover:bg-white/[0.05] rounded-lg px-3 py-2 transition-colors"
            >
              <div className="text-[12px] text-gray-300 truncate">{s.name}</div>
              <div className="text-[10px] text-gray-500">
                {s.node_count} nodes | {new Date(s.updated_at).toLocaleDateString()}
              </div>
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation()
                sessionsApi.delete(s.id).then(() => {
                  const store = useSessionStore.getState()
                  store.setSessionList(store.sessionList.filter(x => x.id !== s.id))
                  try { localStorage.removeItem(`investigation-backup-${s.id}`) } catch {}
                  if (store.currentSession?.id === s.id) {
                    store.closeSession()
                  }
                })
              }}
              className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 p-1 transition-opacity"
              title="Delete"
            >
              {'\u2715'}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
