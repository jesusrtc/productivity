---
name: domain-investigation
description: >-
  Investigate suspicious email domains for reputation, infrastructure relationships, and
  hijacking indicators. Use when analyzing email domains from FA clusters, ATO incidents,
  or registration attacks. Supports actor attribution via infrastructure pivoting and
  domain hijack detection for email compromise investigations.
allowed-tools: Bash, Read
---

# Domain Investigation

## Overview

This skill guides investigation of suspicious email domains encountered during trust investigations. It uses the `trustim-scout` tool to query VirusTotal Enterprise for domain reputation, infrastructure relationships, and historical WHOIS data.

**When to use this skill:**
- Analyst asks to "investigate this email domain"
- FA cluster shows concentration on suspicious/new email domains
- ATO investigation suggests email account compromise
- Registration attack uses domains that need attribution analysis
- Need to find related domains owned by the same actor

**Tool:** `trustim-scout` (install via `mint install trustim-scout`)
---

## Investigation Workflow

### Step 1: Understand the Context

Before running domain investigation, clarify the investigation context:

| Context | Key Questions | Primary Focus |
|---------|---------------|---------------|
| **Fake Account** | What domain(s) are concentrated in the cluster? When did registrations start? | Domain age, infrastructure pivoting, related domains |
| **ATO** | Is email compromise suspected? Did victim report "I didn't request reset"? | Hijacking indicators, registration gaps, ownership changes |
| **Registration Attack** | What domains appeared in the spike? Are they new or established? | Domain age vs attack timeline, disposable detection |
| **Actor Attribution** | Need to link multiple domains to same operator? | MX/NS pivoting, registrar + date clustering |

### Step 2: Prerequisites

```bash
# Clone the repository
mint clone trustim-scout
cd trustim-scout

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install
mint install

# Verify installation
trustim-scout --version
```

To update: `cd trustim-scout && source venv/bin/activate && git pull && mint install`

### Step 3: Choose Investigation Approach

Based on context, select the appropriate approach:

#### 3A: Quick Domain Assessment (Single Domain)

**Use when:** You have one suspicious domain and want a quick reputation check.

**Action:** `domain-investigation` → *Domain Lookup (Basic)*

```bash
trustim-scout domain lookup {DOMAIN} --json
```

**Interpret results:**
- `risk_score > 70` → Likely malicious, proceed to full investigation
- `domain_age_days < 7` + registration spike → Strong attack signal
- `is_disposable: true` → Throwaway domain, likely FA
- `vt_positives > 0` → Flagged by security vendors

#### 3B: Full Domain Investigation (Deep Analysis)

**Use when:** Domain appears suspicious and you need infrastructure analysis, related domains, or hijacking detection.

**Action:** `domain-investigation` → *Email Domain Full Investigation*

```bash
OUTPUT_DIR="/tmp/trustim-scout-results/$(date +%Y%m%d_%H%M%S)_{DOMAIN}"
mkdir -p "$OUTPUT_DIR"
trustim-scout investigate email-domain {DOMAIN} -d "$OUTPUT_DIR" --json
```

**Review output files:**
1. Read `*_summary.md` for quick findings
2. Check `*_full.json` for detailed data
3. Use `*_discovered_domains.txt` for cross-reference with LinkedIn data

#### 3C: Batch Domain Analysis (Multiple Domains)

**Use when:** You have a list of domains from a registration spike or FA cluster.

**Action:** `domain-investigation` → *Batch Domain Analysis*

```bash
# Save domains to file (one per line)
cat > /tmp/domains_to_check.txt << 'EOF'
suspicious-mail.com
newmail-2026.xyz
signup-verify.top
EOF

# Run batch analysis
trustim-scout domain analyze --file /tmp/domains_to_check.txt --output /tmp/batch_results.json

# Find high-risk domains
cat /tmp/batch_results.json | jq '[.[] | select(.risk_score > 70)] | sort_by(-.risk_score)'
```

#### 3D: Hijacking Analysis (ATO Focus)

**Use when:** Investigating ATO where email compromise is suspected.

**Action:** `domain-investigation` → *Domain Hijack Check*

```bash
trustim-scout domain lookup {DOMAIN} --include-historical --json | jq '{
  domain: .domain,
  hijack_risk_level: .hijack_risk_level,
  hijack_indicators: .hijack_indicators,
  domain_age_days: .domain_age_days
}'
```

**Hijack indicators to check:**
- `registration_gap` → Domain expired and re-registered (HIGH severity)
- `registrant_change` → Ownership transferred (HIGH severity)
- `registrar_change` + `ns_change` → Full takeover pattern

---

## Step 4: Interpret Results

### Domain Risk Assessment

| Finding | Interpretation | Recommended Action |
|---------|----------------|-------------------|
| `risk_level: CRITICAL` | Confirmed malicious domain | Block accounts, investigate all users |
| `risk_level: HIGH` + `domain_age_days < 7` | New domain used in attack | Strong FA signal, correlate with registration timeline |
| `hijack_risk_level: CRITICAL` | Domain was hijacked | All accounts since hijack date are potentially compromised |
| `malicious_related_count > 5` | Actor controls multiple bad domains | Large-scale operation, expand investigation |
| `is_disposable: true` | Throwaway domain | Common in bulk FA registration |

### Infrastructure Attribution

When reviewing related domains from full investigation:

| Pivot Type | Confidence | Interpretation |
|------------|------------|----------------|
| Same MX server | Highest | Almost certainly same operator |
| Same NS servers | High | Strong infrastructure link |
| Same registrar + similar date | Medium | Coordinated registration |
| Same JARM hash | Medium | Shared hosting/config |
| Same ASN only | Low | Too many false positives, need additional signals |

**Attribution decision tree:**
```
Domains share MX server?
  └─ YES → Same operator (high confidence)
  └─ NO → Domains share NS servers?
           └─ YES → Same operator (medium-high confidence)
           └─ NO → Same registrar + registered within 7 days?
                    └─ YES → Possibly same operator (medium confidence)
                    └─ NO → Likely unrelated
```

### Hijacking Analysis (ATO)

**Decision tree for email domain hijack:**
```
registration_gap detected?
  └─ YES → Domain was hijacked
           └─ Check gap_start and gap_end dates
           └─ All accounts using domain after gap_end are suspect
  └─ NO → registrant_change detected?
           └─ YES → Ownership transferred
                    └─ Verify if legitimate sale vs hostile takeover
           └─ NO → ns_change detected?
                    └─ YES → DNS takeover possible
                             └─ Check if NS change coincides with ATO timeline
                    └─ NO → Domain likely not hijacked
                             └─ ATO via credential compromise, not domain takeover
```

---

## Step 5: Cross-Reference with LinkedIn Data

After domain investigation, link findings to LinkedIn accounts.

### Find Registrations Using Discovered Domains

**Action:** Use Trino query from `registration-events` skill

```sql
SET SESSION li_authorization_user = 'trustim';

SELECT
  split_part(email, '@', 2) AS email_domain,
  COUNT(*) AS reg_count,
  COUNT(DISTINCT header.memberid) AS distinct_mids,
  MIN(from_unixtime(header.time / 1000)) AS first_reg,
  MAX(from_unixtime(header.time / 1000)) AS last_reg
FROM tracking.registrationevent
WHERE datepartition BETWEEN '{START_DATE}-00' AND '{END_DATE}-00'
  AND split_part(email, '@', 2) IN ({DOMAIN_LIST})
GROUP BY 1
ORDER BY reg_count DESC
```

### Check Restriction Status

```sql
SELECT
  split_part(email, '@', 2) AS email_domain,
  COUNT(*) AS total,
  COUNT(CASE WHEN mr.restrictioninfo IS NOT NULL THEN 1 END) AS restricted
FROM tracking.registrationevent r
LEFT JOIN data_derived.member_restrictions mr ON r.header.memberid = mr.member_id
WHERE r.datepartition BETWEEN '{START_DATE}-00' AND '{END_DATE}-00'
  AND split_part(email, '@', 2) IN ({DOMAIN_LIST})
GROUP BY 1
ORDER BY total DESC
```

---

## Step 6: Document Findings

Structure your findings for incident documentation:

### Fake Account Investigation

```markdown
## Domain Investigation Summary

**Target Domain:** {DOMAIN}
**Investigation Date:** {DATE}

### Domain Profile
- Risk Score: {score}/100 ({level})
- Domain Age: {days} days (registered {date})
- Registrar: {registrar}
- VT Detections: {positives} vendors

### Infrastructure Fingerprint
- MX Servers: {mx_list}
- NS Servers: {ns_list}

### Related Domains
- Total Discovered: {count}
- Malicious: {malicious_count}
- Key related domains: {top_3_domains}

### LinkedIn Impact
- Registrations using this domain: {count}
- Restricted: {restricted_count} ({percent}%)
- Related domains in use: {count}

### Conclusion
{assessment based on findings}

### Recommended Actions
1. {action_1}
2. {action_2}
```

### ATO Investigation

```markdown
## Email Domain Hijack Analysis

**Victim Email Domain:** {DOMAIN}
**Investigation Date:** {DATE}

### Hijack Assessment
- Hijack Risk Level: {level}
- Domain Age: {days} days

### Hijack Indicators
| Indicator | Severity | Details |
|-----------|----------|---------|
| {indicator} | {severity} | {description} |

### Timeline
- Domain originally registered: {date}
- Hijack window: {gap_start} to {gap_end}
- Domain re-registered: {date}

### Impact Assessment
- ATOs potentially via domain hijack: {count}
- Accounts to review: {mid_list or count}

### Conclusion
{assessment: hijacked vs credential compromise vs other}

### Recommended Actions
1. {action_1}
2. {action_2}
```

---

## Common Investigation Scenarios

### Scenario 1: New Domain in FA Registration Spike

**Trigger:** High-volume email domain detection shows `newmail-2026.xyz` with 200 registrations in 24 hours

**Investigation:**
1. Run full investigation: `trustim-scout investigate email-domain newmail-2026.xyz -d /tmp/results/`
2. Check domain age → 3 days old (attack preparation)
3. Check related domains via MX pivot → 15 domains share same MX
4. Cross-reference related domains with LinkedIn → find 800 more accounts
5. **Conclusion:** Coordinated FA campaign using domain cluster

### Scenario 2: ATO Cluster on Corporate Domain

**Trigger:** 30 ATOs in one week, all victims use `@legacy-corp.com` email

**Investigation:**
1. Run hijack check: `trustim-scout domain lookup legacy-corp.com --include-historical --json`
2. Find `registration_gap` indicator → domain expired 2 months ago, re-registered 3 weeks ago
3. Check registrant change → changed from "Legacy Corp Inc" to "Privacy Protect LLC"
4. **Conclusion:** Domain hijack — attacker re-registered expired domain to intercept password resets

### Scenario 3: Actor Attribution Across Multiple Attacks

**Trigger:** Multiple FA waves over 3 months use different domains, want to link to same actor

**Investigation:**
1. List domains from each wave: `wave1.xyz`, `wave2.top`, `wave3.click`
2. Run full investigation on each
3. Find all three share `ns1.attacker-dns.net` nameserver
4. Run related domain discovery → find 50 additional domains on same NS
5. **Conclusion:** Same actor controls all three waves + 50 additional domains

---

## Tips

- **Start with quick lookup** before committing to full investigation (saves API quota)
- **Domain age is critical** — new domains (<7 days) appearing in attacks are strong signals
- **MX pivot is strongest** for attribution — same mail server = same operator
- **Hijack vs credential theft** — registration gap = hijack; no indicators = credential compromise
- **Document timestamps** — correlate domain registration/hijack dates with attack timeline
- **Batch first, investigate deeply second** — when you have many domains, batch analyze to prioritize which deserve full investigation
- **Rate limits** — 1000 req/min, 12000/day; batch operations help stay within limits

---

## Related Skills

- **fake-account-research**: For FA cluster analysis (domain investigation is optional pivot)
- **account-takeover**: For ATO investigation (domain investigation for email compromise)
- **suspicious-registrations**: For registration attack analysis (domain investigation for top domains)
- **actions/domain-investigation**: Reusable CLI actions referenced by this skill
- **actions/registration-events**: Trino queries for cross-referencing domains with LinkedIn data
