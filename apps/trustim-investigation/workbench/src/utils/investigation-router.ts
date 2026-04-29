/**
 * Investigation Router — maps user prompts to the appropriate TrustIM skill
 * based on the headless-investigation routing tables.
 *
 * This is used to:
 * 1. Suggest the right skill in the system prompt sent to Claude
 * 2. Show investigation type badges on root nodes
 * 3. Route auto-investigate to the right skill sequence
 */

export interface InvestigationRoute {
  skill: string
  trino_account: string
  description: string
  category: string
}

/** Primary routing: keyword matching against the user's prompt */
const KEYWORD_ROUTES: { keywords: string[]; route: InvestigationRoute }[] = [
  {
    keywords: ['registration', 'signup', 'reg spike', 'cold reg', 'fake account', 'disposable domain', '.xyz', '.icu', '.top', 'automation at reg', 'member id', 'mid ', 'mids', 'account investigation'],
    route: { skill: 'suspicious-registrations', trino_account: 'ir2fake', description: 'Cold registration spike investigation', category: 'Fake Accounts' },
  },
  {
    keywords: ['ato', 'account takeover', 'credential', 'password reset', 'login spike', 'list washing', 'evilginx', 'phishing', 'mitm'],
    route: { skill: 'account-takeover', trino_account: 'ir2ato', description: 'Account takeover investigation', category: 'ATO' },
  },
  {
    keywords: ['login', 'auth failure', 'login score', 'ip washing', 'credential washing'],
    route: { skill: 'login-analysis', trino_account: 'ir2ato', description: 'Login abuse analysis', category: 'Login' },
  },
  {
    keywords: ['scraping', 'data egress', 'denial event', 'block filter', 'guest scraping', 'member scraping'],
    route: { skill: 'scraping-investigation', trino_account: 'ir2scraping', description: 'Scraping investigation', category: 'Scraping' },
  },
  {
    keywords: ['fake romance', 'romance scam', 'bcookie fanout', 'name change', 'scam', 'money scam'],
    route: { skill: 'fake-account-research', trino_account: 'ir2fake', description: 'Fake account / romance scam investigation', category: 'Fake Accounts' },
  },
  {
    keywords: ['messaging', 'group spam', 'inmail', 'invitation', 'non-connection message'],
    route: { skill: 'messaging-abuse', trino_account: 'trustim', description: 'Messaging abuse', category: 'Messaging' },
  },
  {
    keywords: ['abi', 'invite spam', 'bulk invite', 'contacts upload', 'invitation abuse'],
    route: { skill: 'abi-abuse', trino_account: 'trustim', description: 'Address book invitation abuse', category: 'ABI' },
  },
  {
    keywords: ['challenge', 'captcha', 'phone challenge', 'irsf', 'voip', 'sms', 'email pin'],
    route: { skill: 'challenge-research', trino_account: 'trustim', description: 'Challenge/phone abuse', category: 'Challenge' },
  },
  {
    keywords: ['qps', 'traffic spike', 'site speed', 'bot wave', 'ddos', 'ipv6'],
    route: { skill: 'site-anomaly', trino_account: 'trustim', description: 'Site traffic anomaly', category: 'Traffic' },
  },
  {
    keywords: ['sales navigator', 'sn abuse', 'recruiter', 'free trial', 'contract', 'enterprise'],
    route: { skill: 'sn-abuse', trino_account: 'ir2fake', description: 'Sales Navigator abuse', category: 'SN' },
  },
  {
    keywords: ['domain', 'email domain', 'mx record', 'disposable'],
    route: { skill: 'domain-investigation', trino_account: 'trustim', description: 'Email domain risk analysis', category: 'Domain' },
  },
  {
    keywords: ['rule', 'fpr', 'false positive', 'drools', 'model performance', 'umi'],
    route: { skill: 'rule-tuning', trino_account: 'trustim', description: 'Rule performance tuning', category: 'Rules' },
  },
  {
    keywords: ['sev', 'dihe', 'member report', 'self report', 'wow', 't7d'],
    route: { skill: 'sev-assessment', trino_account: 'trustim', description: 'SEV assessment', category: 'SEV' },
  },
  {
    keywords: ['alert', 'incident', 'triage', 'oncall'],
    route: { skill: 'oncall-triage', trino_account: 'trustim', description: 'General oncall triage', category: 'Triage' },
  },
]

/** InResponse Type enum → investigation skill (from headless-investigation routing table) */
const IR_TYPE_ROUTES: Record<string, InvestigationRoute> = {
  'ato': { skill: 'account-takeover', trino_account: 'ir2ato', description: 'Account takeover investigation', category: 'ATO' },
  'fake accounts': { skill: 'fake-account-research', trino_account: 'ir2fake', description: 'Fake account investigation', category: 'Fake Accounts' },
  'guest scraping': { skill: 'scraping-investigation', trino_account: 'ir2scraping', description: 'Guest scraping investigation', category: 'Scraping' },
  'member scraping': { skill: 'scraping-investigation', trino_account: 'ir2scraping', description: 'Member scraping investigation', category: 'Scraping' },
  'private messaging': { skill: 'messaging-abuse', trino_account: 'trustim', description: 'Private messaging abuse', category: 'Messaging' },
  'dos/ddos': { skill: 'site-anomaly', trino_account: 'trustim', description: 'DoS/DDoS investigation', category: 'Traffic' },
  'enterprise violations': { skill: 'sn-abuse', trino_account: 'ir2fake', description: 'Enterprise violations', category: 'SN' },
}

/** Route a user prompt to the most appropriate investigation skill */
export function routeInvestigation(prompt: string): InvestigationRoute | null {
  const result = routeInvestigationWithConfidence(prompt)
  return result?.route || null
}

/** Route with confidence scoring */
export function routeInvestigationWithConfidence(prompt: string): { route: InvestigationRoute; confidence: 'high' | 'medium' | 'low'; matchCount: number } | null {
  const lower = prompt.toLowerCase()

  // Try InResponse type enum matching first (highest priority — exact type match)
  for (const [irType, route] of Object.entries(IR_TYPE_ROUTES)) {
    if (lower.includes(irType)) return { route, confidence: 'high', matchCount: 1 }
  }

  // Fall back to keyword matching
  let bestRoute: InvestigationRoute | null = null
  let bestScore = 0

  for (const { keywords, route } of KEYWORD_ROUTES) {
    let score = 0
    for (const kw of keywords) {
      if (lower.includes(kw)) score++
    }
    if (score > bestScore) {
      bestScore = score
      bestRoute = route
    }
  }

  if (!bestRoute) return null

  const confidence = bestScore >= 3 ? 'high' : bestScore >= 2 ? 'medium' : 'low'
  return { route: bestRoute, confidence, matchCount: bestScore }
}

/** Get the Trino authorization account for a skill */
export function getTrinoAccount(skillName: string): string {
  for (const { route } of KEYWORD_ROUTES) {
    if (route.skill === skillName) return route.trino_account
  }
  return 'trustim'
}

/** Get all available investigation templates for the quick-start UI */
export function getInvestigationTemplates(): { label: string; prompt: string; skill: string; icon: string }[] {
  return [
    { label: 'Registration Spike', prompt: 'Investigate cold registration spike from yesterday', skill: 'suspicious-registrations', icon: '\u{1F4C8}' },
    { label: 'ATO / Phishing', prompt: 'Investigate account takeover signals', skill: 'account-takeover', icon: '\u{1F512}' },
    { label: 'Scraping', prompt: 'Investigate scraping activity and denial events', skill: 'scraping-investigation', icon: '\u{1F310}' },
    { label: 'Login Abuse', prompt: 'Investigate login abuse patterns and credential washing', skill: 'login-analysis', icon: '\u{1F511}' },
    { label: 'Messaging Spam', prompt: 'Investigate messaging and invitation spam', skill: 'messaging-abuse', icon: '\u{1F4E8}' },
    { label: 'ABI Abuse', prompt: 'Investigate address book invitation abuse', skill: 'abi-abuse', icon: '\u{1F4CB}' },
    { label: 'Challenge Abuse', prompt: 'Investigate challenge/captcha abuse and IRSF', skill: 'challenge-research', icon: '\u{1F4F1}' },
    { label: 'SEV Assessment', prompt: 'Run SEV assessment for True North metrics', skill: 'sev-assessment', icon: '\u{1F3AF}' },
    { label: 'Alert Triage', prompt: 'Triage oncall alert', skill: 'oncall-triage', icon: '\u{1F6A8}' },
  ]
}
