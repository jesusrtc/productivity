import { useState, useRef, useMemo, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { setupApi } from '../../api'
import { useSessionStore } from '../../store/session'
import { useGraphStore } from '../../store/graph'
import { ExportDialog } from '../export/ExportDialog'
import { createDemoSession } from '../../utils/demo-session'
import type { ViewMode, Session } from '../../types'
import { confidenceColor } from '../../types'

const STATIC_TABS = [
  { id: 'home', label: 'Home' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'automations', label: 'Automations' },
  { id: 'playbooks', label: 'Playbooks' },
  { id: 'settings', label: 'Settings' },
] as const

export interface OpenTab {
  sessionId: string
  name: string
}

interface SessionBarProps {
  currentPage: string
  onPageChange: (page: string) => void
  openTabs: OpenTab[]
  onCloseTab: (sessionId: string) => void
  onRefreshTab?: (sessionId: string) => void
  onShowSkills: () => void
  onShowStats?: () => void
  onShowSessions?: () => void
}

export function SessionBar({ currentPage, onPageChange, openTabs, onCloseTab, onRefreshTab, onShowSkills, onShowStats, onShowSessions }: SessionBarProps) {
  const currentSession = useSessionStore((s) => s.currentSession)
  const closeSession = useSessionStore((s) => s.closeSession)
  const loadSession = useSessionStore((s) => s.loadSession)
  const sessionList = useSessionStore((s) => s.sessionList)
  const isConnected = useSessionStore((s) => s.isConnected)
  const processingInfo = useSessionStore((s) => s.processingInfo)
  const readOnly = useSessionStore((s) => s.readOnly)
  const viewMode = useGraphStore((s) => s.viewMode)
  const setViewMode = useGraphStore((s) => s.setViewMode)
  const nodes = useGraphStore((s) => s.nodes)
  const nodeCount = Object.keys(nodes).length

  // Confidence distribution for stats
  const confStats = useMemo(() => {
    let high = 0, medium = 0, low = 0
    for (const n of Object.values(nodes)) {
      if (n.confidence > 0.6) high++
      else if (n.confidence > 0.2) medium++
      else low++
    }
    return { high, medium, low }
  }, [nodes])
  const [showExport, setShowExport] = useState(false)
  const [showSaved, setShowSaved] = useState(false)
  const importRef = useRef<HTMLInputElement>(null)

  // Listen for auto-save events
  useEffect(() => {
    const handler = () => {
      setShowSaved(true)
      setTimeout(() => setShowSaved(false), 1500)
    }
    window.addEventListener('sessionSaved', handler)
    return () => window.removeEventListener('sessionSaved', handler)
  }, [])


  /** R56: Import a previously exported investigation for review */
  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      try {
        const data = JSON.parse(reader.result as string)
        // Support both raw session format and wrapped export format
        const session: Session = data.session || data
        if (!session.id || !session.nodes) {
          alert('Invalid investigation file')
          return
        }
        loadSession(session, true) // read-only mode
      } catch {
        alert('Failed to parse investigation file')
      }
    }
    reader.readAsText(file)
    // Reset input so the same file can be re-imported
    e.target.value = ''
  }

  // Drag-and-drop import handler
  return (
    <>
      <div className="h-11 bg-surface-1 border-b border-white/[0.06] flex items-center px-4 flex-shrink-0 relative z-[60]" role="toolbar" aria-label="Navigation">
        {/* LEFT: Static tabs + dynamic investigation tabs */}
        <nav className="flex items-center gap-0.5 overflow-x-auto min-w-0">
          {STATIC_TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => onPageChange(tab.id)}
              className={`px-3 py-1.5 text-[12px] rounded-md transition-colors flex-shrink-0 ${
                currentPage === tab.id
                  ? 'bg-accent-blue/15 text-accent-blue font-medium'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-white/[0.04]'
              }`}
            >
              {tab.label}
            </button>
          ))}
          {/* Dynamic investigation tabs */}
          {openTabs.length > 0 && <div className="w-px h-5 bg-white/[0.08] mx-1 flex-shrink-0" />}
          {openTabs.map(tab => (
            <InvestigationTab
              key={tab.sessionId}
              tab={tab}
              isActive={currentPage === `inv:${tab.sessionId}`}
              onClick={() => onPageChange(`inv:${tab.sessionId}`)}
              onClose={() => onCloseTab(tab.sessionId)}
              onRefresh={onRefreshTab ? () => onRefreshTab(tab.sessionId) : undefined}
              showSaved={showSaved}
              isConnected={isConnected}
              nodeCount={currentPage === `inv:${tab.sessionId}` ? nodeCount : undefined}
              processingInfo={currentPage === `inv:${tab.sessionId}` ? processingInfo : null}
            />
          ))}
        </nav>

        {/* RIGHT: Utility buttons */}
        <div className="flex items-center gap-0.5 ml-auto">
          {/* Investigation-specific utilities */}
          {currentPage.startsWith('inv:') && (
            <>
              {onRefreshTab && (
                <button
                  onClick={() => onRefreshTab(currentPage.replace('inv:', ''))}
                  className="text-[11px] text-gray-400 hover:text-accent-blue px-2 py-1 rounded hover:bg-surface-3 transition-colors"
                  title="Reload investigation from server"
                >
                  Refresh
                </button>
              )}
              <button
                onClick={() => window.dispatchEvent(new Event('showChecklist'))}
                className="text-[11px] text-gray-400 hover:text-gray-200 px-2 py-1 rounded hover:bg-surface-3 transition-colors relative"
                title="Investigation checklist (⌘⇧I)"
              >
                Checklist
                {nodeCount >= 3 && (() => {
                  const nodeTexts = Object.values(useGraphStore.getState().nodes).map(n => [n.label, n.query, ...(n.tags || [])].join(' ').toLowerCase())
                  const dims = [['email','split_part'],['ip','requestheader'],['canvashash','webgl'],['challenge','securitychallenge'],['restriction','dim_member'],['wow','t7d'],['dihe','fact_experience'],['sev','sev-']]
                  const unchecked = dims.filter(kws => !nodeTexts.some(t => kws.some(k => t.includes(k)))).length
                  if (unchecked > 0 && unchecked < 8) return (
                    <span className="absolute -top-1 -right-1 w-3.5 h-3.5 bg-accent-blue rounded-full text-[8px] text-white flex items-center justify-center">{unchecked}</span>
                  )
                  return null
                })()}
              </button>
              {onShowStats && (
                <button onClick={onShowStats} className="text-[11px] text-gray-400 hover:text-gray-200 px-2 py-1 rounded hover:bg-surface-3 transition-colors">Stats</button>
              )}
              <button
                onClick={() => window.dispatchEvent(new Event('togglePlaybookDrawer'))}
                className="text-[11px] text-gray-400 hover:text-gray-200 px-2 py-1 rounded hover:bg-surface-3 transition-colors"
                title="Toggle playbook DAG view"
              >Playbook</button>
            </>
          )}
          {/* Always-visible utilities */}
          {currentPage.startsWith('inv:') && <div className="w-px h-4 bg-white/[0.08] mx-1" />}
          {onShowSessions && (
            <button onClick={onShowSessions} className="text-[11px] text-gray-400 hover:text-gray-200 px-2 py-1 rounded hover:bg-surface-3 transition-colors" title="Browse investigations (⌘⇧L)">Sessions</button>
          )}
          <button onClick={() => setShowExport(true)} className="text-[11px] text-gray-400 hover:text-gray-200 px-2 py-1 rounded hover:bg-surface-3 transition-colors">Import / Export</button>
          <input ref={importRef} type="file" accept=".json" onChange={handleImport} className="hidden" />
          <MoreActionsMenu
            onDemo={() => {
              const demo = createDemoSession()
              loadSession(demo)
              // Dispatch event so App.tsx opens it as a tab
              window.dispatchEvent(new CustomEvent('openInvestigationTab', { detail: { sessionId: demo.id, name: demo.name } }))
            }}
          />
        </div>
      </div>

      {showExport && <ExportDialog onClose={() => setShowExport(false)} />}
    </>
  )
}

/** Live session timer with idle detection — pauses after 5min inactivity */
function SessionTimer({ startTime }: { startTime: string }) {
  const [display, setDisplay] = useState('')
  const [isIdle, setIsIdle] = useState(false)
  const activeTimeRef = useRef(0)
  const lastActivityRef = useRef(Date.now())

  useEffect(() => {
    // Track user activity
    const onActivity = () => { lastActivityRef.current = Date.now(); setIsIdle(false) }
    window.addEventListener('mousemove', onActivity, { passive: true })
    window.addEventListener('keydown', onActivity, { passive: true })

    let prevTick = Date.now()

    const interval = setInterval(() => {
      const now = Date.now()
      const idleMs = now - lastActivityRef.current
      const idle = idleMs > 300000 // 5 minutes

      if (!idle) {
        activeTimeRef.current += now - prevTick
      }
      setIsIdle(idle)
      prevTick = now

      const activeS = Math.floor(activeTimeRef.current / 1000)
      const fmt = (s: number) => {
        const h = Math.floor(s / 3600)
        const m = Math.floor((s % 3600) / 60)
        return h > 0 ? `${h}h${m}m` : m > 0 ? `${m}m` : `${s}s`
      }
      setDisplay(idle ? `${fmt(activeS)} active (idle)` : fmt(activeS))
    }, 1000)

    return () => {
      clearInterval(interval)
      window.removeEventListener('mousemove', onActivity)
      window.removeEventListener('keydown', onActivity)
    }
  }, [startTime])

  return (
    <span className={`text-[10px] tabular-nums ${isIdle ? 'text-yellow-500' : 'text-gray-500'}`} title="Active investigation time">
      {display}
    </span>
  )
}

/** Dropdown menu for less-used actions */
function MoreActionsMenu({ onDemo }: {
  onDemo: () => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as HTMLElement)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="text-xs text-gray-400 hover:text-gray-200 px-2 py-1 rounded hover:bg-surface-3 transition-colors"
      >
        More
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 bg-surface-2 border border-surface-4 rounded-lg shadow-2xl py-1 z-50 min-w-[160px] animate-[fadeIn_0.1s_ease-out]" onMouseDown={(e) => e.stopPropagation()}>
          {[
            { label: 'Load demo investigation', action: onDemo, enabled: true },
            { label: 'IOC database (WIP)', action: () => window.dispatchEvent(new Event('showIocBrowser')), enabled: false },
          ].map(item => (
            <button
              key={item.label}
              onClick={() => { if (item.enabled) { item.action(); setOpen(false) } }}
              className={`w-full text-left px-3 py-1.5 text-xs transition-colors ${
                item.enabled
                  ? 'text-gray-300 hover:bg-surface-3 cursor-pointer'
                  : 'text-gray-600 cursor-default'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/** Inline editable session name — toggles between display and input to avoid React contentEditable issues */
function InlineSessionName({ name }: { name: string }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(name)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [editing])

  // Sync draft when name changes externally (e.g., auto-rename on first message)
  useEffect(() => { if (!editing) setDraft(name) }, [name, editing])

  const commit = () => {
    setEditing(false)
    const trimmed = draft.trim()
    if (trimmed && trimmed !== name) {
      useSessionStore.getState().renameSession(trimmed)
    } else {
      setDraft(name)
    }
  }

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={draft}
        onChange={e => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={e => {
          if (e.key === 'Enter') commit()
          if (e.key === 'Escape') { setDraft(name); setEditing(false) }
        }}
        className="text-sm font-medium text-gray-200 bg-surface-2 border border-accent-blue/40 rounded px-1.5 py-0.5 max-w-[200px] focus:outline-none focus:ring-1 focus:ring-accent-blue/40"
      />
    )
  }

  return (
    <span
      className="text-sm font-medium text-gray-200 truncate max-w-[200px] cursor-text hover:text-accent-blue transition-colors rounded px-1 -mx-1"
      title="Click to rename"
      onClick={() => setEditing(true)}
    >
      {name}
    </span>
  )
}

/** Editable investigation tab with inline status info */
function InvestigationTab({ tab, isActive, onClick, onClose, onRefresh, showSaved, isConnected, nodeCount, processingInfo }: {
  tab: OpenTab
  isActive: boolean
  onClick: () => void
  onClose: () => void
  onRefresh?: () => void
  showSaved: boolean
  isConnected: boolean
  nodeCount?: number
  processingInfo: { active: boolean; operation: string } | null
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(tab.name)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { if (!editing) setDraft(tab.name) }, [tab.name, editing])
  useEffect(() => { if (editing && inputRef.current) { inputRef.current.focus(); inputRef.current.select() } }, [editing])

  const commit = () => {
    setEditing(false)
    const trimmed = draft.trim()
    if (trimmed && trimmed !== tab.name) {
      useSessionStore.getState().renameSession(trimmed)
      // Update the tab name in parent via event
      window.dispatchEvent(new CustomEvent('renameInvestigationTab', { detail: { sessionId: tab.sessionId, name: trimmed } }))
    } else {
      setDraft(tab.name)
    }
  }

  return (
    <div
      className={`flex items-center gap-1.5 pl-2.5 pr-1 py-1.5 rounded-md transition-colors flex-shrink-0 cursor-pointer ${
        isActive
          ? 'bg-accent-blue/15 text-accent-blue'
          : 'text-gray-400 hover:text-gray-200 hover:bg-white/[0.04]'
      }`}
      onClick={onClick}
    >
      {/* Status dot (only for active tab) */}
      {isActive && (
        <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 transition-colors ${
          showSaved ? 'bg-accent-cyan' : processingInfo?.active ? 'bg-accent-cyan animate-pulse' : isConnected ? 'bg-green-400' : 'bg-red-400'
        }`} />
      )}
      {/* Editable name */}
      {editing ? (
        <input
          ref={inputRef}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') { setDraft(tab.name); setEditing(false) } }}
          onClick={e => e.stopPropagation()}
          className="text-[12px] bg-surface-2 border border-accent-blue/40 rounded px-1 py-0 max-w-[160px] focus:outline-none text-gray-200"
        />
      ) : (
        <span
          className="text-[12px] truncate max-w-[160px]"
          onDoubleClick={(e) => { e.stopPropagation(); setEditing(true) }}
          title="Double-click to rename"
        >
          {tab.name}
        </span>
      )}
      {/* Node count for active tab */}
      {isActive && nodeCount !== undefined && nodeCount > 0 && (
        <span className="text-[9px] text-gray-500 tabular-nums flex-shrink-0">{nodeCount}</span>
      )}
      {/* Refresh + Close */}
      <div className="flex items-center gap-0.5 ml-1">
        {onRefresh && (
          <button
            onClick={(e) => { e.stopPropagation(); onRefresh() }}
            className="text-[11px] text-gray-500 hover:text-accent-blue hover:bg-surface-3 w-5 h-5 flex items-center justify-center rounded transition-colors flex-shrink-0"
            title="Reload from server"
          >
            {'\u21BB'}
          </button>
        )}
        <button
          onClick={(e) => { e.stopPropagation(); onClose() }}
          className="text-[11px] text-gray-500 hover:text-red-400 hover:bg-surface-3 w-5 h-5 flex items-center justify-center rounded transition-colors flex-shrink-0"
          title="Close tab"
        >
          {'\u2715'}
        </button>
      </div>
    </div>
  )
}

/** Compact dropdown for auto-investigate config (depth limit, max branches, max turns) */
const AGENT_DEFAULTS = { maxDepth: 5, maxBranches: 3, maxTurns: 25 }

function AgentConfigDropdown() {
  const [open, setOpen] = useState(false)
  const maxDepth = useGraphStore((s) => s.maxAutoDepth)
  const maxBranches = useGraphStore((s) => s.maxConcurrentBranches)
  const setMaxDepth = useGraphStore((s) => s.setMaxAutoDepth)
  const setMaxBranches = useGraphStore((s) => s.setMaxConcurrentBranches)
  const [maxTurns, setMaxTurns] = useState(AGENT_DEFAULTS.maxTurns)
  const ref = useRef<HTMLDivElement>(null)

  // Sync maxTurns from server on mount
  useEffect(() => {
    setupApi.bridgeConfig().then(d => {
      if (d.maxTurns) setMaxTurns(d.maxTurns)
    }).catch(() => {})
  }, [])

  const updateMaxTurns = (n: number) => {
    const clamped = Math.max(1, Math.min(50, n))
    setMaxTurns(clamped)
    setupApi.setBridgeConfig(clamped).catch(() => {})
  }

  // Position the portal dropdown below the trigger button
  const triggerRef = useRef<HTMLButtonElement>(null)
  const portalRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ top: 0, right: 0 })
  useEffect(() => {
    if (open && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect()
      setPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right })
    }
  }, [open])

  // Close on click outside — must check both the trigger ref AND the portal ref
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      if (ref.current?.contains(target)) return // Click on trigger
      if (portalRef.current?.contains(target)) return // Click inside portal dropdown
      setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div ref={ref} className="relative">
      <button
        ref={triggerRef}
        onClick={() => setOpen(!open)}
        className="text-xs text-gray-400 hover:text-gray-200 px-2 py-1 rounded hover:bg-surface-3 transition-colors"
        title="Agent configuration"
      >
        Agent
      </button>
      {open && createPortal(
        <div
          ref={portalRef}
          className="fixed bg-surface-2 border border-surface-4 rounded-lg shadow-2xl py-3 px-4 z-[200] min-w-[220px] animate-[fadeIn_0.1s_ease-out]"
          style={{ top: pos.top, right: pos.right }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between mb-3">
            <p className="text-[10px] text-gray-500 uppercase tracking-wider">Auto-Investigate</p>
            {(maxDepth !== AGENT_DEFAULTS.maxDepth || maxBranches !== AGENT_DEFAULTS.maxBranches || maxTurns !== AGENT_DEFAULTS.maxTurns) && (
              <button
                onClick={() => {
                  setMaxDepth(AGENT_DEFAULTS.maxDepth)
                  setMaxBranches(AGENT_DEFAULTS.maxBranches)
                  updateMaxTurns(AGENT_DEFAULTS.maxTurns)
                }}
                className="text-[10px] text-accent-blue hover:text-blue-400 transition-colors"
              >
                Reset defaults
              </button>
            )}
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-[12px] text-gray-400">Max depth</span>
                <span className="text-[10px] text-gray-600 ml-1">(rec: {AGENT_DEFAULTS.maxDepth})</span>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => setMaxDepth(maxDepth - 1)} className="text-[14px] text-gray-400 hover:text-gray-100 w-7 h-7 flex items-center justify-center rounded-md bg-surface-3 hover:bg-surface-4 active:bg-accent-blue/20 transition-colors select-none">-</button>
                <span className="text-[13px] text-gray-200 tabular-nums w-6 text-center font-medium">{maxDepth}</span>
                <button onClick={() => setMaxDepth(maxDepth + 1)} className="text-[14px] text-gray-400 hover:text-gray-100 w-7 h-7 flex items-center justify-center rounded-md bg-surface-3 hover:bg-surface-4 active:bg-accent-blue/20 transition-colors select-none">+</button>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <span className="text-[12px] text-gray-400">Max branches</span>
                <span className="text-[10px] text-gray-600 ml-1">(rec: {AGENT_DEFAULTS.maxBranches})</span>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => setMaxBranches(maxBranches - 1)} className="text-[14px] text-gray-400 hover:text-gray-100 w-7 h-7 flex items-center justify-center rounded-md bg-surface-3 hover:bg-surface-4 active:bg-accent-blue/20 transition-colors select-none">-</button>
                <span className="text-[13px] text-gray-200 tabular-nums w-6 text-center font-medium">{maxBranches}</span>
                <button onClick={() => setMaxBranches(maxBranches + 1)} className="text-[14px] text-gray-400 hover:text-gray-100 w-7 h-7 flex items-center justify-center rounded-md bg-surface-3 hover:bg-surface-4 active:bg-accent-blue/20 transition-colors select-none">+</button>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <span className="text-[12px] text-gray-400">Max turns</span>
                <span className="text-[10px] text-gray-600 ml-1">(rec: {AGENT_DEFAULTS.maxTurns})</span>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => updateMaxTurns(maxTurns - 1)} className="text-[14px] text-gray-400 hover:text-gray-100 w-7 h-7 flex items-center justify-center rounded-md bg-surface-3 hover:bg-surface-4 active:bg-accent-blue/20 transition-colors select-none">-</button>
                <span className="text-[13px] text-gray-200 tabular-nums w-6 text-center font-medium">{maxTurns}</span>
                <button onClick={() => updateMaxTurns(maxTurns + 1)} className="text-[14px] text-gray-400 hover:text-gray-100 w-7 h-7 flex items-center justify-center rounded-md bg-surface-3 hover:bg-surface-4 active:bg-accent-blue/20 transition-colors select-none">+</button>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  )
}

/** Standalone agent config for settings page */
export function AgentConfigSection() {
  const maxDepth = useGraphStore((s) => s.maxAutoDepth)
  const maxBranches = useGraphStore((s) => s.maxConcurrentBranches)
  const setMaxDepth = useGraphStore((s) => s.setMaxAutoDepth)
  const setMaxBranches = useGraphStore((s) => s.setMaxConcurrentBranches)
  const [maxTurns, setMaxTurns] = useState(AGENT_DEFAULTS.maxTurns)

  useEffect(() => {
    setupApi.bridgeConfig().then(d => { if (d.maxTurns) setMaxTurns(d.maxTurns) }).catch(() => {})
  }, [])

  const updateMaxTurns = (n: number) => {
    const clamped = Math.max(1, Math.min(50, n))
    setMaxTurns(clamped)
    setupApi.setBridgeConfig(clamped).catch(() => {})
  }

  const rows = [
    { label: 'Max depth', value: maxDepth, set: (n: number) => setMaxDepth(n), rec: AGENT_DEFAULTS.maxDepth },
    { label: 'Max branches', value: maxBranches, set: (n: number) => setMaxBranches(n), rec: AGENT_DEFAULTS.maxBranches },
    { label: 'Max turns', value: maxTurns, set: updateMaxTurns, rec: AGENT_DEFAULTS.maxTurns },
  ]

  return (
    <div className="space-y-3">
      {rows.map(r => (
        <div key={r.label} className="flex items-center justify-between">
          <div>
            <span className="text-[12px] text-gray-400">{r.label}</span>
            <span className="text-[10px] text-gray-600 ml-1">(default: {r.rec})</span>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => r.set(r.value - 1)} className="text-[14px] text-gray-400 hover:text-gray-100 w-7 h-7 flex items-center justify-center rounded-md bg-surface-3 hover:bg-surface-4 transition-colors select-none">-</button>
            <span className="text-[13px] text-gray-200 tabular-nums w-6 text-center font-medium">{r.value}</span>
            <button onClick={() => r.set(r.value + 1)} className="text-[14px] text-gray-400 hover:text-gray-100 w-7 h-7 flex items-center justify-center rounded-md bg-surface-3 hover:bg-surface-4 transition-colors select-none">+</button>
          </div>
        </div>
      ))}
      {(maxDepth !== AGENT_DEFAULTS.maxDepth || maxBranches !== AGENT_DEFAULTS.maxBranches || maxTurns !== AGENT_DEFAULTS.maxTurns) && (
        <button
          onClick={() => { setMaxDepth(AGENT_DEFAULTS.maxDepth); setMaxBranches(AGENT_DEFAULTS.maxBranches); updateMaxTurns(AGENT_DEFAULTS.maxTurns) }}
          className="text-[11px] text-accent-blue hover:text-blue-400 transition-colors"
        >
          Reset to defaults
        </button>
      )}
    </div>
  )
}
