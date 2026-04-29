import { useEffect, useRef } from 'react'
import { sessionsApi } from '../api'
import { useSessionStore } from '../store/session'
import { useGraphStore } from '../store/graph'
import { useToastStore } from '../store/toast'

let lastListRefresh = 0

/** Auto-save session on every state change (R35), debounced to 2s.
 *  Uses Zustand subscriptions for atomic reads — prevents saving intermediate
 *  state during rapid graph mutations (Bug #1). */
export function useAutoSave() {
  const readOnly = useSessionStore((s) => s.readOnly)
  const timerRef = useRef<ReturnType<typeof setTimeout>>()
  const saveVersionRef = useRef(0)

  useEffect(() => {
    if (readOnly) return

    // Subscribe to both stores — any change triggers a debounced save
    const unsubSession = useSessionStore.subscribe(() => scheduleSave())
    const unsubGraph = useGraphStore.subscribe(() => scheduleSave())

    function scheduleSave() {
      if (timerRef.current) clearTimeout(timerRef.current)
      const version = ++saveVersionRef.current
      timerRef.current = setTimeout(() => {
        // Check version to skip stale saves — only the latest scheduled save runs
        if (version !== saveVersionRef.current) return
        const data = useSessionStore.getState().getSessionData()
        if (!data) return
        // Don't persist empty sessions — wait until there's actual content
        const hasContent = Object.keys(data.nodes || {}).length > 0
          || (data.messages && data.messages.length > 0)
        if (!hasContent) return
        const json = JSON.stringify(data)
        // Warn if session exceeds 5MB
        if (json.length > 5 * 1024 * 1024) {
          useToastStore.getState().addToast(
            `Session size: ${(json.length / 1024 / 1024).toFixed(1)}MB — consider exporting and starting fresh`,
            'warning', 8000
          )
        }
        // Save to server
        sessionsApi.save(data.id, data)
          .then(() => {
            window.dispatchEvent(new Event('sessionSaved'))
            // Refresh session list at most every 10s to avoid request spam
            const now = Date.now()
            if (now - lastListRefresh > 10000) {
              lastListRefresh = now
              sessionsApi.list()
                .then(list => useSessionStore.getState().setSessionList(list))
                .catch(() => {})
            }
          })
          .catch(() => {})

        // Backup to localStorage (survives server restarts)
        try {
          localStorage.setItem(`investigation-backup-${data.id}`, json)
        } catch {
          // localStorage full — ignore
        }
      }, 2000)
    }

    return () => {
      unsubSession()
      unsubGraph()
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [readOnly])
}
