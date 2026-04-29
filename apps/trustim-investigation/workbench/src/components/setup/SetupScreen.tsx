import { useState, useEffect, useCallback, useRef } from 'react'
import { setupApi } from '../../api'

interface SetupCheck {
  id: string
  label: string
  status: 'ok' | 'warning' | 'error' | 'checking'
  message: string
  required: boolean
  fix?: string
}

interface SetupResult {
  ready: boolean
  checks: SetupCheck[]
  requiredPassing: number
  requiredTotal: number
}

interface Props {
  onReady: () => void
}

export function SetupScreen({ onReady }: Props) {
  const [result, setResult] = useState<SetupResult | null>(null)
  const [running, setRunning] = useState(false)
  const [phase, setPhase] = useState<'checking' | 'results'>('checking')
  const [animatedChecks, setAnimatedChecks] = useState<SetupCheck[]>([])
  const [dismissed, setDismissed] = useState(false)
  const hasRunOnce = useRef(false)

  const runningRef = useRef(false)

  const runChecks = useCallback(async () => {
    // Guard against StrictMode double-invocation
    if (runningRef.current) return
    runningRef.current = true

    setRunning(true)
    setPhase('checking')

    const placeholders: SetupCheck[] = [
      { id: 'claude', label: 'Claude CLI', status: 'checking', message: 'Checking...', required: true },
      { id: 'mcp', label: 'Captain MCP Tools', status: 'checking', message: 'Checking...', required: false },
      { id: 'trino', label: 'Trino (Holdem)', status: 'checking', message: 'Checking...', required: true },
      { id: 'davi', label: 'DAVI / Darwin', status: 'checking', message: 'Checking...', required: false },
      { id: 'iris', label: 'IRIS / InResponse', status: 'checking', message: 'Checking...', required: false },
      { id: 'skills', label: 'Investigation Skills', status: 'checking', message: 'Checking...', required: true },
    ]

    // Stagger appearance — use absolute set (not append) to avoid duplicates
    for (let i = 0; i < placeholders.length; i++) {
      await new Promise(r => setTimeout(r, 120))
      setAnimatedChecks(placeholders.slice(0, i + 1))
    }

    // Use /recheck (invalidates server cache) if user clicked Re-check, otherwise
    // use /check which returns cached results (prevents StrictMode double-fire)
    try {
      const isRecheck = hasRunOnce.current
      hasRunOnce.current = true
      const data: SetupResult = isRecheck
        ? await setupApi.recheck() as SetupResult
        : await setupApi.check() as SetupResult

      // Animate each check resolving to its real status
      for (let i = 0; i < data.checks.length; i++) {
        await new Promise(r => setTimeout(r, 200))
        setAnimatedChecks(prev =>
          prev.map(c => c.id === data.checks[i].id ? data.checks[i] : c)
        )
      }

      setResult(data)
      setPhase('results')
    } catch {
      setResult({ ready: false, checks: [], requiredPassing: 0, requiredTotal: 3 })
      setPhase('results')
    }
    setRunning(false)
    runningRef.current = false
  }, [])

  // Run on mount
  useEffect(() => { runChecks() }, [runChecks])

  // Auto-proceed if all required checks pass (skip the screen entirely for returning users)
  useEffect(() => {
    if (result?.ready && !dismissed) {
      const timer = setTimeout(() => onReady(), 1500)
      return () => clearTimeout(timer)
    }
  }, [result, dismissed, onReady])

  if (dismissed) return null

  const checks = animatedChecks
  const requiredOk = checks.filter(c => c.required && c.status === 'ok').length
  const requiredTotal = checks.filter(c => c.required).length
  const allRequiredOk = requiredTotal > 0 && requiredOk === requiredTotal
  const hasErrors = checks.some(c => c.required && c.status === 'error')

  return (
    <div className="fixed inset-0 z-[500] bg-surface-0 flex items-center justify-center">
      <div className="w-full max-w-lg px-8">
        {/* Header */}
        <div className="text-center mb-10">
          <div className="text-[40px] mb-3 opacity-60">{'\u{1F50D}'}</div>
          <h1 className="text-[22px] font-semibold text-gray-100 tracking-tight mb-2">
            Juniper
          </h1>
          <p className="text-[14px] text-gray-500 leading-relaxed">
            Verifying your environment before we begin.
          </p>
        </div>

        {/* Checklist */}
        <div className="space-y-1 mb-8">
          {checks.map((check, i) => (
            <div
              key={check.id}
              className="flex items-start gap-3 px-4 py-3 rounded-xl transition-all duration-300"
              style={{
                opacity: 1,
                transform: 'translateY(0)',
                animation: `fadeSlideIn 0.3s ease-out ${i * 0.08}s both`,
              }}
            >
              {/* Status icon */}
              <div className="w-5 h-5 flex items-center justify-center flex-shrink-0 mt-0.5">
                {check.status === 'checking' ? (
                  <div className="w-4 h-4 border-2 border-gray-600 border-t-accent-blue rounded-full animate-spin" />
                ) : check.status === 'ok' ? (
                  <div className="w-5 h-5 bg-green-500/20 rounded-full flex items-center justify-center">
                    <svg className="w-3 h-3 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                ) : check.status === 'warning' ? (
                  <div className="w-5 h-5 bg-yellow-500/20 rounded-full flex items-center justify-center">
                    <span className="text-yellow-400 text-[11px] font-bold">!</span>
                  </div>
                ) : (
                  <div className="w-5 h-5 bg-red-500/20 rounded-full flex items-center justify-center">
                    <svg className="w-3 h-3 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </div>
                )}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className={`text-[13px] font-medium ${
                    check.status === 'ok' ? 'text-gray-200' :
                    check.status === 'checking' ? 'text-gray-400' :
                    check.status === 'warning' ? 'text-yellow-300' :
                    'text-red-300'
                  }`}>
                    {check.label}
                  </span>
                  {!check.required && (
                    <span className="text-[9px] text-gray-600 uppercase tracking-wider">Optional</span>
                  )}
                </div>
                <p className={`text-[12px] mt-0.5 ${
                  check.status === 'error' ? 'text-red-400/80' :
                  check.status === 'warning' ? 'text-yellow-400/70' :
                  'text-gray-500'
                }`}>
                  {check.message}
                </p>
                {/* Actionable fix */}
                {check.fix && check.status !== 'ok' && check.status !== 'checking' && (
                  <div className="mt-1.5 flex items-center gap-2">
                    <code className="text-[11px] bg-surface-2 text-accent-blue px-2 py-0.5 rounded font-mono select-all">
                      {check.fix}
                    </code>
                    <button
                      onClick={() => navigator.clipboard.writeText(check.fix!)}
                      className="text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
                      title="Copy to clipboard"
                    >
                      Copy
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Progress summary */}
        {phase === 'results' && (
          <div className="text-center space-y-4">
            {allRequiredOk ? (
              <>
                <div className="flex items-center justify-center gap-2 text-green-400">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span className="text-[14px] font-medium">Ready to investigate</span>
                </div>
                <p className="text-[12px] text-gray-500">
                  {checks.filter(c => c.status === 'warning').length > 0
                    ? 'Some optional services are unavailable — core investigation features work fine.'
                    : 'All systems operational.'}
                </p>
                <button
                  onClick={onReady}
                  className="bg-accent-blue hover:bg-blue-600 text-white text-[13px] px-8 py-2.5 rounded-lg transition-colors"
                >
                  Get Started
                </button>
              </>
            ) : (
              <>
                <div className="flex items-center justify-center gap-2 text-red-400">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                  </svg>
                  <span className="text-[14px] font-medium">Setup required</span>
                </div>
                <p className="text-[12px] text-gray-500">
                  Fix the issues above, then re-check. Required items must pass before investigating.
                </p>
                <div className="flex items-center justify-center gap-3">
                  <button
                    onClick={runChecks}
                    disabled={running}
                    className="bg-accent-blue hover:bg-blue-600 disabled:bg-gray-700 text-white text-[13px] px-6 py-2.5 rounded-lg transition-colors"
                  >
                    {running ? 'Checking...' : 'Re-check'}
                  </button>
                  <button
                    onClick={() => { setDismissed(true); onReady() }}
                    className="text-[13px] text-gray-500 hover:text-gray-300 px-4 py-2.5 transition-colors"
                  >
                    Skip for now
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {/* Checking spinner */}
        {phase === 'checking' && (
          <div className="text-center">
            <p className="text-[12px] text-gray-500 animate-pulse">Running checks...</p>
          </div>
        )}
      </div>

      {/* CSS animation */}
      <style>{`
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  )
}
