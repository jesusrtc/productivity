---
name: domain-investigation
description: >-
  Reusable actions for email domain investigation using trustim-scout. Covers domain lookup,
  email domain full investigation with infrastructure pivoting, batch domain analysis, related
  domain discovery via MX/NS/registrar pivoting, and domain hijacking detection via historical
  WHOIS analysis. Use when investigating suspicious email domains in FA, ATO, or registration
  attack investigations.
allowed-tools: Bash, Read
---

# Domain Investigation: CLI Actions

Reusable CLI actions for domain investigation using the `trustim-scout` tool. Referenced by investigation skills (fake-account-research, account-takeover, suspicious-registrations, domain-investigation) to analyze email domain reputation, discover related domains via infrastructure pivoting, and detect domain hijacking.

**Tool:** `trustim-scout` (install via `mint install trustim-scout`)
**API:** VirusTotal Enterprise (rate limit: 1000 req/min, 12000 req/day)
**Output directory pattern:** `/tmp/trustim-scout-results/{investigation_id}/`

---

## Prerequisites

### Installation

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

### Update to Latest Version

```bash
cd trustim-scout
source venv/bin/activate
git pull
mint install
```

---

## Actions

### Domain Lookup (Basic)

**When to use:** Quick domain reputation check during any investigation. Use as a first pass before committing to full investigation. Returns risk score, VT detection stats, domain age, and registrar info.

**Parameters:**
- `{DOMAIN}` — the email domain to investigate (e.g., `suspicious-mail.com`)

**Command:**
```bash
trustim-scout domain lookup {DOMAIN} --json
```

**Output interpretation:**
| Field | Meaning |
|-------|---------|
| `risk_score` | 0-100 composite risk score |
| `risk_level` | INFO / LOW / MEDIUM / HIGH / CRITICAL |
| `vt_positives` | Number of VT vendors flagging as malicious |
| `domain_age_days` | Days since domain registration |
| `registrar` | Domain registrar name |
| `is_disposable` | True if matches disposable email patterns |

**Example:**
```bash
trustim-scout domain lookup newmail-2026.xyz --json | jq '{risk_score, risk_level, vt_positives, domain_age_days}'
```

---

### Domain Lookup with Historical WHOIS

**When to use:** When you need domain ownership history to detect registrar changes or registration gaps. Use for ATO investigations where email domain compromise is suspected.

**Parameters:**
- `{DOMAIN}` — the email domain to investigate

**Command:**
```bash
trustim-scout domain lookup {DOMAIN} --include-historical --json
```

**Additional output:**
| Field | Meaning |
|-------|---------|
| `whois_history` | Array of historical WHOIS records |
| `registrar_changes` | Number of registrar changes detected |
| `registrant_changes` | Number of ownership changes detected |
| `registration_gaps` | Periods where domain was unregistered |

---

### Email Domain Full Investigation

**When to use:** Comprehensive investigation of a suspicious email domain. Use when:
- A domain appears in a high-volume registration cluster
- Investigating potential ATO via email compromise
- Need to find related domains owned by the same actor
- Want to assess domain hijacking risk

This is the primary action for domain-based attribution and infrastructure analysis.

**Parameters:**
- `{DOMAIN}` — the email domain to investigate
- `{OUTPUT_DIR}` — directory to write output files (default: `/tmp/trustim-scout-results/`)

**Command:**
```bash
# Create output directory with investigation ID
OUTPUT_DIR="/tmp/trustim-scout-results/$(date +%Y%m%d_%H%M%S)_{DOMAIN}"
mkdir -p "$OUTPUT_DIR"

# Run full investigation
trustim-scout investigate email-domain {DOMAIN} -d "$OUTPUT_DIR" --json

# Output files created:
# - {DOMAIN}_full.json          — Complete investigation data
# - {DOMAIN}_discovered_domains.txt — Raw list of related domains (one per line)
# - {DOMAIN}_scored_domains.txt — Scored domains: domain|score|confidence|malicious|pivot_types
# - {DOMAIN}_summary.md         — Human-readable markdown summary
```

**Output files:**

| File | Purpose | Use Case |
|------|---------|----------|
| `*_full.json` | Complete structured investigation data | Parse for follow-up queries, store for attribution |
| `*_discovered_domains.txt` | Raw domain list (up to 1000 domains) | Input for batch analysis, cross-reference with registration data |
| `*_scored_domains.txt` | Scored/ranked domains with malicious indicators | Prioritize domains for investigation |
| `*_summary.md` | Markdown summary with key findings | Quick review, incident documentation |

**Key JSON fields:**

```json
{
  "target_domain": "suspicious-mail.com",
  "investigation_time": "2026-03-13T10:30:00Z",
  
  "domain_info": {
    "risk_score": 78,
    "risk_level": "HIGH",
    "vt_positives": 3,
    "domain_age_days": 5,
    "registrar": "NameCheap Inc.",
    "is_malicious": true
  },
  
  "fingerprint": {
    "mx_servers": ["mx1.suspicious-host.com"],
    "ns_servers": ["ns1.attacker-ns.net", "ns2.attacker-ns.net"],
    "registrar": "NameCheap Inc.",
    "jarm_hash": "29d29d00029d29d00042d42d000000...",
    "ssl_issuer": "Let's Encrypt"
  },
  
  "hijack_indicators": [
    {
      "indicator_type": "registration_gap",
      "severity": "HIGH",
      "description": "Domain was unregistered for 45 days before re-registration",
      "gap_start": "2026-01-15",
      "gap_end": "2026-03-01"
    }
  ],
  "hijack_risk_level": "CRITICAL",
  
  "all_discovered_domains": ["domain1.com", "domain2.com", ...],
  "total_discovered": 47,
  
  "related_domains": [
    {
      "domain": "another-suspicious.com",
      "similarity_score": 0.92,
      "confidence": "HIGH",
      "is_malicious": true,
      "pivot_types": ["mx", "ns"],
      "shared_infrastructure": {
        "mx": ["mx1.suspicious-host.com"],
        "ns": ["ns1.attacker-ns.net"]
      }
    }
  ],
  "total_related_found": 12,
  "malicious_related_count": 5,
  "infrastructure_risk_level": "CRITICAL",
  
  "key_findings": [
    "Domain registered 5 days ago",
    "Shares MX server with 12 other domains",
    "5 related domains flagged malicious by VT",
    "Domain shows hijacking indicators (registration gap)"
  ],
  
  "recommended_actions": [
    "Block accounts using this email domain",
    "Investigate related domains for additional accounts",
    "For ATO: treat all accounts on this domain as potentially compromised"
  ]
}
```

---

### Batch Domain Analysis

**When to use:** Analyze multiple domains from a list. Use after:
- Running "High-Volume Email Domain Detection" query and getting top domains
- Discovering related domains from a full investigation
- Having a list of domains from a coordinated attack cluster

**Parameters:**
- `{INPUT_FILE}` — file containing domains (one per line)
- `{OUTPUT_FILE}` — JSON output file

**Command:**
```bash
# Analyze multiple domains (basic lookup for each)
trustim-scout domain analyze --file {INPUT_FILE} --output {OUTPUT_FILE}

# Or for full investigation of each domain (more comprehensive, slower)
trustim-scout investigate batch -f {INPUT_FILE} -o {OUTPUT_FILE}
```

**Input file format:**
```
suspicious-mail.com
newmail-2026.xyz
signup-verify.top
```

**Output:**
JSON array with investigation results for each domain. Use `jq` to filter:

```bash
# Find all domains with risk_score > 70
cat {OUTPUT_FILE} | jq '[.[] | select(.risk_score > 70)]'

# Find all malicious domains
cat {OUTPUT_FILE} | jq '[.[] | select(.is_malicious == true)] | length'

# Get domains sorted by risk
cat {OUTPUT_FILE} | jq 'sort_by(-.risk_score) | .[0:10] | .[] | {domain, risk_score, vt_positives}'
```

---

### Related Domain Discovery

**When to use:** Find domains sharing infrastructure with a target domain. Use for:
- Actor attribution (same MX/NS = likely same operator)
- Expanding known-bad domain lists
- Identifying campaign infrastructure

This action is part of the full investigation but can be run standalone for quick pivoting.

**Parameters:**
- `{DOMAIN}` — the seed domain to pivot from
- `{PIVOT_TYPE}` — infrastructure type to pivot on: `mx`, `ns`, `registrar`, `jarm`, `asn`, or `all`

**Command:**
```bash
# Full pivot (all infrastructure types)
trustim-scout investigate email-domain {DOMAIN} --json | jq '.all_discovered_domains'

# To filter by pivot type in results
trustim-scout investigate email-domain {DOMAIN} --json | jq '
  .related_domains | 
  [.[] | select(.pivot_types | contains(["mx"]))] |
  .[0:20] | .[] | {domain, similarity_score, pivot_types}
'
```

**Pivot type signal strength:**

| Pivot Type | Signal Strength | Description |
|------------|-----------------|-------------|
| `mx` | Highest | Same mail server — strongest indicator of same operator |
| `ns` | High | Same nameservers — strong shared infrastructure signal |
| `registrar` | Medium | Same registrar (combined with time window) |
| `jarm` | Medium | Same TLS fingerprint — shared hosting/config |
| `asn` | Lower | Same autonomous system — weaker signal, many false positives |

**Example workflow:**
```bash
# 1. Run investigation
trustim-scout investigate email-domain suspicious-mail.com -d /tmp/results/ --json

# 2. Get domains sharing MX server (strongest signal)
cat /tmp/results/suspicious-mail.com_full.json | jq '
  .related_domains | 
  [.[] | select(.pivot_types | contains(["mx"]))]
' > /tmp/results/mx_related.json

# 3. Check how many are malicious
cat /tmp/results/mx_related.json | jq '[.[] | select(.is_malicious == true)] | length'

# 4. Get domain list for cross-reference with LinkedIn data
cat /tmp/results/mx_related.json | jq -r '.[].domain' > /tmp/results/mx_related_domains.txt
```

---

### Domain Hijack Check

**When to use:** Specifically check for domain hijacking indicators when investigating ATO via email compromise. Use when:
- Multiple ATOs share the same email domain
- Victim reports "I didn't request password reset"
- Investigating historical domain ownership

**Parameters:**
- `{DOMAIN}` — the email domain to check for hijacking

**Command:**
```bash
trustim-scout domain lookup {DOMAIN} --include-historical --json | jq '{
  domain: .domain,
  hijack_risk_level: .hijack_risk_level,
  hijack_indicators: .hijack_indicators,
  current_registrar: .registrar,
  domain_age_days: .domain_age_days
}'
```

**Hijack indicator severity:**

| Indicator | Severity | Description | Investigation Action |
|-----------|----------|-------------|---------------------|
| `registration_gap` | HIGH | Domain expired and was re-registered | All accounts using this domain since re-registration are suspect |
| `registrant_change` | HIGH | Ownership transferred to new entity | Verify with original owner; assume compromise |
| `registrar_change` | MEDIUM | Domain moved to different registrar | May be benign; correlate with other signals |
| `ns_change` | MEDIUM | Nameservers completely changed | Check if NS change coincides with attack timeline |
| `privacy_toggle` | LOW | Privacy protection toggled on/off | Weak signal; use only with other indicators |

**Example: ATO email domain hijack detection**
```bash
# Check domain for hijacking
RESULT=$(trustim-scout domain lookup legacy-corp-mail.com --include-historical --json)

# Check hijack risk
echo "$RESULT" | jq '.hijack_risk_level'

# If CRITICAL or HIGH, get details
echo "$RESULT" | jq '.hijack_indicators[] | select(.severity == "HIGH")'

# Get gap dates if registration_gap detected
echo "$RESULT" | jq '.hijack_indicators[] | select(.indicator_type == "registration_gap") | {gap_start, gap_end}'
```

---

### Cross-Reference with LinkedIn Registration Data

**When to use:** After discovering related domains, cross-reference with LinkedIn registration data to find accounts using those domains.

**Parameters:**
- `{DOMAIN_FILE}` — file containing discovered domains (from `*_discovered_domains.txt`)
- `{START_DATE}`, `{END_DATE}` — date range to search

**Workflow:**
```bash
# 1. Get discovered domains from investigation
DOMAINS_FILE="/tmp/trustim-scout-results/suspicious-mail.com_discovered_domains.txt"

# 2. Create temporary table in headless schema with domains
# (This is a Trino query pattern, not bash)
```

**Trino query to find registrations using discovered domains:**
```sql
-- Replace {DOMAIN_LIST} with quoted, comma-separated domains from the file
-- Or use a headless schema table if you have many domains

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

---

## Signal Reference

### Risk Score Interpretation

| Score Range | Level | Meaning | Recommended Action |
|-------------|-------|---------|-------------------|
| 0-20 | INFO | No significant signals | No action needed |
| 21-40 | LOW | Minor signals, likely benign | Monitor if volume is high |
| 41-60 | MEDIUM | Some suspicious indicators | Investigate further |
| 61-80 | HIGH | Strong malicious indicators | Consider blocking |
| 81-100 | CRITICAL | Confirmed malicious or high-risk | Block and investigate related domains |

### Key Signals for Investigation Type

**Fake Account Investigation:**
| Signal | Where to Find | Action |
|--------|---------------|--------|
| `domain_age_days < 7` | Domain lookup | New domains in registration spike = strong attack signal |
| `malicious_related_count > 0` | Full investigation | Actor controls other malicious domains |
| `pivot_types: ["mx"]` | Related domains | Same mail server = same operator |
| `registrar: NameCheap/Porkbun/Njalla` | Domain lookup | High-risk registrars often used in attacks |

**ATO Investigation:**
| Signal | Where to Find | Action |
|--------|---------------|--------|
| `hijack_risk_level: CRITICAL` | Full investigation | Domain was hijacked; all accounts compromised |
| `registration_gap` | Hijack indicators | Domain expired and re-registered by attacker |
| `registrant_change` | Hijack indicators | Ownership transferred; verify legitimacy |
| `ns_change` coinciding with ATO timeline | Hijack indicators | Attacker took control of DNS |

**Registration Attack Investigation:**
| Signal | Where to Find | Action |
|--------|---------------|--------|
| `is_disposable: true` | Domain lookup | Throwaway domain; block immediately |
| `risk_level: HIGH/CRITICAL` | Domain lookup | Known malicious domain |
| `total_discovered > 20` | Full investigation | Actor has large infrastructure |
| Cluster of domains same `registrar` + `registration_date` | Batch analysis | Coordinated domain registration |

---

## Tips

- **Rate limits**: trustim-scout handles rate limiting internally (1000 req/min). For batch operations with >500 domains, consider splitting into multiple runs.
- **Caching**: Results are cached for 24 hours. To force refresh, use `--no-cache` flag.
- **Output directory**: Always use `-d` flag for full investigations to get structured output files for follow-up analysis.
- **jq patterns**: Use `jq` for parsing JSON output. Key patterns:
  - Filter by risk: `jq '[.[] | select(.risk_score > 70)]'`
  - Get domain list: `jq -r '.[].domain'`
  - Count malicious: `jq '[.[] | select(.is_malicious == true)] | length'`
- **Cross-reference**: After discovering related domains, always cross-reference with LinkedIn registration/login data to find actual accounts.
- **Attribution**: MX pivot has highest confidence for "same operator" attribution. NS pivot is next. ASN alone is too weak.
- **Hijacking vs New Domain**: For ATO, distinguish between:
  - **Hijacked domain**: `registration_gap` or `registrant_change` → compromised via domain takeover
  - **Attacker-controlled domain**: `domain_age_days < 30` + `is_malicious` → attacker registered new domain
- **Disposable detection**: Domains matching disposable patterns (`.xyz`, `.top`, high-entropy names) are flagged automatically. These are common in bulk FA registration.
- **Enterprise features**: Infrastructure pivoting and VT Intelligence search require Enterprise API. Verify `TRUSTIM_SCOUT_VT_ENTERPRISE=true` is set.

---

## Integration with Other Skills

This action skill is referenced by:

- **fake-account-research**: For email domain clustering and actor attribution
- **account-takeover**: For email domain hijacking detection
- **suspicious-registrations**: For analyzing high-volume email domains
- **domain-investigation** (investigation skill): For standalone domain investigations

When using from other skills, follow this pattern:
1. Identify suspicious email domain(s) from Trino queries
2. Run appropriate domain investigation action
3. Parse output to extract related domains
4. Cross-reference related domains with LinkedIn data
5. Document findings in investigation summary
