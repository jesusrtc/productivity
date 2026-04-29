# Registration Spike Investigation

**Date:** 2026-04-08 | **Investigator:** Jesus Cortes
**Detection method:** Anomaly Detection using Z-Scores with a Moving Window
**Data partition:** `2026-04-07-00`
**Metric anchor:** `COUNT(*)` from `u_trustim.event_registration`

---

## 1. Spike Confirmed: Two Edge UAs, ~18-21x Baseline

Edge/138 averaged 37/day and spiked to 671 (~18x). Edge/139 averaged 24/day and spiked to 515 (~21x). Combined 1,186 anomalous registrations on a single day vs a baseline of ~60/day.

![Registration Spike by User-Agent](assets/reg_spike_by_useragent.png)

<details><summary>Query</summary>

```sql
SELECT datepartition, useragent, COUNT(*) AS reg_count
FROM u_trustim.event_registration
WHERE datepartition >= '2026-03-24-00' AND datepartition <= '2026-04-07-00'
  AND useragent IN (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0'
  )
GROUP BY datepartition, useragent
ORDER BY datepartition, useragent
```
</details>

---

## 2. Residential Proxy Farm: 280+ IPs Across 52 Countries

This is not a single-IP bot. The operation uses diverse residential IPs across 52+ countries, consistent with a residential proxy network. Top 3 countries (Brazil 173, USA 171, Mexico 164) account for 43% of volume. All IPs show `ip_proxy_type = '?'` (unclassified) — no flagged proxies/VPNs.

| Dimension | Edge/138 | Edge/139 |
|-----------|----------|----------|
| Unique IPs | 194 | 140 |
| Countries | 52 | 42 |
| Email domains | 176 | 112 |
| Unique browsers | 190 | 129 |

Top IPs have 15-36 regs each, from residential ISPs: Cablevision (MX), Claro (BR), Vimpelcom (RU), Charter (US), Vodafone (DE).

![Geographic Distribution](assets/geo_distribution.png)

<details><summary>Query</summary>

```sql
SELECT ip_country, ip_country_code, COUNT(*) AS reg_count
FROM u_trustim.event_registration
WHERE datepartition = '2026-04-07-00'
  AND useragent IN (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0'
  )
GROUP BY ip_country, ip_country_code
ORDER BY reg_count DESC
```
</details>

---

## 3. Two Operational Bursts, Clear Work Schedule

Activity runs in two bursts (00-12 UTC, 17-23 UTC) with near-silence from 13-16 UTC. This pattern suggests an operator with a shift break, or two geographic operating windows. Edge/138 dominates in Burst 2 (17-20 UTC), Edge/139 is more evenly spread.

![Hourly Pattern on Spike Day](assets/hourly_pattern_spike_day.png)

<details><summary>Query</summary>

```sql
SELECT SUBSTR(str_time, 1, 13) AS hour, useragent, COUNT(*) AS reg_count
FROM u_trustim.event_registration
WHERE datepartition = '2026-04-07-00'
  AND useragent IN (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0'
  )
GROUP BY SUBSTR(str_time, 1, 13), useragent
ORDER BY hour, useragent
```
</details>

---

## 4. Auto-Generated Gmail Aliases Confirm Automation

Email domains are overwhelmingly auto-generated patterns: `<spanishname><number>.gmail.com`. Only 28 of 1,186 used plain `gmail.com`. These are not real Gmail subdomains — they're programmatically generated aliases indicating a registration bot.

| Email Domain | Regs |
|-------------|------|
| `jossalgadog001.gmail.com` | 36 |
| `jostorreshh001.gmail.com` | 32 |
| `julgutierrezh001.gmail.com` | 28 |
| `gmail.com` | 28 |
| `frafrances02.gmail.com` | 26 |
| `antcristobal02.gmail.com` | 26 |
| `josrevillae001.gmail.com` | 25 |
| `angblancob02.gmail.com` | 25 |

Pattern: `{3-letter-prefix}{spanish-surname}{suffix}{number}.gmail.com` — clear programmatic naming convention.

<details><summary>Query</summary>

```sql
SELECT email_domain, COUNT(*) AS reg_count
FROM u_trustim.event_registration
WHERE datepartition = '2026-04-07-00'
  AND useragent IN (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0'
  )
GROUP BY email_domain
ORDER BY reg_count DESC
LIMIT 15
```
</details>

---

## 5. Attribution: Email Regex Reveals a Larger Campaign

The Edge UA spike (1,186) is just one fingerprint of a much larger operation. Using regex `^[a-z]{8,}0[0-9]{1,2}\.gmail\.com$` to match the auto-generated email pattern (without assuming Spanish names), we find a campaign ramping from ~120/day on Mar 24 to **12,505/day on Apr 7** — growing 100x in two weeks. The alert only caught the UA signal; the email pattern reveals the true scale.

| Date | Edge 138/139 | Auto-gen Gmail (regex) | Other |
|------|-------------|----------------------|-------|
| 03/24 | 56 | 121 | 804,918 |
| 03/27 | 79 | 2,608 | 794,846 |
| 04/01 | 72 | 3,542 | 850,776 |
| 04/04 | 26 | 5,360 | 701,629 |
| **04/07** | **1,186** | **12,505** | **779,190** |

96% of the Edge UA accounts (1,139/1,186) also match the email regex — confirming it's the same actor. The remaining 12,505 Gmail-pattern accounts use various other UAs.

![Attribution: IOC Cohorts vs Other](assets/attribution_ioc_vs_other.png)

<details><summary>Query</summary>

```sql
SELECT datepartition,
  CASE
    WHEN useragent IN (
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0'
    ) THEN 'IOC: Edge 138/139'
    WHEN REGEXP_LIKE(email_domain, '^[a-z]{8,}0[0-9]{1,2}\.gmail\.com$')
      THEN 'IOC: auto-gen Gmail (long prefix)'
    ELSE 'Other'
  END AS cohort,
  COUNT(*) AS reg_count
FROM u_trustim.event_registration
WHERE datepartition >= '2026-03-24-00' AND datepartition <= '2026-04-07-00'
GROUP BY 1, 2
ORDER BY 1, 2
```
</details>

---

## 6. Registration Flow: Email-Based via Authwall, No SSO

All 1,186 accounts registered through the standard email flow (`handle_type = EMAIL`), not Google SSO. The entry point was the **authwall** (`trk=seo-authwall-base`) — these bots were scraping LinkedIn as guests, hit the authwall, and automated the signup flow.

| Signal | Value |
|--------|-------|
| Registration method | 1,183 email-based, 2 phone-based, 1 hosting IP |
| Entry point | `d_registration-create-account` via `seo-authwall-base` |
| CSRF token reuse | 319 unique tokens / 1,186 regs = **3.7 regs per session** |
| Google SSO | **None** (0%) |

The CSRF token reuse (3.7 accounts per token) confirms session batching — the bot registers multiple accounts per browser session before rotating.

<details><summary>Query</summary>

```sql
SELECT e.custom_event, e.custom_description, COUNT(*) AS cnt
FROM u_trustim.event_registration e
JOIN u_trustim.reg_automation_alert_2026_04_07_00 a ON e.memberid = a.memberid
WHERE e.datepartition = '2026-04-07-00'
GROUP BY e.custom_event, e.custom_description
```
</details>

---

## 7. Defense Gap: Models Detected Bots, But Experiment Overrode to "No Challenge"

The models **correctly identified these as high-risk** — scores 0.95-1.0 across all models. But the experiment framework overrode the challenge decision for 37% of score events, setting `challengeType = NONE`.

### Model Scores (all high-risk)
| Model | Score Range | Classification |
|-------|-----------|---------------|
| `registration_model_frame-v16_2` | 0.95 - 1.0 | (no threshold label) |
| `fake_unprevented_autoretrained-v1_2` | 0.96 - 0.99 | **HIGHLY_ABUSIVE** |
| `registration_challenge_difficulty_phone_model` | 0.92 - 0.99 | — |
| `registration_challenge_difficulty_captcha_model` | 0.86 - 0.97 | — |

### Effective Challenge Decision (CURRENT stage)
| Decision | Score Events | Share |
|----------|-------------|-------|
| CAPTCHA / EVERCAPTCHA | 1,347 | 55% |
| **NONE** | **911** | **37%** |
| PHONE | 171 | 7% |

**Root cause:** The activated rules reveal two issues:
1. **Experiment contamination:** The rule `All sign-up challenge experiment: No Challenge variant` is a lix A/B test with a "No Challenge" arm. Bot registrations landing in this variant get **zero friction**.
2. **Model-to-rule gap:** Even when `registration_model_frame-v16_2` scored 0.99, some rules set `EXPERIMENTATION_FRAMEWORK: set challengeType NONE` — the experiment framework overriding the model's risk signal.

### Post-Challenge: EMAIL_PIN Unsolved by 98.6%

For accounts that did get past scoring, the only challenge served was EMAIL_PIN (not CAPTCHA). 1,110 email pin challenges were created, but only **15 were solved (1.4%)**.

| Challenge | Created | Solved | Solve Rate |
|-----------|---------|--------|------------|
| EMAIL_PIN_CHALLENGE | 1,110 | 15 | **1.4%** |
| PIN_CHALLENGE | 6 | 6 | 100% |
| CAPTCHA | **0 served** | — | — |

**The defense gap is the experiment, not the models.** The models saw these bots clearly (0.95+). The "No Challenge" lix variant needs to exclude high-risk registrations, or the experiment should be paused for traffic scoring above a threshold.

<details><summary>Queries</summary>

```sql
-- Model scores
SELECT m.name, m.classification, ROUND(m.score, 2) AS score_bucket, COUNT(*) AS cnt
FROM tracking.scoreeventforregistration s
CROSS JOIN UNNEST(s.modelresults) AS t(m)
WHERE s.datepartition = '2026-04-07-00'
  AND s.requestheader.useragent IN (...)
  AND s.scorerstage = 'CURRENT'
GROUP BY 1, 2, 3 ORDER BY cnt DESC

-- Effective challenge decisions
SELECT CASE
    WHEN ARRAY_JOIN(s.activatedrules, '|') LIKE '%set challengeType NONE%'
      OR ARRAY_JOIN(s.activatedrules, '|') LIKE '%set NONE from%' THEN 'NONE'
    WHEN ARRAY_JOIN(s.activatedrules, '|') LIKE '%CAPTCHA%'
      OR ARRAY_JOIN(s.activatedrules, '|') LIKE '%EVERCAPTCHA%' THEN 'CAPTCHA/EVERCAPTCHA'
    WHEN ARRAY_JOIN(s.activatedrules, '|') LIKE '%PHONE%' THEN 'PHONE'
    ELSE 'OTHER'
  END AS effective_challenge, COUNT(*) AS cnt
FROM tracking.scoreeventforregistration s
WHERE s.datepartition = '2026-04-07-00'
  AND s.requestheader.useragent IN (...)
  AND s.scorerstage = 'CURRENT'
GROUP BY 1

-- Challenge events
SELECT c.eventtype, c.challengetype, c.validationresult, COUNT(*) AS cnt
FROM tracking.securitychallengeevent c
JOIN u_trustim.reg_automation_alert_2026_04_07_00 a ON c.header.memberid = a.memberid
WHERE c.datepartition = '2026-04-07-00'
GROUP BY 1, 2, 3 ORDER BY cnt DESC
```
</details>

---

## 8. Post-Reg Impact: Well Contained, Median TTR 1.2 Hours

96.2% restricted. Median time-to-restrict is **1.2 hours**, mean 1.5 hours. A fast-restriction cohort (176 accounts) was caught at ~12 minutes — likely a batch restriction pipeline. 90% were restricted within 4 hours. 45 remain unrestricted.

| Signal | Result |
|--------|--------|
| **Restricted** | 1,141/1,186 (**96.2%**) |
| **Median TTR** | **1.2 hours** |
| **90th pctl TTR** | **4.0 hours** |
| **Fast batch** | 176 accounts restricted at ~12 min |
| **Unrestricted** | 45 accounts still active |
| **DIHE contribution** | **0** — no harmful experiences generated |
| **Scraping labels** | **0** — inconclusive (accounts <1 day old, Ultrascrapper has ~30 day lag) |
| **Email confirmed** | ~15/1,186 (1.3%) — virtually none confirmed email |

| Time Bucket | Accounts | Share |
|-------------|----------|-------|
| < 1 hour | 436 | 36.8% |
| 1-6 hours | 703 | 59.3% |
| 6-24 hours | 1 | 0.1% |
| Not restricted | 45 | 3.8% |

![Restriction Time Distribution](assets/restriction_time_distribution.png)

![Cumulative Restriction Curve](assets/cumulative_restriction_curve.png)

The accounts were restricted before they could cause downstream harm. Zero DIHE means no victims were impacted. The 45 unrestricted accounts should be reviewed.

---

## 9. Data Egress: API-Based Scraping, Zero Scraping Labels

Using the earlier campaign wave (586 accounts registered Mar 27 - Apr 5 with the same Edge UAs) on the `2026-04-05-00` egress partition:

**Coverage:** Only **46/586 (7.9%)** have any egress data. The rest were restricted before generating traffic.

| Metric | Value |
|--------|-------|
| Accounts with egress | 46 / 586 (7.9%) |
| Total data egress (URNs) | 51,627 |
| Avg egress per account | ~1,123 URNs |
| Top account egress | 11,661 URNs in 9 days |
| Profile views | Minimal (0-27 per account) |
| **Labeled as scraping** | **0 (0%)** |
| **Scraping label sources** | **None** |
| **Enforced** | **0 (0%)** |

**The scraping pipeline is completely blind to these accounts.** All 46 show `is_scraping = 0`, no label sources, no enforcement. They are flying under the radar.

**API-based, not UI-based:** The accounts show high `total_unique_urns` (thousands) but near-zero `distinct_profile_views`. This means they're pulling data through API endpoints programmatically, not browsing profile pages in a browser. The scraping detection pipeline, which relies on page-level signals, misses this pattern entirely.

**Handle never confirmed:** Correct — 98.6% never solved the EMAIL_PIN challenge. Accounts get logged-in API access without proving email ownership. This is a second defense gap: unconfirmed handles should not have full API access.

<details><summary>Query</summary>

```sql
SELECT eg.is_scraping, eg.is_enforced, eg.trust_member_tier,
       COUNT(DISTINCT eg.member_id) AS members,
       SUM(eg.total_data_egress) AS total_egress,
       SUM(eg.distinct_profile_views) AS profile_views,
       SUM(eg.total_unique_urns) AS unique_urns
FROM u_metrics.scraping_member_data_egress_union eg
JOIN u_trustim.reg_inv_campaign_members_tmp c ON eg.member_id = c.member_id
WHERE eg.datepartition = '2026-04-05-00'
GROUP BY 1, 2, 3
```
</details>

<details><summary>Queries</summary>

```sql
-- Restriction status
SELECT CASE WHEN r.member_id IS NOT NULL THEN 'Restricted' ELSE 'Not Restricted' END AS status, COUNT(*)
FROM u_trustim.reg_automation_alert_2026_04_07_00 a
LEFT JOIN data_derived.member_restrictions r ON CAST(a.memberid AS bigint) = r.member_id
GROUP BY 1

-- DIHE contribution
SELECT COUNT(DISTINCT CASE WHEN fhe.memberid IS NOT NULL THEN a.memberid END) AS contributing_to_dihe
FROM u_trustim.reg_automation_alert_2026_04_07_00 a
LEFT JOIN u_trustim.flatten_harmful_experiences fhe
  ON CAST(a.memberid AS bigint) = fhe.memberid
  AND fhe.datepartition >= '2026-04-07-00' AND fhe.datepartition <= '2026-04-08-00'
```
</details>

---

## 9. Next Steps

- [ ] Profile the broader Gmail-pattern campaign (12,505 accounts on Apr 7) — which UAs, same defense gaps?
- [ ] Investigate why CAPTCHA was not served — check model score distribution for these registrations
- [ ] Review the 45 unrestricted accounts — restrict or add to watchlist
- [ ] Recommend email domain regex as a blocking signal at registration
- [ ] Assess severity (low DIHE impact but growing campaign volume)

---

## Appendix

### Tables Used
| Table | Purpose |
|-------|---------|
| `u_trustim.event_registration` | Registration events with UA, IP, geo, email, timestamps |
| `u_trustim.reg_automation_alert_2026_04_07_00` | Alert member list (1,186 member IDs) |
| `tracking.securitychallengeevent` | Challenge events (type, result, solve rate) |
| `tracking.scoreeventforregistration` | Registration scoring decisions |
| `data_derived.member_restrictions` | Member restriction status |
| `u_trustim.flatten_harmful_experiences` | DIHE abuser/victim join |
| `u_metrics.scraping_member_labels_union` | Scraping labels (inconclusive for <30d accounts) |

### References
- Alert source: Z-Score anomaly detection pipeline, partition `2026-04-07-00`
