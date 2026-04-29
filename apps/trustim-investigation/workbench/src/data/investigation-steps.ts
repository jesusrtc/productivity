import type { ActionType } from '../types'

export interface InvestigationStep {
  label: string
  actionType: ActionType
  queryTemplate: string
  resultTemplate: (severity: string) => string
}

/**
 * Real TrustIM investigation steps — used as fallback when Claude Code is not connected.
 * When Claude Code IS connected, the agent decides its own investigation steps.
 */
export const INVESTIGATION_STEPS: InvestigationStep[] = [
  {
    label: 'High-volume email domain detection',
    actionType: 'query_execution',
    queryTemplate: `SELECT split_part(email, '@', 2) AS email_domain, COUNT(*) AS reg_count
FROM tracking.registrationevent
WHERE datepartition = '{DATE}-00' AND email IS NOT NULL
GROUP BY split_part(email, '@', 2)
HAVING COUNT(*) >= 5
ORDER BY reg_count DESC LIMIT 20`,
    resultTemplate: (sev) => sev === 'high' || sev === 'critical'
      ? 'Disposable TLD domains (.xyz, .icu, .top) show anomalous registration volume above T7D baseline.'
      : 'Email domain distribution within normal range. No disposable TLD concentration detected.',
  },
  {
    label: 'IP-based coordinated registration analysis',
    actionType: 'query_execution',
    queryTemplate: `SELECT DISTINCT requestheader__ip AS ip, count(*) AS c,
       COUNT(DISTINCT requestheader__useragent) AS distinct_ua_c,
       COUNT(DISTINCT requestheader__browserid) AS distinct_bcookie_c
FROM tracking_column.registrationEvent AS tr
JOIN (SELECT DISTINCT submissionid, params['challenge_type'] as challenge_type
      FROM tracking_column.scoreEvent
      WHERE datepartition = '{DATE}-00' AND scorerType = 'SCORER_REGISTRATION'
        AND scorerStage = 'CURRENT' AND params['registration_type'] = 'COLD') ts
  ON tr.submissionid = ts.submissionid
WHERE tr.datepartition = '{DATE}-00'
GROUP BY requestheader__ip ORDER BY c DESC LIMIT 20`,
    resultTemplate: (sev) => sev === 'high' || sev === 'critical'
      ? 'Top IPs show low UA diversity + bcookie reuse. Hosting provider IPs with automated registration patterns.'
      : 'IP distribution shows normal diversity. No datacenter concentration detected.',
  },
  {
    label: 'Device fingerprint clustering',
    actionType: 'query_execution',
    queryTemplate: `SELECT canvashash, webglrenderer,
       COUNT(DISTINCT header.memberid) AS members,
       COUNT(DISTINCT requestheader.browserid) AS bcookies,
       APPROX_PERCENTILE(rtt, 0.5) AS median_rtt_ms
FROM TRACKING.AntiAbuseJavaScriptDeviceFeaturesEvent
WHERE datepartition = '{DATE}-00'
GROUP BY canvashash, webglrenderer
ORDER BY members DESC LIMIT 10`,
    resultTemplate: (sev) => sev === 'critical'
      ? 'SwiftShader renderer detected with shared canvas hash. RTT >199ms confirms proxy.'
      : sev === 'high'
        ? 'Some canvas hash clustering detected. Investigating bcookie fanout.'
        : 'Device fingerprints show normal diversity.',
  },
  {
    label: 'Challenge solve rate analysis',
    actionType: 'query_execution',
    queryTemplate: `SELECT datepartition, challengetype,
       count(*) as total_challenges,
       count(case when validationresult = 'USER_RESPONSE_CORRECT' then 1 end) as solved,
       count(case when validationresult = 'USER_RESPONSE_INCORRECT' then 1 end) as failed
FROM tracking.securitychallengeevent
WHERE datepartition >= '{START_DATE}-00' AND datepartition <= '{END_DATE}-00'
  AND eventtype = 'SUBMIT_CHALLENGE'
GROUP BY 1, 2 ORDER BY 1 ASC`,
    resultTemplate: (sev) => sev === 'high'
      ? 'Captcha solve rate anomalous — possible solver service in use.'
      : 'Challenge solve rates within normal parameters.',
  },
  {
    label: 'Member restriction status check',
    actionType: 'enrichment',
    queryTemplate: `SELECT
  COUNT(*) AS total,
  COUNT(CASE WHEN restriction_date IS NOT NULL AND is_current = 1 THEN 1 END) AS currently_restricted,
  COUNT(CASE WHEN restriction_date IS NOT NULL THEN 1 END) AS ever_restricted
FROM prod_foundation_tables.dim_member_trust_restrictions
WHERE member_id IN ({COHORT_MEMBER_IDS})`,
    resultTemplate: (sev) => sev === 'high'
      ? 'Low restriction rate for flagged cohort — defenses may not have caught these accounts yet.'
      : 'Restriction rates consistent with normal operations.',
  },
  {
    label: 'FA member reports T7D WoW computation',
    actionType: 'enrichment',
    queryTemplate: `WITH daily AS (
  SELECT datepartition, COUNT(*) AS reports
  FROM u_metrics.user_flagging_v3_union
  WHERE datepartition >= daysago(21) AND flagging_reason = 'FAKE_ACCOUNT'
  GROUP BY 1
), t7d AS (
  SELECT datepartition,
    SUM(reports) OVER (ORDER BY datepartition ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS t7d_sum
  FROM daily
)
SELECT datepartition, t7d_sum,
  LAG(t7d_sum, 7) OVER (ORDER BY datepartition) AS prev_t7d,
  ROUND((t7d_sum - LAG(t7d_sum, 7) OVER (ORDER BY datepartition)) * 100.0 /
    NULLIF(LAG(t7d_sum, 7) OVER (ORDER BY datepartition), 0), 1) AS wow_pct
FROM t7d ORDER BY datepartition DESC LIMIT 14`,
    resultTemplate: (sev) => sev === 'critical'
      ? 'FA member reports T7D WoW >35%. Meets SEV-1/SEV-2 threshold.'
      : sev === 'high'
        ? 'FA member reports T7D WoW between 15-35%. SEV-3 or SEV-4 range.'
        : 'FA member reports T7D WoW within normal range.',
  },
  {
    label: 'DIHE cohort impact assessment',
    actionType: 'enrichment',
    queryTemplate: `SELECT datepartition, 'cohort' AS source, COUNT(entity_urn) AS metric_value
FROM u_tds.fact_experience_base
WHERE datepartition >= daysago(36) AND experience_type IN ('RECEIVED_INVITATION', 'RECEIVED_MESSAGE')
  AND experience_creator_member_id IN ({COHORT_MEMBER_IDS})
GROUP BY 1 ORDER BY datepartition`,
    resultTemplate: (sev) => sev === 'high' || sev === 'critical'
      ? 'Cohort DIHE impact above 10% gate. Harmful experience from this cohort is measurable.'
      : 'Cohort DIHE impact below 10% gate. Minimal harm from this population.',
  },
  {
    label: 'Login score — MITM/phishing rule check',
    actionType: 'query_execution',
    queryTemplate: `SELECT header.memberid, activatedrules, count(*) as c
FROM tracking.scoreevent
WHERE datepartition = '{DATE}-00' AND scorertype = 'SCORER_LOGIN'
  AND scorerstage = 'CURRENT' AND element_at(params, 'password_result') = 'PASS'
  AND (contains(activatedrules, 'IMIR: MITM ATO')
    OR contains(activatedrules, 'Incident Response: ColorFish ATO')
    OR contains(activatedrules, 'MITM phishing attack protection'))
GROUP BY 1, 2 ORDER BY c DESC LIMIT 50`,
    resultTemplate: (sev) => sev === 'critical'
      ? 'MITM/Evilginx phishing rules firing. Active credential theft campaign detected.'
      : 'No MITM/phishing rule activations in this time window.',
  },
  {
    label: 'ATO self-reports T7D WoW',
    actionType: 'enrichment',
    queryTemplate: `WITH daily AS (
  SELECT datepartition, COUNT(*) AS cases
  FROM u_metrics.gco_case_v2_union
  WHERE datepartition >= daysago(21) AND ask_path IN ('TS-RHA')
    AND category_name IN ('ATO -TnS-', 'Account Compromise - TnS')
  GROUP BY 1
), t7d AS (
  SELECT datepartition,
    SUM(cases) OVER (ORDER BY datepartition ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS t7d_sum
  FROM daily
)
SELECT datepartition, t7d_sum,
  ROUND((t7d_sum - LAG(t7d_sum, 7) OVER (ORDER BY datepartition)) * 100.0 /
    NULLIF(LAG(t7d_sum, 7) OVER (ORDER BY datepartition), 0), 1) AS wow_pct
FROM t7d ORDER BY datepartition DESC LIMIT 14`,
    resultTemplate: (sev) => sev === 'critical'
      ? 'ATO self-reports T7D WoW >40%. SEV-1 threshold.'
      : sev === 'high'
        ? 'ATO self-reports T7D WoW >25%. SEV-2 range.'
        : 'ATO self-reports T7D WoW within normal baseline.',
  },
  {
    label: 'Scraping denial event volume',
    actionType: 'query_execution',
    queryTemplate: `SELECT datepartition, denialinfo.blockfilterrulename as rule, count(*) as c
FROM tracking.userrequestdenialevent
WHERE datepartition >= daysAgo(7)
GROUP BY 1, 2 ORDER BY 1 ASC, c DESC`,
    resultTemplate: (sev) => sev === 'high'
      ? 'Block filter rule denial volume spiking. Possible new scraping campaign.'
      : 'Denial event volume within normal parameters.',
  },
]
