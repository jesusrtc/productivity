import { useState } from 'react'

interface Props {
  onClose: () => void
  onSendPrompt: (prompt: string) => void
}

const GUIDE_STEPS = [
  {
    title: 'Start with context',
    description: 'What triggered this investigation? Paste an alert ID, describe the signal, or share member IDs.',
    examples: [
      { label: 'Alert triage', prompt: 'Triage alert 249973199 — registration spike detected' },
      { label: 'MID investigation', prompt: 'Investigate member IDs 123456789, 987654321 — flagged as suspicious' },
      { label: 'Metric spike', prompt: 'FA member reports T7D WoW is +25% — investigate registration sources' },
    ],
  },
  {
    title: 'Follow the signals',
    description: 'As nodes appear in the graph, click high-confidence ones (red/orange) and ask follow-up questions.',
    tips: [
      'Click any node to see details and continue from it',
      'Use "Auto-investigate" for autonomous deep-dive',
      'Use "Fan out with skill" to apply specific skill patterns',
    ],
  },
  {
    title: 'Check key dimensions',
    description: 'A thorough investigation checks multiple angles:',
    checklist: [
      { label: 'IP analysis', prompt: 'Analyze IP clustering and ASN distribution for this cohort' },
      { label: 'Device fingerprints', prompt: 'Check device fingerprints — canvas hash, WebGL renderer, RTT' },
      { label: 'Email domains', prompt: 'Analyze email domain distribution — check for disposable TLDs' },
      { label: 'Challenge solve rates', prompt: 'Check challenge solve rates — captcha, phone, email PIN' },
      { label: 'Restriction status', prompt: 'Check restriction status for the identified cohort' },
    ],
  },
  {
    title: 'Assess severity',
    description: 'Compute the T7D WoW for relevant metrics and check against SEV thresholds.',
    examples: [
      { label: 'FA reports WoW', prompt: 'Compute FA member reports T7D WoW for the last 14 days' },
      { label: 'ATO self-reports WoW', prompt: 'Compute ATO self-reports T7D WoW and check SEV thresholds' },
      { label: 'DIHE impact', prompt: 'Assess DIHE cohort impact — check downstream harmful experiences' },
    ],
  },
  {
    title: 'Document & export',
    description: 'Export your findings for the audit trail.',
    tips: [
      'Click "Export" → Jira to create a ticket draft',
      'Click "Export" → Notebook for ipynb audit trail',
      'Click "Handoff" to generate a continuation prompt',
      'All queries are auto-saved to the investigation notebook',
    ],
  },
]

/** Guided investigation wizard for new investigators */
export function InvestigationGuide({ onClose, onSendPrompt }: Props) {
  const [step, setStep] = useState(0)
  const currentStep = GUIDE_STEPS[step]

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[100]" onClick={onClose}>
      <div className="glass-panel rounded-2xl p-6 w-[520px] max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-medium text-gray-200">Investigation Guide</h2>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-gray-500">Step {step + 1} of {GUIDE_STEPS.length}</span>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-200">{'\u2715'}</button>
          </div>
        </div>

        {/* Progress dots */}
        <div className="flex gap-1.5 mb-4">
          {GUIDE_STEPS.map((_, i) => (
            <button
              key={i}
              onClick={() => setStep(i)}
              className={`h-1.5 rounded-full transition-all ${i === step ? 'w-6 bg-accent-blue' : 'w-1.5 bg-surface-3 hover:bg-surface-4'}`}
            />
          ))}
        </div>

        <h3 className="text-[15px] font-medium text-gray-200 mb-2">{currentStep.title}</h3>
        <p className="text-[13px] text-gray-400 leading-relaxed mb-4">{currentStep.description}</p>

        {/* Examples (clickable prompts) */}
        {currentStep.examples && (
          <div className="space-y-1.5 mb-4">
            {currentStep.examples.map(ex => (
              <button
                key={ex.label}
                onClick={() => { onSendPrompt(ex.prompt); onClose() }}
                className="w-full text-left bg-white/[0.03] hover:bg-white/[0.06] rounded-lg px-3 py-2 transition-colors"
              >
                <div className="text-[12px] text-accent-blue font-medium">{ex.label}</div>
                <div className="text-[11px] text-gray-500">{ex.prompt}</div>
              </button>
            ))}
          </div>
        )}

        {/* Checklist items (clickable) */}
        {currentStep.checklist && (
          <div className="space-y-1.5 mb-4">
            {currentStep.checklist.map(item => (
              <button
                key={item.label}
                onClick={() => { onSendPrompt(item.prompt); onClose() }}
                className="w-full text-left flex items-center gap-2 bg-white/[0.03] hover:bg-white/[0.06] rounded-lg px-3 py-2 transition-colors"
              >
                <span className="text-accent-cyan text-[12px]">{'\u25CB'}</span>
                <div>
                  <span className="text-[12px] text-gray-200">{item.label}</span>
                  <span className="text-[11px] text-gray-500 ml-2">{item.prompt.slice(0, 50)}</span>
                </div>
              </button>
            ))}
          </div>
        )}

        {/* Tips */}
        {currentStep.tips && (
          <div className="space-y-1 mb-4">
            {currentStep.tips.map((tip, i) => (
              <div key={i} className="flex items-start gap-2 text-[12px] text-gray-400">
                <span className="text-accent-blue mt-0.5">{'\u2022'}</span>
                <span>{tip}</span>
              </div>
            ))}
          </div>
        )}

        {/* Navigation */}
        <div className="flex justify-between mt-auto pt-4 border-t border-surface-3">
          <button
            onClick={() => setStep(s => Math.max(0, s - 1))}
            disabled={step === 0}
            className="text-[12px] text-gray-400 hover:text-gray-200 disabled:text-gray-600 transition-colors"
          >
            Previous
          </button>
          {step < GUIDE_STEPS.length - 1 ? (
            <button
              onClick={() => setStep(s => s + 1)}
              className="text-[12px] bg-accent-blue/20 text-accent-blue hover:bg-accent-blue/30 px-4 py-1.5 rounded-lg transition-colors"
            >
              Next step
            </button>
          ) : (
            <button
              onClick={onClose}
              className="text-[12px] bg-accent-blue hover:bg-blue-500 text-white px-4 py-1.5 rounded-lg transition-colors"
            >
              Start investigating
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
