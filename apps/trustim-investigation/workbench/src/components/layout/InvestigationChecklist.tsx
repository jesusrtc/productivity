import { useMemo } from 'react'
import { useGraphStore } from '../../store/graph'

interface Props {
  onClose: () => void
  onRunStep: (prompt: string) => void
}

interface CheckItem {
  id: string
  label: string
  description: string
  keywords: string[] // If any node label/query matches these, mark as checked
  prompt: string // Prompt to run if unchecked
}

const INVESTIGATION_CHECKLIST: CheckItem[] = [
  {
    id: 'email_domains',
    label: 'Email domain analysis',
    description: 'Check email domain distribution for disposable/suspicious TLDs',
    keywords: ['email domain', 'split_part', '@', 'email_domain', 'disposable'],
    prompt: 'Analyze email domain distribution — check for disposable TLDs (.xyz, .icu, .top) and high-volume domains',
  },
  {
    id: 'ip_analysis',
    label: 'IP clustering & ASN',
    description: 'Check IP address patterns, datacenter vs residential',
    keywords: ['ip', 'requestheader__ip', 'asn', 'ip_org', 'datacenter', 'hosting'],
    prompt: 'Analyze IP clustering — check for datacenter IPs, hosting providers, and IP reuse patterns',
  },
  {
    id: 'device_fingerprints',
    label: 'Device fingerprints',
    description: 'Check canvas hash, WebGL renderer, RTT for automation signals',
    keywords: ['canvashash', 'webglrenderer', 'device', 'fingerprint', 'swiftshader', 'rtt'],
    prompt: 'Analyze device fingerprints — check canvas hash, WebGL renderer, and RTT for automation indicators like SwiftShader',
  },
  {
    id: 'challenge_rates',
    label: 'Challenge solve rates',
    description: 'Check captcha, phone, email PIN completion rates',
    keywords: ['challenge', 'captcha', 'solve rate', 'securitychallengeevent', 'irsf', 'voip'],
    prompt: 'Check challenge solve rates — captcha, phone verification, email PIN. Look for solver service indicators',
  },
  {
    id: 'restriction_status',
    label: 'Restriction status',
    description: 'Check if identified accounts have been restricted',
    keywords: ['restriction', 'restricted', 'dim_member_trust', 'member_restrictions'],
    prompt: 'Check restriction status for the identified cohort — are defenses catching these accounts?',
  },
  {
    id: 'wow_metrics',
    label: 'T7D WoW metrics',
    description: 'Compute week-over-week changes for key metrics',
    keywords: ['wow', 't7d', 'week over week', 'wow_pct', 'lag('],
    prompt: 'Compute T7D WoW for relevant True North metrics (member reports, self-reports, prevalence)',
  },
  {
    id: 'impact_assessment',
    label: 'Impact assessment (DIHE)',
    description: 'Assess downstream harmful impact from the cohort',
    keywords: ['dihe', 'impact', 'fact_experience', 'harmful', 'experience_type'],
    prompt: 'Assess DIHE cohort impact — check downstream harmful experiences (invitations, messages) from identified accounts',
  },
  {
    id: 'sev_assessment',
    label: 'SEV assessment',
    description: 'Determine incident severity using official thresholds',
    keywords: ['sev', 'sev-1', 'sev-2', 'sev-3', 'sev-4', 'severity'],
    prompt: 'Run SEV assessment — compute T7D WoW for all relevant metrics and check against SEV thresholds',
  },
]

/** Interactive investigation checklist — auto-checks completed dimensions */
export function InvestigationChecklist({ onClose, onRunStep }: Props) {
  const nodes = useGraphStore((s) => s.nodes)

  const checkedItems = useMemo(() => {
    const checked = new Set<string>()
    const nodeTexts = Object.values(nodes).map(n =>
      [n.label, n.query, n.result_summary, ...(n.tags || [])].join(' ').toLowerCase()
    )

    for (const item of INVESTIGATION_CHECKLIST) {
      const isChecked = nodeTexts.some(text =>
        item.keywords.some(kw => text.includes(kw.toLowerCase()))
      )
      if (isChecked) checked.add(item.id)
    }
    return checked
  }, [nodes])

  const completedCount = checkedItems.size
  const totalCount = INVESTIGATION_CHECKLIST.length
  const pct = Math.round((completedCount / totalCount) * 100)

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[100]" onClick={onClose}>
      <div className="glass-panel rounded-2xl p-6 w-[480px] max-h-[80vh] flex flex-col animate-[fadeIn_0.2s_ease-out]" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-medium text-gray-200">Investigation Checklist</h2>
            <p className="text-[11px] text-gray-500 mt-0.5">{completedCount}/{totalCount} dimensions covered ({pct}%)</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-200">{'\u2715'}</button>
        </div>

        {/* Progress bar */}
        <div className="h-1.5 bg-surface-3 rounded-full mb-4 overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${pct}%`,
              backgroundColor: pct === 100 ? '#22c55e' : pct > 50 ? '#3b82f6' : '#6b7280',
            }}
          />
        </div>

        <div className="flex-1 overflow-y-auto space-y-1.5">
          {INVESTIGATION_CHECKLIST.map(item => {
            const isDone = checkedItems.has(item.id)
            return (
              <div
                key={item.id}
                className={`flex items-start gap-3 rounded-lg px-3 py-2.5 transition-colors ${
                  isDone ? 'bg-green-900/10' : 'bg-white/[0.02] hover:bg-white/[0.04]'
                }`}
              >
                <div className={`w-5 h-5 rounded-md border-2 flex items-center justify-center flex-shrink-0 mt-0.5 transition-colors ${
                  isDone ? 'border-green-500 bg-green-500/20' : 'border-gray-600'
                }`}>
                  {isDone && <span className="text-green-400 text-[10px]">{'\u2714'}</span>}
                </div>
                <div className="flex-1 min-w-0">
                  <div className={`text-[13px] font-medium ${isDone ? 'text-green-300' : 'text-gray-200'}`}>
                    {item.label}
                  </div>
                  <div className="text-[11px] text-gray-500 mt-0.5">{item.description}</div>
                </div>
                {!isDone && (
                  <button
                    onClick={() => { onRunStep(item.prompt); onClose() }}
                    className="text-[10px] bg-accent-blue/15 text-accent-blue hover:bg-accent-blue/25 px-2 py-1 rounded flex-shrink-0 transition-colors"
                  >
                    Run
                  </button>
                )}
              </div>
            )
          })}
        </div>

        {completedCount === totalCount && (
          <div className="mt-4 pt-3 border-t border-surface-3 text-center">
            <p className="text-[13px] text-green-400 font-medium">All investigation dimensions covered</p>
            <p className="text-[11px] text-gray-500 mt-1">Ready for SEV assessment and audit trail export</p>
          </div>
        )}
      </div>
    </div>
  )
}
