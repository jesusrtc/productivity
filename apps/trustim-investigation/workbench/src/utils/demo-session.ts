/**
 * Demo session seeder — creates a realistic pre-populated investigation graph
 * for showcasing the Workbench features without requiring a real Claude Code connection.
 *
 * All queries use real TrustIM Trino tables and patterns from production skills.
 */

import type { InvestigationNode, InvestigationEdge, Session } from '../types'
import { createNode } from '../types'
import { v4 as uuid } from 'uuid'

export function createDemoSession(): Session {
  const sessionId = uuid()
  const nodes: Record<string, InvestigationNode> = {}
  const edges: InvestigationEdge[] = []
  const now = new Date()
  const today = now.toISOString().split('T')[0]
  const ts = (minutesAgo: number) => new Date(now.getTime() - minutesAgo * 60000).toISOString()

  function addNode(overrides: Partial<InvestigationNode>): string {
    const id = uuid()
    nodes[id] = createNode({ node_id: id, ...overrides })
    return id
  }

  function addEdge(source: string, target: string, relation: InvestigationEdge['relation'] = 'led_to') {
    edges.push({ id: `${source}-${target}`, source, target, relation })
  }

  // Root: Alert triage — cold registration spike investigation
  const root = addNode({
    action_type: 'enrichment',
    label: 'Alert — Cold Registration Spike from Disposable Domains',
    query: 'ir alert view 249973199',
    status: 'completed',
    result_summary: 'Registration spike alert: high-volume registrations from disposable email domains (.xyz, .icu, .top), 280% above T7D baseline',
    result_raw: JSON.stringify({
      alert_id: 249973199,
      title: 'Cold Registration Spike — Disposable Email Domains',
      severity: 'SEV-3',
      incident_date: '2026-03-24',
      type: 'Fake Accounts',
      entity_impact: 'Members',
      detected_by: 'TrustIM Oncall Monitoring',
    }, null, 2),
    confidence: 0.88,
    reasoning: 'Root node from InResponse alert. Registration volume 280% above T7D baseline. Disposable TLD domains (.xyz, .icu, .top) driving the spike.',
    timestamp: ts(45),
    duration_ms: 1200,
  })

  // Step 1: Registration volume by email domain — real query against tracking.registrationevent
  const regQuery = addNode({
    action_type: 'query_execution',
    label: 'High-volume email domain detection',
    query: `SET SESSION li_authorization_user = 'ir2fake';\n\nSELECT split_part(email, '@', 2) AS email_domain, COUNT(*) AS reg_count\nFROM tracking.registrationevent\nWHERE datepartition = '${today}-00' AND email IS NOT NULL\nGROUP BY split_part(email, '@', 2)\nHAVING COUNT(*) >= 5\nORDER BY reg_count DESC LIMIT 20`,
    parent_ids: [root],
    status: 'completed',
    result_summary: 'quickmail.xyz: 342 regs, inbox-now.icu: 189 regs, fastdrop.top: 112 regs. Disposable TLDs account for 643 registrations vs 45 baseline.',
    result_raw: 'email_domain\treg_count\nquickmail.xyz\t342\ninbox-now.icu\t189\nfastdrop.top\t112\ngmail.com\t12045\nyahoo.com\t8934\noutlook.com\t6721\nhotmail.com\t3421',
    confidence: 0.91,
    tool_name: 'execute_trino_query',
    source_tool: 'captain',
    reasoning: 'Querying tracking.registrationevent to identify domains driving the spike. Disposable TLDs (.xyz, .icu, .top) show anomalous registration volume.',
    timestamp: ts(42),
    duration_ms: 3400,
  })
  addEdge(root, regQuery)

  // Step 2: IP-based coordinated registration analysis — real query joining registrationEvent + scoreEvent
  const ipQuery = addNode({
    action_type: 'query_execution',
    label: 'IP-based coordinated registration detection',
    query: `SELECT DISTINCT requestheader__ip AS ip, count(*) AS c,\n       COUNT(DISTINCT requestheader__useragent) AS distinct_ua_c,\n       COUNT(DISTINCT requestheader__browserid) AS distinct_bcookie_c,\n       COUNT(DISTINCT HC) AS distinct_hc_c,\n       COUNT(DISTINCT CC) AS distinct_cc_c\nFROM tracking_column.registrationEvent AS tr\nJOIN (SELECT DISTINCT submissionid, params['challenge_type'] as challenge_type,\n             params['sortedHeaderNames'] as HC, params['sortedCookieNames'] as CC\n      FROM tracking_column.scoreEvent\n      WHERE datepartition = '${today}-00' AND scorerType = 'SCORER_REGISTRATION'\n        AND scorerStage = 'CURRENT' AND params['registration_type'] = 'COLD'\n        AND params['reg_input_data_validation'] = 'VALID') ts\n  ON tr.submissionid = ts.submissionid\nWHERE tr.datepartition = '${today}-00'\nGROUP BY requestheader__ip ORDER BY c DESC LIMIT 20`,
    parent_ids: [regQuery],
    status: 'completed',
    result_summary: 'Top IP shows 187 registrations with only 2 distinct UAs and 3 bcookies. Classic datacenter automation pattern from hosting provider IPs.',
    result_raw: 'ip\tc\tdistinct_ua_c\tdistinct_bcookie_c\tdistinct_hc_c\tdistinct_cc_c\n104.238.xx.41\t187\t2\t3\t1\t1\n149.28.xx.92\t134\t1\t2\t1\t1\n207.148.xx.15\t89\t3\t4\t2\t1\n82.132.xx.201\t45\t42\t43\t18\t12\n86.12.xx.77\t28\t26\t25\t15\t11',
    confidence: 0.93,
    tool_name: 'execute_trino_query',
    source_tool: 'captain',
    reasoning: 'Joining registrationEvent with scoreEvent on submissionid to correlate IPs with cookie/header signals. Top 3 IPs show low UA diversity + extreme bcookie reuse = automated registration.',
    timestamp: ts(38),
    duration_ms: 4200,
  })
  addEdge(regQuery, ipQuery)

  // Step 3: Device fingerprint analysis — real query against AntiAbuseJavaScriptDeviceFeaturesEvent
  const deviceQuery = addNode({
    action_type: 'query_execution',
    label: 'Device fingerprint clustering — canvas hash + WebGL',
    query: `SELECT canvashash, webglrenderer, COUNT(DISTINCT header.memberid) AS members,\n       COUNT(DISTINCT requestheader.browserid) AS bcookies,\n       APPROX_PERCENTILE(rtt, 0.5) AS median_rtt_ms\nFROM TRACKING.AntiAbuseJavaScriptDeviceFeaturesEvent\nWHERE datepartition = '${today}-00'\n  AND header.memberid IN (\n    SELECT header__memberid FROM tracking_column.registrationEvent\n    WHERE datepartition = '${today}-00'\n      AND split_part(email, '@', 2) IN ('quickmail.xyz','inbox-now.icu','fastdrop.top')\n  )\nGROUP BY canvashash, webglrenderer\nORDER BY members DESC LIMIT 10`,
    parent_ids: [regQuery],
    status: 'completed',
    result_summary: 'Top canvas hash shared by 298 members with only 5 bcookies. WebGL renderer shows SwiftShader (headless Chrome VM). Median RTT 312ms confirms proxy usage (>199ms threshold).',
    result_raw: 'canvashash\twebglrenderer\tmembers\tbcookies\tmedian_rtt_ms\n0x8a2f1d3e\tGoogle SwiftShader\t298\t5\t312\n0x7c4b2e9a\tGoogle SwiftShader\t87\t3\t289\n0xf1a39c7d\tANGLE (Intel HD 630)\t45\t42\t34\n0xd5e28b4f\tANGLE (NVIDIA GeForce)\t38\t36\t28',
    confidence: 0.96,
    tool_name: 'execute_trino_query',
    source_tool: 'captain',
    reasoning: 'Branching to check device fingerprints via AntiAbuseJavaScriptDeviceFeaturesEvent. SwiftShader renderer = headless Chrome VM. Canvas hash shared by 298 members with 5 bcookies = extreme cookie reuse. RTT >199ms = proxy traffic.',
    timestamp: ts(35),
    duration_ms: 3100,
  })
  addEdge(regQuery, deviceQuery, 'branched_from')

  // Step 4: Member restriction check and behavioral signals
  const scoringQuery = addNode({
    action_type: 'enrichment',
    label: 'Cohort restriction status + profile completion',
    query: `SELECT\n  COUNT(*) AS total_members,\n  COUNT(CASE WHEN ma.restrictioninfo IS NOT NULL THEN 1 END) AS already_restricted,\n  COUNT(CASE WHEN dm.num_connections > 0 THEN 1 END) AS has_connections,\n  COUNT(CASE WHEN dm.headline IS NOT NULL THEN 1 END) AS has_headline,\n  COUNT(CASE WHEN dm.profile_picture_url IS NOT NULL THEN 1 END) AS has_photo\nFROM tracking_column.registrationEvent tr\nLEFT JOIN data_derived.member_restrictions ma ON tr.header__memberid = ma.member_id\nLEFT JOIN prod_foundation_tables.dim_member_all dm ON tr.header__memberid = dm.member_id\nWHERE tr.datepartition = '${today}-00'\n  AND split_part(email, '@', 2) IN ('quickmail.xyz','inbox-now.icu','fastdrop.top')`,
    parent_ids: [deviceQuery],
    status: 'completed',
    result_summary: '643 total members. 0 already restricted. Only 3 added connections, 0 have headlines or photos. Zero engagement confirms dormant fake accounts.',
    result_raw: JSON.stringify({
      total_members: 643,
      already_restricted: 0,
      has_connections: 3,
      has_headline: 0,
      has_photo: 0,
    }, null, 2),
    confidence: 0.89,
    source_tool: 'captain',
    reasoning: 'Checking dim_member_all and member_restrictions for the cohort. Zero profile completion and minimal connection activity confirms these are dormant fake accounts created by automation.',
    timestamp: ts(30),
    duration_ms: 4200,
  })
  addEdge(deviceQuery, scoringQuery)

  // Step 5: Residential IP check — benign finding for residential traffic
  const residentialCheck = addNode({
    action_type: 'query_execution',
    label: 'Residential IP registration patterns — benign check',
    query: `SELECT ip2str(requestheader.ipasbytes) AS ip, header__memberid,\n       from_unixtime(header__time / 1000) AS reg_time,\n       requestheader__useragent AS ua\nFROM tracking_column.registrationEvent\nWHERE datepartition = '${today}-00'\n  AND split_part(email, '@', 2) IN ('quickmail.xyz','inbox-now.icu','fastdrop.top')\n  AND ip_org_name(ip2str(requestheader.ipasbytes)) NOT LIKE '%Hosting%'\n  AND ip_org_name(ip2str(requestheader.ipasbytes)) NOT LIKE '%Cloud%'\n  AND ip_org_name(ip2str(requestheader.ipasbytes)) NOT LIKE '%Server%'\nORDER BY reg_time LIMIT 50`,
    parent_ids: [ipQuery],
    status: 'completed',
    result_summary: '73 members from residential ISPs (BT, Virgin Media, Sky). Unique user agents, spread timing, diverse bcookies. Likely legitimate users who chose the same disposable email providers.',
    result_raw: 'Residential IP registrations show normal patterns: 73 members, unique UAs per member, no bcookie reuse, registration times spread over 14 hours. ISPs include BT (28), Virgin Media (24), Sky (21).',
    confidence: 0.1, // Low confidence = benign finding
    tool_name: 'execute_trino_query',
    source_tool: 'captain',
    reasoning: 'Filtering to non-hosting IPs using ip_org_name(). Residential ISP traffic shows normal diversity in UAs, bcookies, and timing — likely legitimate users. Not part of the automated campaign.',
    timestamp: ts(33),
    duration_ms: 1900,
  })
  addEdge(ipQuery, residentialCheck)

  // Step 6: SEV assessment + recommendation
  const synthesis = addNode({
    action_type: 'recommendation',
    label: 'SEV assessment + triage recommendation',
    query: 'SEV assessment: FA member reports T7D WoW computation per sev-assessment thresholds',
    parent_ids: [ipQuery, deviceQuery, scoringQuery],
    status: 'completed',
    result_summary: 'CONFIRMED: Automated fake account registration campaign. 570 of 643 accounts are bot-created. SEV-3 recommended (FA member reports T7D WoW +18%, exceeds >15% SEV-4 threshold, boosted to SEV-3 due to novel attack pattern).',
    result_raw: `## SEV Assessment\n\n**FA member reports T7D WoW:** +18% (threshold: >15% = SEV-4, >20% = SEV-3)\n**Baseline SEV:** SEV-4\n**Modifier applied:** +1 boost (novel disposable TLD pattern not previously seen)\n**Final SEV:** SEV-3\n\n## Evidence Summary\n- 643 registrations from disposable TLD domains (280% above T7D baseline)\n- 410 (64%) from 3 hosting provider IPs with extreme UA/bcookie reuse\n- 298 (46%) share identical canvas hash + SwiftShader WebGL renderer (headless Chrome VM)\n- Median RTT 312ms confirms proxy usage (>199ms threshold)\n- 0 accounts completed profile or posted content\n\n## Benign Signal\n- 73 members from residential ISPs appear legitimate\n\n## Recommended Actions\n1. Restrict 570 hosting-origin accounts via ASTA batch job\n2. Add disposable TLD pattern (.xyz/.icu/.top cluster) to SCORER_REGISTRATION rules\n3. Monitor for pattern migration to other TLDs`,
    confidence: 0.93,
    reasoning: 'SEV assessment per sev-assessment skill thresholds. FA member reports T7D WoW +18% exceeds SEV-4 threshold (>15%). Novel attack pattern modifier boosts to SEV-3. Datacenter IPs + SwiftShader + cookie reuse = confirmed automation.',
    timestamp: ts(25),
    duration_ms: 500,
    investigator_notes: 'Confirmed with detection team. ASTA restriction job queued. Rule update PR in progress.',
  })
  addEdge(ipQuery, synthesis, 'supports')
  addEdge(deviceQuery, synthesis, 'supports')
  addEdge(scoringQuery, synthesis, 'supports')

  return {
    id: sessionId,
    name: 'Demo: Cold Reg Spike — Disposable Domains',
    created_at: ts(45),
    updated_at: ts(25),
    starting_input: 'Alert 249973199',
    starting_input_type: 'alert_id',
    nodes,
    edges,
    messages: [
      { id: uuid(), role: 'system', content: 'Investigation started with: Alert 249973199', timestamp: ts(45), node_ids: [root] },
      { id: uuid(), role: 'assistant', content: 'Loaded alert from InResponse. This is a **cold registration spike** from disposable email domains (.xyz, .icu, .top). Starting investigation with `tracking.registrationevent`.', timestamp: ts(44), node_ids: [] },
      { id: uuid(), role: 'assistant', content: 'Registration volume query complete. **quickmail.xyz** (342), **inbox-now.icu** (189), **fastdrop.top** (112) — 643 registrations from disposable TLDs.', timestamp: ts(42), node_ids: [regQuery] },
      { id: uuid(), role: 'assistant', content: 'Branching into IP correlation (registrationEvent JOIN scoreEvent) and device fingerprinting (AntiAbuseJavaScriptDeviceFeaturesEvent).', timestamp: ts(40), node_ids: [] },
      { id: uuid(), role: 'assistant', content: 'IP analysis: top 3 IPs have 410 registrations with minimal UA/bcookie diversity. Device analysis: SwiftShader renderer + canvas hash shared by 298 members + RTT >199ms. **Confirmed automation.**', timestamp: ts(35), node_ids: [ipQuery, deviceQuery] },
      { id: uuid(), role: 'assistant', content: 'SEV assessment complete. FA member reports T7D WoW +18% (>15% = SEV-4, boosted to **SEV-3** for novel attack). 570 accounts flagged for ASTA restriction.', timestamp: ts(25), node_ids: [synthesis] },
      { id: uuid(), role: 'assistant', content: `## Investigation Conclusion

**Alert 249973199 — Cold Registration Spike from Disposable Domains**

### Executive Summary
Automated fake account registration campaign detected: 570 bot-created accounts from 3 disposable TLD domains (.xyz, .icu, .top) via 3 datacenter IPs running headless Chrome. 73 additional registrations from residential ISPs appear legitimate and should not be actioned.

### Key Findings
| Signal | Value | Threshold |
|--------|-------|-----------|
| Disposable TLD registrations | 643 (280% above T7D) | >100% = anomalous |
| Datacenter IP registrations | 410 (64% of cohort) | >30% = suspicious |
| Shared canvas hash (SwiftShader) | 298 members / 5 bcookies | >10:1 = automated |
| Median RTT | 312ms | >199ms = proxy |
| Profile completion | 0% | <5% = dormant |
| FA member reports T7D WoW | +18% | >15% = SEV-4 |

### SEV: SEV-3
Baseline SEV-4 (+18% WoW exceeds 15% threshold), boosted to SEV-3 due to novel disposable TLD attack pattern not previously seen in detection rules.

### Recommended Actions
- 🔴 **Immediate:** Restrict 570 hosting-origin accounts via ASTA batch job
- 🟠 **Short-term:** Add disposable TLD cluster pattern (.xyz/.icu/.top) to SCORER_REGISTRATION rules
- 🟡 **Medium-term:** Add canvas hash + SwiftShader combo as a registration signal
- 🟢 **Monitor:** Watch for pattern migration to other TLDs (.click, .buzz, .surf)

---
*Investigation complete. 6 queries executed across 4 Trino tables in 20 minutes.*`, timestamp: ts(24), node_ids: [] },
    ],
    skills_used: ['suspicious-registrations', 'fake-account-research', 'sev-assessment'],
    tools_used: ['execute_trino_query'],
    mcp_tools: [],
  }
}
