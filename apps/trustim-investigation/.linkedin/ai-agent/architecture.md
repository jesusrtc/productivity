# trustim-investigation Architecture

## Purpose

A Claude Code plugin providing investigation and action skills for TrustIM oncall and incident
response workflows. It enables structured trust and safety investigations across account takeover (ATO), fake accounts,
scraping, login abuse, messaging abuse, challenge/phone abuse, and SEV assessment domains. The plugin integrates with
Trino for SQL queries, DAVI widgets on Darwin for notebook-based analysis, and Google Docs for publishing investigation
audit trails.

## Folder Structure

```
trustim-investigation/
├── skills/                          # Claude Code skill definitions (Markdown)
│   ├── account-takeover/            # ATO investigation skill
│   ├── fake-account-research/       # Fake account investigation
│   ├── login-analysis/              # Login events and abuse detection
│   ├── suspicious-registrations/    # Registration attack investigation
│   ├── scraping-investigation/      # Guest/member scraping
│   ├── messaging-abuse/             # Messaging and invitation spam
│   ├── challenge-research/          # VoIP, IRSF, captcha, IDV
│   ├── sev-assessment/              # SEV 1-4 severity framework
│   ├── oncall-triage/               # General oncall triage queries
│   ├── rule-tuning/                 # FPR/UMI rule tuning
│   ├── site-anomaly/                # QPS and traffic patterns
│   ├── sn-abuse/                    # Sales Navigator abuse
│   ├── abi-abuse/                   # Addressbook Import abuse
│   ├── domain-investigation/        # Email domain risk analysis
│   ├── headless-investigation/      # Autonomous investigation from InResponse alerts
│   ├── investigation-report-standards/ # Report language, structure, and quality rules
│   ├── jss-dihe-investigation/      # Job Seeker Safety DIHE/T7D spike investigation
│   ├── payment-investigation/       # Payment abuse cohort investigation
│   ├── telesign-triage/             # Telesign SMS incident triage
│   ├── common-reference/            # Table reference, UDFs, DAVI widget index
│   ├── ir-cli/                      # InResponse CLI integration
│   ├── publish-audit-trail/         # Google Docs report publishing
│   ├── davi-runner/                 # Darwin pod execution management
│   ├── playbook-creation/           # Alerting and triage playbook guidelines
│   ├── writing-humanizer/           # Text humanizer for reports and conclusions
│   └── actions/                     # Reusable SQL query template skills
│       ├── account-activity/        # 2FA, self-report correlation
│       ├── challenge-events/        # Challenge volume and solve rates
│       ├── device-fingerprint/      # Canvas hash, phishing IP fanout
│       ├── domain-investigation/    # Email domain MX/disposable queries
│       ├── invitation-scoring/      # Invitation delay and counter analysis
│       ├── login-events/            # IP washing, login correlation
│       ├── login-score-events/      # MITM, credential washing detection
│       ├── member-lookup/           # Member profile, restriction, appeals
│       ├── registration-events/     # Email/IP coordination, cookie signals
│       ├── rule-performance/        # Rule trigger volume, FPR/UMI
│       ├── scraping-events/         # Block filter rules, denial events
│       ├── site-traffic/            # QPS by hour, top denied IPs
│       └── sn-seats/               # SN contract fanout, seat lookup
├── tools/
│   └── davi_runner.py               # CLI bridge to Darwin pods for DAVI widgets
├── trustim-investigation/           # Python package (li-python-product)
│   ├── src/linkedin/trustiminvestigation/  # Package source
│   ├── test/                        # Python tests
│   ├── setup.py                     # setuptools + GradleDistribution
│   ├── setup.cfg                    # flake8, pytest, mypy, coverage config
│   └── build.gradle                 # li-python-lib plugin config
├── .claude-plugin/
│   └── plugin.json                  # Claude Code plugin manifest
├── acl/
│   └── main.acl                     # Access control list
├── CLAUDE.md                        # Investigation conduct rules for Claude Code
├── README.md                        # Full plugin documentation
├── build.gradle                     # Root Gradle config (li-python-product)
├── settings.gradle                  # Gradle project settings
└── gradle.properties                # Gradle daemon/parallel config
```

## Key Components

### Skills (Markdown-based)

Each skill is a `SKILL.md` file with YAML frontmatter (`name`, `description`, `allowed-tools`) followed by structured
investigation guidance. Investigation skills define the investigative workflow, reference tables, and point to action
skills for reusable SQL templates. Action skills under `skills/actions/` contain parameterized SQL query templates
referenced by name from investigation skills to avoid SQL duplication.

### DAVI Runner (`tools/davi_runner.py`)

A Python CLI tool that bridges Claude Code to Darwin pods via `darwin-local-client`. It manages the full lifecycle:
proxy startup, Jupyter kernel management, Darwin pod connection, code execution (remote or local), and notebook audit
trail. All output is JSON on stdout; progress messages go to stderr. The `--notebook` flag appends timestamped code
cells with outputs to `.ipynb` files in the `notebooks/` directory.

### Investigation Conduct Rules (`CLAUDE.md`)

Defines mandatory rules for all investigations: never assume (ask the user), audit trail requirements (Google Docs +
notebook), query-before-claim (no stating numbers without a query), conversational investigation flow, explicit
uncertainty, and SEV assessment discipline.

### Plugin Manifest (`.claude-plugin/plugin.json`)

Registers the repository as a Claude Code plugin so all skills are automatically available when the plugin is
installed.

## Major Libraries and Tools

- **Trino (holdem server)** -- Primary data access layer; all SQL queries run against holdem with headless account
  authorization
- **Jupyter (jupyter_client, ipykernel, nbformat)** -- Kernel management for Darwin execution and notebook audit trail
  generation
- **darwin-local-client (lipy-darwin-local-client)** -- LinkedIn internal library for connecting to Darwin pods; cloned
  to `/tmp/` during setup
- **DAVI widgets (linkedin.davi.widgets)** -- SevCalculatorWidget, DiheWidget, MagicPlotWidget,
  SurfaceVisualizationWidget, AlertPlotWidget for automated analysis
- **irisclient** -- IRIS incident alerting for automated detection playbooks
- **Gradle (li-python-product, li-python-lib)** -- Build system for the Python package
- **flake8, mypy, pytest** -- Code quality tools configured in `setup.cfg`
- **Captain MCP tools** -- `execute_trino_query`, `unified_context_search`, `search_confluence_content`,
  `read_google_docs_document` for data access and context retrieval
