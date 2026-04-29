import { useState, useCallback, useEffect, useRef, lazy, Suspense } from 'react'
import { sessionsApi } from './api'
import { useSessionStore } from './store/session'
import { ChatPanel } from './components/chat/ChatPanel'
import { GraphPanel } from './components/graph/GraphPanel'
import { ErrorBoundary } from './components/ErrorBoundary'
import { NodeDetailDrawer } from './components/graph/NodeDetailDrawer'
import { SessionBar, AgentConfigSection } from './components/layout/SessionBar'
import { ToastContainer } from './components/layout/ToastContainer'
import { TraceLogPanel } from './components/trace/TraceLogPanel'
import { TimelineView } from './components/graph/TimelineView'
import { SetupScreen } from './components/setup/SetupScreen'

// Lazy-load overlay panels (only loaded when opened)
const KeyboardHelp = lazy(() => import('./components/layout/KeyboardHelp').then(m => ({ default: m.KeyboardHelp })))
const InvestigationStats = lazy(() => import('./components/layout/InvestigationStats').then(m => ({ default: m.InvestigationStats })))
const SessionListPanel = lazy(() => import('./components/layout/SessionListPanel').then(m => ({ default: m.SessionListPanel })))
const SessionComparePanel = lazy(() => import('./components/layout/SessionComparePanel').then(m => ({ default: m.SessionComparePanel })))
const QuickOpen = lazy(() => import('./components/layout/QuickOpen').then(m => ({ default: m.QuickOpen })))
const GlobalSearch = lazy(() => import('./components/layout/GlobalSearch').then(m => ({ default: m.GlobalSearch })))
const InvestigationGuide = lazy(() => import('./components/layout/InvestigationGuide').then(m => ({ default: m.InvestigationGuide })))
const TemplateGallery = lazy(() => import('./components/layout/TemplateGallery').then(m => ({ default: m.TemplateGallery })))
const InvestigationChecklist = lazy(() => import('./components/layout/InvestigationChecklist').then(m => ({ default: m.InvestigationChecklist })))
const IocBrowser = lazy(() => import('./components/layout/IocBrowser').then(m => ({ default: m.IocBrowser })))
const SkillBrowser = lazy(() => import('./components/skills/SkillBrowser').then(m => ({ default: m.SkillBrowser })))
const AlertQueue = lazy(() => import('./components/alerts/AlertQueue').then(m => ({ default: m.AlertQueue })))
import { useGraphStore } from './store/graph'
import { useWebSocket } from './hooks/useWebSocket'
import { useAutoSave } from './hooks/useAutoSave'
import { useAutoInvestigate } from './hooks/useAutoInvestigate'
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts'
import { useTabManagement } from './hooks/useTabManagement'
import { useAdapterSetup, useSessionPolling } from './hooks/useBackgroundPolling'

type OverlayId = 'skills' | 'mcp' | 'help' | 'stats' | 'sessions' | 'compare' | 'quickOpen' | 'globalSearch' | 'guide' | 'templates' | 'checklist' | 'iocBrowser' | 'alerts' | null

import { HomePage } from './components/home/HomePage'
import { AutomationLibrary } from './components/automations/AutomationLibrary'
import { PlaybookLibrary } from './components/playbooks/PlaybookLibrary'
import { PlaybookEditor } from './components/playbooks/PlaybookEditor'
import { usePlaybookStore } from './store/playbook'
import { PlaybookDrawer } from './components/playbooks/PlaybookDrawer'
import { RelatedAlertsSidebar } from './components/alerts/RelatedAlertsSidebar'

function PlaybookPage() {
  const [editing, setEditing] = useState<any>(undefined)
  return (
    <>
      <PlaybookLibrary onOpenEditor={(pb) => setEditing(pb ?? null)} />
      {editing !== undefined && <PlaybookEditor playbook={editing || undefined} onClose={() => { setEditing(undefined); usePlaybookStore.getState().fetchPlaybooks() }} />}
    </>
  )
}

export function App() {
  // Setup verification
  const [setupComplete, setSetupComplete] = useState(() => {
    return sessionStorage.getItem('setupComplete') === 'true'
  })
  const handleSetupReady = useCallback(() => {
    sessionStorage.setItem('setupComplete', 'true')
    setSetupComplete(true)
  }, [])

  const viewMode = useGraphStore((s) => s.viewMode)
  const selectedNodeId = useGraphStore((s) => s.selectedNodeId)
  const isConnected = useSessionStore((s) => s.isConnected)
  const currentSession = useSessionStore((s) => s.currentSession)
  const [splitRatio, setSplitRatio] = useState(0.38)

  // Tab management hook
  const {
    currentPage, setCurrentPage, openTabs,
    switchPage, openInvestigation, closeTab, startNewInvestigation,
  } = useTabManagement()

  // Single overlay state
  const [activeOverlay, setActiveOverlay] = useState<OverlayId>(null)
  const toggleOverlay = useCallback((id: OverlayId) => setActiveOverlay(prev => prev === id ? null : id), [])

  const showSkills = activeOverlay === 'skills'
  const showHelp = activeOverlay === 'help'
  const showStats = activeOverlay === 'stats'
  const showSessions = activeOverlay === 'sessions'
  const showCompare = activeOverlay === 'compare'
  const showQuickOpen = activeOverlay === 'quickOpen'
  const showGlobalSearch = activeOverlay === 'globalSearch'
  const showGuide = activeOverlay === 'guide'
  const showTemplates = activeOverlay === 'templates'
  const showChecklist = activeOverlay === 'checklist'
  const showIocBrowser = activeOverlay === 'iocBrowser'

  const containerRef = useRef<HTMLDivElement>(null)
  const isDragging = useRef(false)

  // WebSocket + adapter setup + polling
  const wsRef = useWebSocket()
  useAdapterSetup(wsRef)
  useSessionPolling()

  // Keyboard shortcuts
  const { syncOverlayRef } = useKeyboardShortcuts({ toggleOverlay, setActiveOverlay, switchPage })
  syncOverlayRef(activeOverlay)

  // Listen for overlay events from child components
  useEffect(() => {
    const helpHandler = () => setActiveOverlay('help')
    const guideHandler = () => setActiveOverlay('guide')
    const templatesHandler = () => setActiveOverlay('templates')
    const checklistHandler = () => setActiveOverlay('checklist')
    const iocHandler = () => setActiveOverlay('iocBrowser')
    window.addEventListener('showKeyboardHelp', helpHandler)
    window.addEventListener('showInvestigationGuide', guideHandler)
    window.addEventListener('showTemplateGallery', templatesHandler)
    window.addEventListener('showChecklist', checklistHandler)
    window.addEventListener('showIocBrowser', iocHandler)
    return () => {
      window.removeEventListener('showKeyboardHelp', helpHandler)
      window.removeEventListener('showInvestigationGuide', guideHandler)
      window.removeEventListener('showTemplateGallery', templatesHandler)
      window.removeEventListener('showChecklist', checklistHandler)
      window.removeEventListener('showIocBrowser', iocHandler)
    }
  }, [])

  // Handle "investigate value" events from table cell double-clicks
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { value: string; column: string }
      if (!detail?.value) return
      const prompt = `Investigate "${detail.value}"${detail.column ? ` (${detail.column})` : ''} — what can we find about this entity?`
      window.dispatchEvent(new CustomEvent('prefillChat', { detail: { text: prompt } }))
    }
    window.addEventListener('investigateValue', handler)
    return () => window.removeEventListener('investigateValue', handler)
  }, [])

  useEffect(() => { if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission() }, [])

  // Auto-save + auto-investigate
  useAutoSave()
  useAutoInvestigate()

  // Resize handle
  const onMouseDown = useCallback(() => { isDragging.current = true }, [])
  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging.current || !containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      setSplitRatio(Math.max(0.2, Math.min(0.7, (e.clientX - rect.left) / rect.width)))
    }
    const onMouseUp = () => { isDragging.current = false }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => { window.removeEventListener('mousemove', onMouseMove); window.removeEventListener('mouseup', onMouseUp) }
  }, [])

  // Sync selected node with URL hash
  useEffect(() => {
    if (selectedNodeId) {
      window.history.replaceState(null, '', `#node=${selectedNodeId}`)
    } else if (window.location.hash.startsWith('#node=')) {
      window.history.replaceState(null, '', window.location.pathname + window.location.search)
    }
  }, [selectedNodeId])

  // On mount, check for node hash and select it
  useEffect(() => {
    const hash = window.location.hash
    if (hash.startsWith('#node=')) {
      const nodeId = hash.slice(6)
      setTimeout(() => {
        const page = sessionStorage.getItem('currentPage') || 'home'
        if (page.startsWith('inv:') && useGraphStore.getState().nodes[nodeId]) {
          useGraphStore.getState().selectNode(nodeId)
        }
      }, 1000)
      window.history.replaceState(null, '', window.location.pathname + window.location.search)
    }
  }, [])

  if (!setupComplete) {
    return <SetupScreen onReady={handleSetupReady} />
  }

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {!isConnected && (
        <div className="bg-red-900/30 border-b border-red-900/40 px-4 py-1.5 flex items-center gap-2 text-[11px] text-red-300 flex-shrink-0">
          <div className="w-2 h-2 bg-red-400 rounded-full" />
          <span>Server disconnected — reconnecting automatically. Investigation data is preserved locally.</span>
        </div>
      )}
      <SevAlertBar />
      <SessionBar
        currentPage={currentPage}
        onPageChange={switchPage}
        openTabs={openTabs}
        onCloseTab={closeTab}
        onRefreshTab={async (sessionId) => {
          useSessionStore.getState().clearTabSnapshot(sessionId)
          try {
            const data = await sessionsApi.get(sessionId) as any
            if (data?.id) useSessionStore.getState().loadSession(data)
          } catch {}
        }}
        onShowSkills={() => toggleOverlay('skills')}
        onShowStats={() => toggleOverlay('stats')}
        onShowSessions={() => toggleOverlay('sessions')}
      />

      {/* Page: Home */}
      <div className={`flex-1 overflow-hidden ${currentPage === 'home' ? '' : 'hidden'}`}>
        <HomePage
          onOpenInvestigation={openInvestigation}
          onNewInvestigation={startNewInvestigation}
          onNavigateToAlerts={() => setCurrentPage('alerts')}
        />
      </div>

      {/* Page: Alerts */}
      <div className={`flex-1 overflow-hidden ${currentPage === 'alerts' ? '' : 'hidden'}`}>
        <Suspense fallback={null}>
          <AlertQueue onNavigateToInvestigation={(sessionId?: string, name?: string) => {
            if (sessionId) openInvestigation(sessionId, name)
            else setCurrentPage('home')
          }} />
        </Suspense>
      </div>

      {/* Page: Automations */}
      <div className={`flex-1 overflow-hidden ${currentPage === 'automations' ? '' : 'hidden'}`}>
        <AutomationLibrary />
      </div>

      {/* Page: Playbooks */}
      <div className={`flex-1 overflow-hidden ${currentPage === 'playbooks' ? '' : 'hidden'}`}>
        <PlaybookPage />
      </div>

      {/* Page: Settings */}
      <div className={`flex-1 overflow-hidden ${currentPage === 'settings' ? '' : 'hidden'}`}>
        <div className="h-full overflow-y-auto p-8 max-w-2xl mx-auto">
          <h2 className="text-lg font-medium text-gray-200 mb-6">Settings</h2>
          <div className="space-y-6">
            <div className="bg-surface-2/40 rounded-lg p-4 border border-white/[0.06]">
              <h3 className="text-[13px] font-medium text-gray-300 mb-3">Agent Configuration</h3>
              <AgentConfigSection />
            </div>
            <div className="bg-surface-2/40 rounded-lg p-4 border border-white/[0.06]">
              <h3 className="text-[13px] font-medium text-gray-300 mb-3">IRIS Sync</h3>
              <p className="text-[12px] text-gray-500">Plans: trust-incident-auto-alert, trust-incident-intake-email, trust-incident-intake, abuse-incidents-thirdeye</p>
              <p className="text-[12px] text-gray-500 mt-1">Interval: 5 minutes</p>
            </div>
          </div>
        </div>
      </div>

      {/* Page: Investigation */}
      <div ref={containerRef} className={`flex-1 flex overflow-hidden relative ${currentPage.startsWith('inv:') ? '' : 'hidden'}`} role="main">
      {!currentSession && currentPage.startsWith('inv:') ? (
        <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">Loading investigation...</div>
      ) : (
      <>
        <section
          aria-label="Investigation Chat"
          className="h-full overflow-hidden border-r border-surface-3 flex flex-col"
          style={{ width: `${splitRatio * 100}%` }}
        >
          <ErrorBoundary fallback={<div className="h-full flex items-center justify-center text-red-400 text-sm">Chat panel error — click Try Again</div>}>
            <div className="flex-1 overflow-hidden">
              <ChatPanel />
            </div>
          </ErrorBoundary>
        </section>

        <div
          role="separator"
          aria-label="Resize panels"
          className="w-2 cursor-col-resize bg-surface-3 hover:bg-accent-blue/50 transition-colors flex-shrink-0 relative group"
          onMouseDown={onMouseDown}
        >
          <div className="absolute inset-y-0 left-1/2 w-px bg-white/[0.06] group-hover:bg-accent-blue/60 transition-colors" />
        </div>

        <section aria-label="Decision Graph" className="h-full overflow-hidden flex-1 flex flex-col">
          <ErrorBoundary fallback={<div className="flex-1 flex items-center justify-center text-red-400 text-sm">Graph panel error — click Try Again</div>}>
            <div className="flex-1 overflow-hidden">
              {viewMode === 'log' ? <TraceLogPanel /> : viewMode === 'timeline' ? <TimelineView /> : <GraphPanel />}
            </div>
          </ErrorBoundary>
          {currentSession && <PlaybookDrawer sessionId={currentSession.id} />}
          {currentSession && <RelatedAlertsSidebar sessionId={currentSession.id} />}
        </section>

        {selectedNodeId && <NodeDetailDrawer nodeId={selectedNodeId} />}
        {showSkills && <Suspense fallback={null}><SkillBrowser onClose={() => setActiveOverlay(null)} /></Suspense>}
      </>
      )}
      </div>

      {/* Lazy-loaded overlay panels */}
      <Suspense fallback={null}>
      {showHelp && <KeyboardHelp onClose={() => setActiveOverlay(null)} />}
      {showStats && <InvestigationStats onClose={() => setActiveOverlay(null)} />}
      {showSessions && <SessionListPanel onClose={() => setActiveOverlay(null)} onCompare={() => setActiveOverlay('compare')} />}
      {showCompare && <SessionComparePanel onClose={() => setActiveOverlay(null)} />}
      {showQuickOpen && <QuickOpen onClose={() => setActiveOverlay(null)} />}
      {showGlobalSearch && <GlobalSearch onClose={() => setActiveOverlay(null)} />}
      {showGuide && <InvestigationGuide onClose={() => setActiveOverlay(null)} onSendPrompt={(prompt) => {
        setActiveOverlay(null)
        window.dispatchEvent(new CustomEvent('prefillChat', { detail: { text: prompt } }))
      }} />}
      {showTemplates && <TemplateGallery onClose={() => setActiveOverlay(null)} onUseTemplate={(prompt) => {
        setActiveOverlay(null)
        window.dispatchEvent(new CustomEvent('prefillChat', { detail: { text: prompt } }))
      }} />}
      {showChecklist && <InvestigationChecklist onClose={() => setActiveOverlay(null)} onRunStep={(prompt) => {
        setActiveOverlay(null)
        window.dispatchEvent(new CustomEvent('executeFromNode', {
          detail: { query: prompt, parentNodeId: Object.keys(useGraphStore.getState().nodes).pop() || '', label: 'Checklist step' }
        }))
      }} />}
      {showIocBrowser && <IocBrowser onClose={() => setActiveOverlay(null)} />}
      </Suspense>
      <ToastContainer />
    </div>
  )
}

function SevAlertBar() {
  const nodes = useGraphStore((s) => s.nodes)
  const sevNode = Object.values(nodes).find(n => (n.tags || []).some(t => t === 'SEV-1' || t === 'SEV-2'))
  if (!sevNode) return null
  const sev = (sevNode.tags || []).find(t => t.startsWith('SEV-'))
  return (
    <div className={`px-4 py-1.5 flex items-center gap-2 text-[11px] flex-shrink-0 ${sev === 'SEV-1' ? 'bg-red-900/40 border-b border-red-900/50 text-red-200' : 'bg-orange-900/30 border-b border-orange-900/40 text-orange-200'}`}>
      <span className="font-bold">{sev}</span>
      <span>{sevNode.label} — {sevNode.result_summary?.slice(0, 80) || 'Critical finding detected'}</span>
      <button
        onClick={() => useGraphStore.getState().selectNode(sevNode.node_id)}
        className="ml-auto text-[10px] underline opacity-70 hover:opacity-100"
      >
        View
      </button>
    </div>
  )
}
