export interface InvestigationDimension {
  id: string
  label: string
  keywords: string[]
  prompt: string
  skill?: string
}

/** Investigation dimensions for checklist-driven auto-investigate. Each links to a skill for richer context. */
export const INVESTIGATION_DIMENSIONS: InvestigationDimension[] = [
  { id: 'email', label: 'email domains', keywords: ['email domain', 'split_part', '@', 'email_domain'], skill: 'suspicious-registrations', prompt: 'Analyze email domain distribution — check for disposable TLDs (.xyz, .icu, .top) and high-volume domains using split_part(email, \'@\', 2) on tracking.registrationevent. [Read skills/suspicious-registrations/SKILL.md for query templates.]' },
  { id: 'ip', label: 'IP analysis', keywords: ['ip', 'requestheader__ip', 'asn'], skill: 'suspicious-registrations', prompt: 'Analyze IP address clustering — check for datacenter IPs, hosting providers, and IP reuse patterns using requestheader__ip. [Read skills/suspicious-registrations/SKILL.md for IP analysis queries.]' },
  { id: 'device', label: 'device fingerprints', keywords: ['canvashash', 'webglrenderer', 'fingerprint', 'swiftshader'], skill: 'suspicious-registrations', prompt: 'Analyze device fingerprints — check canvas hash and WebGL renderer from TRACKING.AntiAbuseJavaScriptDeviceFeaturesEvent for automation indicators like SwiftShader. [Read skills/suspicious-registrations/SKILL.md for device fingerprint queries.]' },
  { id: 'challenge', label: 'challenge rates', keywords: ['challenge', 'securitychallengeevent', 'captcha'], skill: 'challenge-research', prompt: 'Check challenge solve rates — analyze securitychallengeevent for captcha completion rates and solver patterns. [Read skills/challenge-research/SKILL.md for detailed methodology.]' },
  { id: 'restriction', label: 'restrictions', keywords: ['restriction', 'dim_member_trust'], prompt: 'Check restriction status for the identified cohort — query prod_foundation_tables.dim_member_trust_restrictions to see if defenses caught these accounts.' },
  { id: 'wow', label: 'WoW metrics', keywords: ['wow', 't7d', 'wow_pct'], skill: 'sev-assessment', prompt: 'Compute T7D WoW for relevant True North metrics — member reports, self-reports, prevalence. Use LAG(t7d_sum, 7) to compute week-over-week change. [Read skills/sev-assessment/SKILL.md for threshold tables.]' },
  { id: 'impact', label: 'DIHE impact', keywords: ['dihe', 'fact_experience', 'impact'], prompt: 'Assess downstream harmful impact — check u_tds.fact_experience_base for harmful experiences (invitations, messages) created by the identified cohort.' },
  { id: 'sev', label: 'SEV assessment', keywords: ['sev', 'sev-1', 'sev-2', 'severity'], skill: 'sev-assessment', prompt: 'Run SEV assessment — check all T7D WoW metrics against official SEV thresholds. [Read skills/sev-assessment/SKILL.md for the full threshold tables and modifiers.]' },
]
