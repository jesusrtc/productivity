import type { InvestigationNode } from '../../types'

/** Suggests investigation follow-ups based on node content */
export function SuggestedNextSteps({ node, onSelect }: { node: InvestigationNode; onSelect: (prompt: string) => void }) {
  const suggestions: { label: string; prompt: string }[] = []
  const raw = (node.result_raw || '').toLowerCase()
  const label = (node.label || '').toLowerCase()

  // Context-specific suggestions based on what the query found
  if (raw.includes('ip') || label.includes('ip')) {
    suggestions.push({ label: 'Lookup IP orgs', prompt: 'Look up the ASN/org information for the top IPs from the previous results. Check if they are datacenter, residential, or VPN IPs.' })
  }
  if (raw.includes('email') || raw.includes('domain') || label.includes('domain')) {
    suggestions.push({ label: 'Check MX records', prompt: 'Check MX records and domain age for the suspicious email domains found. Are they disposable email providers?' })
  }
  if (raw.includes('member') || raw.includes('memberid') || raw.includes('member_id')) {
    suggestions.push({ label: 'Check member profiles', prompt: 'Check the profile completion and activity patterns for the suspicious member IDs found. Are they automated or real users?' })
  }
  if (raw.includes('registration') || label.includes('reg')) {
    suggestions.push({ label: 'Device fingerprints', prompt: 'Analyze device fingerprints (canvas hash, WebGL renderer) for the registration cohort. Look for automation indicators like SwiftShader.' })
    suggestions.push({ label: 'Challenge solve rates', prompt: 'Check challenge solve rates for this registration cohort. Are they bypassing captcha with solver services?' })
  }
  if (raw.includes('ato') || raw.includes('login') || label.includes('ato') || label.includes('login')) {
    suggestions.push({ label: 'Credential patterns', prompt: 'Analyze login patterns: are these credential stuffing attempts? Check for password-first vs session-based logins.' })
  }
  if (node.confidence > 0.6) {
    suggestions.push({ label: 'Impact assessment', prompt: 'Assess the downstream impact of this finding. How many members were affected? What harmful experiences were created?' })
    suggestions.push({ label: 'SEV assessment', prompt: 'Run a SEV assessment for this finding. Compute the T7D WoW metric and check against SEV thresholds.' })
  }
  if (raw.includes('scraping') || label.includes('scraping') || label.includes('denial')) {
    suggestions.push({ label: 'Rule effectiveness', prompt: 'Check the effectiveness of block filter rules. Are the denial rules catching the right traffic? Check for FPR.' })
  }

  // Always offer a generic dig-deeper
  if (suggestions.length === 0) {
    suggestions.push({ label: 'Dig deeper', prompt: 'Investigate this finding further. What additional queries would help confirm or refute this signal?' })
  }

  return (
    <div className="mb-3">
      <h4 className="text-[11px] text-gray-500 uppercase tracking-wider mb-1.5">Suggested next steps</h4>
      <div className="flex flex-wrap gap-1.5">
        {suggestions.slice(0, 4).map(s => (
          <button
            key={s.label}
            onClick={() => onSelect(s.prompt)}
            className="text-[11px] bg-accent-blue/10 hover:bg-accent-blue/20 text-accent-blue/80 hover:text-accent-blue px-2.5 py-1 rounded-md transition-colors"
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  )
}
