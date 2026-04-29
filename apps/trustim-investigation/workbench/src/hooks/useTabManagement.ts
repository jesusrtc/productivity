import { useState, useCallback, useEffect } from 'react'
import { sessionsApi, investigationsApi } from '../api'
import { useSessionStore } from '../store/session'
import { useGraphStore } from '../store/graph'
import { useToastStore } from '../store/toast'
import type { OpenTab } from '../components/layout/SessionBar'

export function useTabManagement() {
  const [currentPage, setCurrentPage] = useState(() => {
    return sessionStorage.getItem('currentPage') || 'home'
  })
  const [openTabs, setOpenTabs] = useState<OpenTab[]>(() => {
    try { return JSON.parse(sessionStorage.getItem('openTabs') || '[]') } catch { return [] }
  })

  const setSessionList = useSessionStore((s) => s.setSessionList)
  const loadSession = useSessionStore((s) => s.loadSession)

  // Persist current page + open tabs across reloads
  useEffect(() => { sessionStorage.setItem('currentPage', currentPage) }, [currentPage])
  useEffect(() => { sessionStorage.setItem('openTabs', JSON.stringify(openTabs)) }, [openTabs])

  /** Snapshot the current investigation tab if we're on one */
  const snapshotCurrentIfNeeded = useCallback(() => {
    const prevPage = sessionStorage.getItem('currentPage') || 'home'
    if (!prevPage.startsWith('inv:')) return
    const tabSessionId = prevPage.replace('inv:', '')
    const store = useSessionStore.getState()
    if (store.currentSession?.id === tabSessionId) {
      store.flushSave()
      store.snapshotCurrentTab(tabSessionId)
    }
  }, [])

  /** Switch page with snapshot/restore for investigation tabs */
  const switchPage = useCallback((newPage: string) => {
    const prevPage = sessionStorage.getItem('currentPage') || 'home'
    if (newPage === prevPage) return
    if (prevPage.startsWith('inv:')) {
      snapshotCurrentIfNeeded()
    }
    // Sync sessionStorage immediately so rapid successive calls read the correct prev page
    sessionStorage.setItem('currentPage', newPage)
    setCurrentPage(newPage)
    if (newPage.startsWith('inv:')) {
      const targetId = newPage.replace('inv:', '')
      const store = useSessionStore.getState()
      if (!store.restoreTab(targetId)) {
        useGraphStore.getState().clearGraph()
        const tabName = openTabs.find(t => t.sessionId === targetId)?.name || 'Investigation'
        useSessionStore.setState({
          currentSession: {
            id: targetId, name: tabName, created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(), starting_input: '', starting_input_type: 'none' as const,
            nodes: {}, edges: [], messages: [], skills_used: [], tools_used: [], mcp_tools: [],
          },
          chatContext: null, readOnly: false,
        })
        sessionsApi.get(targetId)
          .then((data: any) => {
            if (sessionStorage.getItem('currentPage') === newPage && data?.id) {
              store.loadSession(data)
            }
          })
          .catch(() => {})
      }
    }
  }, [snapshotCurrentIfNeeded, openTabs])

  /** Open an investigation in a new tab (or focus existing) */
  const openInvestigation = useCallback(async (sessionId: string, name?: string) => {
    const pageId = `inv:${sessionId}`
    const prevPage = sessionStorage.getItem('currentPage') || 'home'
    if (prevPage.startsWith('inv:')) {
      snapshotCurrentIfNeeded()
    }
    const store = useSessionStore.getState()
    if (openTabs.some(t => t.sessionId === sessionId)) {
      if (!store.restoreTab(sessionId)) {
        try {
          const data = await sessionsApi.get(sessionId) as any
          if (data?.id) store.loadSession(data)
        } catch {}
      }
      sessionStorage.setItem('currentPage', pageId)
      setCurrentPage(pageId)
      return
    }
    const tabName = name || `Investigation ${sessionId.slice(0, 8)}`
    try {
      const data = await sessionsApi.get(sessionId) as any
      if (data?.id) {
        store.loadSession(data)
        setOpenTabs(prev => [...prev, { sessionId, name: data.name || tabName }])
      } else {
        setOpenTabs(prev => [...prev, { sessionId, name: tabName }])
      }
    } catch {
      setOpenTabs(prev => [...prev, { sessionId, name: tabName }])
    }
    sessionStorage.setItem('currentPage', pageId)
    setCurrentPage(pageId)
  }, [openTabs, snapshotCurrentIfNeeded])

  /** Close an investigation tab */
  const closeTab = useCallback((sessionId: string) => {
    const pageId = `inv:${sessionId}`
    useSessionStore.getState().clearTabSnapshot(sessionId)
    setOpenTabs(prev => prev.filter(t => t.sessionId !== sessionId))
    investigationsApi.stop(sessionId).catch(() => {})
    if (currentPage === pageId) {
      setCurrentPage('home')
      if (useSessionStore.getState().currentSession?.id === sessionId) {
        useSessionStore.getState().closeSession()
      }
    }
  }, [currentPage])

  /** Start a new blank investigation */
  const startNewInvestigation = useCallback(() => {
    const prevPage = sessionStorage.getItem('currentPage') || 'home'
    if (prevPage.startsWith('inv:')) {
      snapshotCurrentIfNeeded()
    }
    const session = useSessionStore.getState().newSession(
      `Investigation — ${new Date().toLocaleDateString()}`,
      ''
    )
    setOpenTabs(prev => [...prev, { sessionId: session.id, name: session.name }])
    const newPage = `inv:${session.id}`
    sessionStorage.setItem('currentPage', newPage)
    setCurrentPage(newPage)
  }, [snapshotCurrentIfNeeded])

  // Load session list on mount + handle deep links
  useEffect(() => {
    sessionsApi.list()
      .then((list) => {
        setSessionList(list)
        const params = new URLSearchParams(window.location.search)

        const sessionId = params.get('session')
        if (sessionId) {
          openInvestigation(sessionId)
          window.history.replaceState({}, '', window.location.pathname)
          return
        }

        const investigatePrompt = params.get('investigate')
        const alertId = params.get('alert') || params.get('incident')
        if (alertId || investigatePrompt) {
          startNewInvestigation()
          const prompt = alertId ? `Triage alert ${alertId}` : investigatePrompt!
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent('autoSendChat', { detail: { text: prompt } }))
          }, 800)
          window.history.replaceState({}, '', window.location.pathname)
          return
        }

        if (currentPage.startsWith('inv:')) {
          const sid = currentPage.replace('inv:', '')
          openInvestigation(sid)
        }
      })
      .catch(() => {
        const keys = Object.keys(localStorage).filter(k => k.startsWith('investigation-backup-'))
        if (keys.length > 0) {
          try {
            const latest = keys.sort().pop()!
            const data = JSON.parse(localStorage.getItem(latest) || '')
            if (data?.id && data?.nodes) {
              loadSession(data)
              useToastStore.getState().addToast('Recovered investigation from local backup', 'info', 5000)
            }
          } catch { /* ignore */ }
        }
      })
  }, [setSessionList, loadSession])

  // Listen for tab close/open/rename events from other components
  useEffect(() => {
    const handler = (e: Event) => {
      const { sessionId } = (e as CustomEvent).detail || {}
      if (sessionId) closeTab(sessionId)
    }
    window.addEventListener('closeInvestigationTab', handler)

    const openHandler = (e: Event) => {
      const { sessionId, name } = (e as CustomEvent).detail || {}
      if (sessionId) {
        setOpenTabs(prev => prev.some(t => t.sessionId === sessionId) ? prev : [...prev, { sessionId, name: name || `Investigation ${sessionId.slice(0, 8)}` }])
        setCurrentPage(`inv:${sessionId}`)
      }
    }
    window.addEventListener('openInvestigationTab', openHandler)

    const renameHandler = (e: Event) => {
      const { sessionId, name } = (e as CustomEvent).detail || {}
      if (sessionId && name) {
        setOpenTabs(prev => prev.map(t => t.sessionId === sessionId ? { ...t, name } : t))
      }
    }
    window.addEventListener('renameInvestigationTab', renameHandler)
    return () => {
      window.removeEventListener('closeInvestigationTab', handler)
      window.removeEventListener('openInvestigationTab', openHandler)
      window.removeEventListener('renameInvestigationTab', renameHandler)
    }
  }, [closeTab])

  return {
    currentPage,
    setCurrentPage,
    openTabs,
    setOpenTabs,
    switchPage,
    openInvestigation,
    closeTab,
    startNewInvestigation,
  }
}
