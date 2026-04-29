---
name: scraping-events
description: >-
  Reusable SQL query actions for scraping investigation. Covers block filter rule volume,
  denial event inspection, scraping funnel correlation, scraping score event analysis,
  member scraping profile lookup, guest scraping FPR check, authwall funnel analysis,
  bot model classification, and scraping FPR confusion matrix.
  Uses tracking.userrequestdenialevent and tracking.scrapingscoreevent as primary tables.
allowed-tools: Bash
---

# Scraping Events: SQL Query Actions

Reusable Trino SQL query templates for scraping investigation. Referenced by the scraping-investigation skill instead of duplicating SQL.

**Trino server:** holdem
**Default headless account:** `ir2scraping` (also `scrapeds`, `trustim`)
**Partition format:** `YYYY-MM-DD-00`

---

## Queries

### Block Filter Rule Volume
**When to use:** Track daily denial event counts for a specific block filter rule. Use to confirm a rule is firing and to see volume trends after a rule deploy.
**Parameters:** `{RULE_NAME}` — the block filter rule name
**Tables:** `tracking.userrequestdenialevent`

```sql
SELECT datepartition,
       denialinfo.blockfilterrulename as rule,
       count(*) as c
FROM tracking.userrequestdenialevent
WHERE datepartition >= daysAgo(7)
  AND denialinfo.blockfilterrulename = '{RULE_NAME}'
GROUP BY 1, 2
ORDER BY 1 ASC
```

---

### Denial Event Detail
**When to use:** Inspect individual denial events for a rule — IP, path, referer, user agent, cookies. Use to understand what traffic a rule is catching and identify patterns.
**Parameters:** `{RULE_NAME}` — the block filter rule name
**Tables:** `tracking.userrequestdenialevent`

```sql
SELECT ip2str(request.ipasbytes) as ip,
       header.treeid, header.time,
       request.path, request.referer, request.useragent,
       request.bcookie, request.cookies
FROM tracking.userrequestdenialevent
WHERE datepartition >= daysAgo(2)
  AND denialinfo.blockfilterrulename = '{RULE_NAME}'
LIMIT 100
```

---

### Scraping Funnel Correlation
**When to use:** Join denial events with the scraping funnel to measure what fraction of denied traffic is actual scrapers vs legitimate users (FPR check for a block filter rule).
**Parameters:** `{RULE_NAME}` — the block filter rule name; adjust `daysAgo(4)` as needed
**Tables:** `tracking.userrequestdenialevent`, `u_metrics.scraping_funnel_union`
**Permission note:** `u_metrics.scraping_funnel_union` has restricted permissions (group `ump003563`). Request access via DataHub.

```sql
SELECT un.isscraping, count(*) as c
FROM tracking.userrequestdenialevent urde
JOIN u_metrics.scraping_funnel_union un
     ON to_base64(urde.header.treeid) = un.treeidbase64
WHERE un.datepartition = daysAgo(4)
  AND urde.datepartition = daysAgo(4)
  AND denialinfo.blockfilterrulename = '{RULE_NAME}'
GROUP BY 1
```

---

### Scraping Score Event Analysis
**When to use:** Analyze scraping scorer decisions by cookie patterns on a specific date. Low `scoringresult = 'ACCEPT'` rate = effective blocking.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking.scrapingscoreevent`

```sql
SELECT array_join(scoringheader.cookienames, ', ') as cookies,
       scoringresult, count(*) as c
FROM tracking.scrapingscoreevent
WHERE datepartition = '{DATE}-00'
  AND scorerStage = 'CURRENT'
  AND whitelisttype IS NULL
  AND requestheader.path LIKE 'in/%'
GROUP BY 1, 2
ORDER BY c DESC
LIMIT 50
```

---

### Member Scraping Profile Lookup
**When to use:** Check scraping classification and activity metrics for specific member IDs. Includes member profile request counts, scraping flags, and restriction status.
**Parameters:** `{MEMBER_IDS}` — comma-separated list of member IDs
**Tables:** `u_metrics.scraping_member_union`

```sql
SELECT memberid, isscraping,
       memberprofilerequests,
       scrapingmemberprofilerequests,
       uniquescrapingmemberprofilerequests,
       uniquememberprofilerequests,
       isinfluencer, ispaying,
       isrestrictedfakeaccount, datepartition
FROM u_metrics.scraping_member_union
WHERE memberid IN ({MEMBER_IDS})
  AND datepartition = daysAgo(1)
```

---

### Guest Scraping FPR Check
**When to use:** Verify the false positive rate for scraping rules on guest (unauthenticated) traffic by joining real-time score events with the scraping funnel labels.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `kafka_streaming.scrapingscoreevent`, `u_metrics.scraping_funnel_union`
**Permission note:** `u_metrics.scraping_funnel_union` has restricted permissions (group `ump003563`). Request access via DataHub.

```sql
SELECT un.isscraping, count(*) as c
FROM kafka_streaming.scrapingscoreevent sse
JOIN u_metrics.scraping_funnel_union un
     ON to_base64(sse.header.treeid) = un.treeidbase64
WHERE un.datepartition = '{DATE}-00'
  AND sse.datepartition = '{DATE}-00'
  AND scorerstage = 'CURRENT'
  AND header.memberid = 0
  AND (requestheader.path like 'in/%' OR requestheader.path like 'company/%'
       OR requestheader.path like 'jobs/%')
  AND (requestheader.referer IS NULL OR length(requestheader.referer) <= 3)
GROUP BY 1
```

---

### Authwall Funnel Analysis
**When to use:** Track guest scrapers redirected to the authwall — how many are redirected to login/registration. Measures scraping-to-authwall conversion.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking.scrapingscoreevent`, `tracking.sentinelredirecttologinpageviewevent`
**Permission note:** `tracking.sentinelredirecttologinpageviewevent` has restricted permissions for `trustim`. Request access via DataHub.

```sql
SELECT datepartition,
       count(*) as total_redirects,
       count(distinct se.requestheader.browserid) as distinct_bcookies
FROM tracking.scrapingscoreevent se
JOIN tracking.sentinelredirecttologinpageviewevent fp
     ON se.header.treeid = fp.deny_id
WHERE se.datepartition = '{DATE}-00'
  AND scoringresult = 'REDIRECT'
  AND concat('[', array_join(scoringheader.cookienames, ', '), ']') IN ('[bcookie, li_gc]', '[bcookie]')
GROUP BY 1
```

---

### Bot Model Classification
**When to use:** Check bot model v2 classification results broken down by IP org. Use to understand what types of traffic (BOT vs HUMAN) are being identified by the ML model.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `kafka_streaming.scrapingscoreevent`

```sql
SELECT ip_org_name(ip2str(requestheader.ipasbytes)) AS ip_org,
       botmodelv2.classification,
       count(*) AS c
FROM kafka_streaming.scrapingscoreevent
CROSS JOIN UNNEST(modelresults) AS t (botmodelv2)
WHERE datepartition = '{DATE}-00'
  AND scoringresult = 'ACCEPT'
  AND requestheader.path LIKE 'in/%'
GROUP BY 1, 2
ORDER BY c DESC
LIMIT 50
```

---

### Scraping FPR Confusion Matrix
**When to use:** Full precision/recall calculation using security label ground truth. Computes TP, FP, TN, FN, and FPR for the scraping scorer on a specific date.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `data_derived.securitylabels_guestscrapinglabelssnapshot`, `kafka_streaming.scrapingscoreevent`

```sql
WITH labels AS (
    SELECT to_base64(treeid) AS treeid, isbot
    FROM data_derived.securitylabels_guestscrapinglabelssnapshot
    WHERE path LIKE 'in/%' AND ismissingvendorlabel != true
),
scores AS (
    SELECT to_base64(header.treeid) AS treeid, scoringresult
    FROM kafka_streaming.scrapingscoreevent
    WHERE datepartition = '{DATE}-00'
      AND requestheader.path LIKE 'in/%'
)
SELECT
  count_if(isbot = true AND scoringresult != 'ACCEPT') as tp,
  count_if(isbot = false AND scoringresult != 'ACCEPT') as fp,
  count_if(isbot = false AND scoringresult = 'ACCEPT') as tn,
  count_if(isbot = true AND scoringresult = 'ACCEPT') as fn,
  round(1.0 * count_if(isbot = false AND scoringresult != 'ACCEPT') /
        (count_if(isbot = false AND scoringresult != 'ACCEPT') + count_if(isbot = false AND scoringresult = 'ACCEPT')), 4) as fpr
FROM labels JOIN scores USING (treeid)
```
