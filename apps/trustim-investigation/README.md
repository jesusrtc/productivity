# trustim-investigation

Skills and tools for Trust/Safety IR investigation during oncall, leveraging Trino queries, im_playbooks, and DAVI widgets.

## Overview

Claude Code investigation plugin for the TrustIM team's oncall and IR workflows. Enables structured investigations across ATO, fake accounts, scraping, login abuse, SEV assessment, and other trust/safety domains.

- **Investigation and action skills** covering the full investigation lifecycle
- **DAVI widget execution** on Darwin pods via `davi_runner.py` — run SevCalculatorWidget, DiheWidget, charts, and more
- **Notebook audit trail** — every query and widget output auto-saved to `.ipynb` for review
- **Google Docs output** — investigation reports published via `publish-audit-trail`
- **40+ incident families** enriched — Yellowfish, GhostLock, ShadowFlux, Golden Grouper, Silver Herring, and more

## Getting Started

### 1. Install the plugin

```bash
# Clone the repo
mint checkout trustim-investigation

# Symlink as a Claude Code plugin
ln -s /path/to/trustim-investigation ~/.claude/plugins/trustim-investigation
```

Once installed, all skills are automatically available. Claude will select the appropriate skill based on your prompt.

### 2. Set up Darwin execution (one-time)

Required for DAVI widgets, Python execution, and notebook audit trails:

```bash
python3 tools/davi_runner.py setup
```

This clones `lipy-darwin-local-client`, creates a Python 3.12 venv, installs dependencies, and registers a Jupyter kernel. Only needs to run once (or after a reboot clears `/tmp`).

### 3. Start investigating

```
"Investigate alert 249973199 — anomalous spike in registrations on 2026-03-18"
```

Claude will use the relevant skills, run Trino queries, execute DAVI widgets, and produce a Google Doc report with a notebook audit trail.

## How to Use This MP

### Investigation Workflow

1. **Alert fires** → start with `oncall-triage` for member lookups and initial assessment
2. **Assess severity** → use `sev-assessment` to determine SEV level (True North or cohort-based)
3. **Route to investigation skill** based on attack type:
   - ATO self-report / member report spike → `account-takeover`
   - FA member report spike → `fake-account-research`
   - Registration volume spike → `suspicious-registrations`
   - Login QPS spike → `login-analysis`
   - Scraping spike → `scraping-investigation`
   - Messaging / invitation abuse → `messaging-abuse`
   - Challenge / phone abuse → `challenge-research`
4. **Start Darwin session** (if DAVI widgets needed) → `davi-runner` skill (`setup` → `start`)
5. **Deep-dive** using SQL templates (via Trino MCP) and DAVI widgets (via `davi-runner`)
   - Always use `--notebook alert-{ID}-{type}-{date}` for audit trail
6. **Mitigate** via rule tuning (`rule-tuning`) or ASTA mass actions
7. **Publish audit trail** → Google Doc via `publish-audit-trail`, notebook saved to `notebooks/`
8. **Track** the incident in InResponse (`ir-cli`)

### Example Prompts

```
# Full investigation with audit trail
"Investigate alert 249973199 — registration spike with spoofed Android UAs and clickregistration.lat domain"

# SEV assessment
"Compute the WoW T7D change for ATO self-reports and determine the SEV level"

# DAVI widget analysis
"Run DiheWidget for fake accounts over the last 7 days, save to notebook"

# Specific investigation
"Check top email domains and IP coordination for registrations from Turkey on 2026-03-18"

# Oncall triage
"Look up member 123456789 — check restriction status, handles, and recent login activity"

# Build an alerting playbook notebook
"Create a playbook notebook that detects spoofed Android UA registration spikes — include the detection query, thresholds, and a SurfaceVisualizationWidget chart"
```

Playbook notebooks are saved to `notebooks/` and can be uploaded to Darwin for scheduled execution, similar to `im_playbooks`.

### Capabilities

**Data access — Trino** (via `execute_trino_query` MCP tool):
- Run all SQL templates in every skill directly against holdem Trino
- Compute WoW T7D changes, baseline gates, SEV assignments
- Member lookups, restriction checks, fanout analysis

**Data access — Darwin** (via `tools/davi_runner.py`):
- Execute DAVI widgets (SevCalculatorWidget, DiheWidget, MagicPlotWidget, SurfaceVisualizationWidget, AlertPlotWidget)
- Run arbitrary Python on Darwin pods (pandas, numpy, trino, etc.)
- Execute `%%sql` magic for interactive Trino queries on Darwin
- Render Plotly charts and HTML widget output (returned as structured JSON)

**Investigation output:**
- Google Docs reports via `publish-audit-trail` skill
- Jupyter notebook audit trail via `--notebook` flag (saved to `notebooks/`, gitignored)
- All queries, results, widget renders, and charts preserved for review

**Cannot do:**
- Mass restrictions or ASTA actions (requires InResponse / manual approval)
- Write to InResponse (read-only via `ir-cli`)
- Interactive widget controls (clipboard, email — static renders only)

## Skills

### Investigation Skills

| Skill | Description |
|-------|-------------|
| `sev-assessment` | SEV 1-4 assessment — True North thresholds (Table 1), cohort-based DIHE/scraping thresholds (Table 2), SEV modifiers, merge rules, SevCalculatorWidget |
| `account-takeover` | ATO investigation — MITM/phishing (Evilginx, Golden Grouper, Silver Herring), 3P login abuse (Google/FB/MSFT), OTP bypass, session hijack, credential washing, scorer failure detection, ASTA patterns |
| `login-analysis` | Login events, list washing attacks (OAuth MSFT, reg/login unified, OTP flow), scorer failure detection, Drools salience pitfalls, 2FA, Ghost Lock |
| `fake-account-research` | 3P ID reuse (Google/Facebook thirdpartyuserid), LWP abuse (Chrome 102 spoofed UA), WEV domain abuse, close/reactivate, bcookie fanout, FA DIHE |
| `suspicious-registrations` | Registration attacks, email/IP pattern analysis, score discrepancies, cookie signals, coordinated signup detection |
| `challenge-research` | VoIP phone abuse (Telesign carrier denylist), IRSF detection, SMS cost awareness, captcha, email pin, SSP/SHC, IDV |
| `scraping-investigation` | Guest/member scraping, logged-in scraping pipeline (BECDT, voyager API), block filter rules, alert thresholds, FPR checks |
| `messaging-abuse` | Groups messaging abuse (FrostGuard), invitation spam, mass messaging, inter-message timing detection |
| `rule-tuning` | FPR/UMI calculation, Laser-to-Quasar migration, Fake Romance patterns (IP orgs, AMCVS cookies), rule generation workflow |
| `oncall-triage` | Member lookups, restrictions, appeals, incident metrics, playbook alert thresholds |
| `sn-abuse` | Sales Navigator abuse, free trial detection, recruiter ATO |
| `abi-abuse` | Addressbook Import abuse, bulk invitations |
| `site-anomaly` | QPS analysis, site speed, traffic patterns |
| `common-reference` | 75+ table reference, UDFs, im_playbooks library, investigation tools, headless accounts, DAVI widget index |
| `domain-investigation` | Email domain risk analysis — MX records, disposable domain detection, domain-to-registration correlation |
| `ir-cli` | InResponse CLI (`ir`) — alerts, incidents, comments, timelines (dynamically pulls from trustim-ir-cli repo) |
| `publish-audit-trail` | Publish investigation findings to Google Doc in TrustIM Investigations folder, update master tracking document |
| `davi-runner` | Execute DAVI widgets on Darwin pods — manages proxy, kernel, connection lifecycle, notebook audit trail |
| `playbook-creation` | Guidelines for creating alert and triage playbooks following im_playbooks conventions — cell structure, statistical methods, IRIS integration |
| `writing-humanizer` | Transforms and humanizes writing for reports, conclusions, and external-facing text. Removes fluff, avoids AI cliches, enforces clear and conversational tone |

### Action Skills

SQL query templates used by investigation skills:

| Action | Description |
|--------|-------------|
| `account-activity` | 2FA opt-in, self-report correlation |
| `challenge-events` | Challenge volume, solve rates, IDV funnel |
| `device-fingerprint` | Canvas hash clustering, phishing IP fanout |
| `domain-investigation` | Email domain queries — MX lookup, disposable detection, registration correlation |
| `invitation-scoring` | Invitation delay rule, counter analysis |
| `login-events` | IP washing, login correlation |
| `login-score-events` | MITM detection, credential washing, counter analysis |
| `member-lookup` | Member profile, restriction status |
| `registration-events` | Email domain detection, IP coordination, cookie signals |
| `rule-performance` | Rule trigger volume, FPR/UMI calculation |
| `scraping-events` | Block filter rules, denial events, FPR checks |
| `site-traffic` | QPS by hour, top denied IPs |
| `sn-seats` | SN contract fanout, seat lookup |

## Tools

### `tools/davi_runner.py` — Darwin Notebook Execution

CLI tool that bridges Claude Code to Darwin pods for DAVI widget execution. Manages the full lifecycle: proxy, kernel, Darwin connection, code execution, and notebook audit trail.

```bash
python3 tools/davi_runner.py setup                                    # One-time: clone darwin-local-client, venv, deps
python3 tools/davi_runner.py start                                    # Start proxy + kernel + connect to Darwin
python3 tools/davi_runner.py run "<code>" --notebook <name>           # Execute on Darwin, save to notebook
python3 tools/davi_runner.py stop                                     # Disconnect and stop
```

**Notebook audit trail:** Every `run` call with `--notebook NAME` appends a timestamped code cell with full outputs to `notebooks/<NAME>.ipynb`. Notebooks are gitignored (contain sensitive investigation data) and can be opened in VS Code or Jupyter for review.

See the `davi-runner` skill for full documentation.

## DAVI Widget Integration

Seven investigation skills reference DAVI widgets. Widgets can be executed directly via `davi_runner.py` on Darwin pods. See `common-reference` for the full widget index.

| Widget | Status | Skills | Use Case |
|--------|--------|--------|----------|
| `SevCalculatorWidget` | Tested | sev-assessment, account-takeover, fake-account-research, scraping-investigation | Automated cohort SEV assessment (DIHE + scraping) |
| `DiheWidget` | Tested | account-takeover, fake-account-research | DIHE analysis by account type (fake/ATO) |
| `MagicPlotWidget` | Tested | common-reference | Auto-plot DataFrames (line, bar, scatter, area) |
| `SurfaceVisualizationWidget` | Tested | fake-account-research, suspicious-registrations | Registration traffic with NL filtering |
| `AlertPlotWidget` | Tested | common-reference | Alert visualization (WoW, IQR, z-score) |
| `IPActivityWidget` | Blocked (gr003155) | account-takeover, login-analysis, scraping-investigation | IP/search pivot from MIDs or IPs |
| `KeywordsAnalysisWidget` | Blocked (gr003155) | messaging-abuse, scraping-investigation | Keyword-based search investigation |
| `SearchTermRankingWidget` | Blocked (gr003155) | messaging-abuse, scraping-investigation | Search term ranking by MIDs |
| `CaptainScrapingWidget` | Untested | scraping-investigation | Per-member scraping pattern analysis (InVizor) |

## Historical Incident Coverage

Skills are enriched with investigation techniques, detection signals, and IoCs from these incident families:

| Incident Family | Skills Enriched | Key Techniques Added |
|----------------|-----------------|---------------------|
| Yellowfish / ColorFish | account-takeover | Evilginx X-Evilginx header, smart link investigation, limsg CLI, time-to-first-message benchmarks |
| Golden Grouper | account-takeover | Human-controlled MiTM, 2FA timing >30s detection, recruiter phishing domains |
| Silver Herring | account-takeover | VM-based MiTM, WebGL renderer regex, Frame_deviceIdSet parsing |
| ShadowFlux | account-takeover, fake-account-research | 3P ID reuse (Google/FB/MSFT), close/reactivate abuse, VoIP 2FA enrollment |
| GhostLock | account-takeover, login-analysis | Scorer failure detection (5 modes), LE-SE join gap, 4 known bad UAs, li/track signal |
| OTP/List Washing | login-analysis | OAuth MSFT endpoint, reg/login unified, timing side-channel, 3-tier mitigation |
| LWP Prevalence | fake-account-research | Chrome 102 spoofed UA, loginWithProfile param, WEV domain abuse |
| FrostGuard | messaging-abuse | Groups messaging 50% abuse rate, 9s inter-message timing |
| IRSF | challenge-research | Restricted account SMS bug, 0% completion detection, geo pricing tiers |

## Trino Access

All queries run on the **holdem** server. Common headless accounts:
- `trustim` — general investigation
- `ir2ato` — ATO investigation
- `ir2fake` — fake account investigation
- `ir2scraping` — scraping investigation
- `login` — login analysis
- `fakeacct` — full member investigation

Partition format: `YYYY-MM-DD-00` (US Pacific time)

## Support

- Crew: 567 (TrustIM)
- Team: styang, jcortes, sbasole, adarki
