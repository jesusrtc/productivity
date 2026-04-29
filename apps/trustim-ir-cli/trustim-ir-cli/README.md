# ir — CLI for InResponse

A command-line interface for InResponse (airp-web), modeled after GitHub's `gh` CLI.

## Install

```bash
cd ir-cli
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

This gives you the `ir` command.

## Quick Start

```bash
ir config --env stg        # Set environment (stg or prod)
ir auth login              # Opens browser, paste cookies
ir alert list              # List alerts
ir incident view 12345     # View incident details
```

## mTLS Authentication (Trust Bridge)

LinkedIn internal services use Trust Bridge, which requires **mutual TLS (mTLS)**. The server asks for a client certificate during the TLS handshake. Browsers present this automatically from the macOS keychain; the CLI does the same via `NSURLSession`.

### How it works

On macOS, `ir` uses the native `NSURLSession` networking stack, which can access client certificates in your keychain — the same ones your browser uses. No certificate export is needed.

### Certificate auto-detection

By default, `ir` matches your system username (`os.getlogin()`) against keychain certificate subject names. For most users, this just works — your corporate cert is typically named after your LDAP (e.g., `afernand`).

### First-time setup

1. **Verify your cert is visible:**

   ```bash
   ir config --list-certs
   ```

   You should see your LDAP username with `<- auto-detected`:

   ```
   Available mTLS client certificates:

     localhost
     cad61bdc-2c2b-41de-8c54-7fd033a29678-MDMIdentity
     jdoe  <- auto-detected

   Using: jdoe (auto-detected from system username)
   ```

2. **If auto-detection picks the wrong cert**, set it explicitly:

   ```bash
   ir config --cert jdoe
   ```

3. **If your cert doesn't appear**, check that:
   - You're on VPN
   - Your corporate certificate is installed (check Keychain Access.app under "My Certificates")
   - You're on a managed Mac with the MDM profile installed

### Non-macOS / fallback

On Linux or if `pyobjc` is not installed, `ir` falls back to Python `requests` without mTLS. This works if Trust Bridge is not required (e.g., local dev) or if you configure a proxy that handles mTLS.

## Cookie Authentication

After mTLS, you still need session cookies for airp-web itself.

```bash
ir auth login
```

This opens `https://airp.stg.linkedin.com/html/cli` in your browser. Copy the full cookie string from the Network tab in DevTools (not the textarea on the page):

1. Open DevTools (F12) -> Network tab
2. Load any airp-web page
3. Click the request -> Headers -> Request Headers -> Cookie
4. Copy the full value
5. Paste into the CLI prompt

Cookies are stored per-environment in `~/.config/ir/config.toml`.

```bash
ir auth status   # Check current auth state
ir auth logout   # Clear stored cookies
```

## Environment Configuration

```bash
ir config --env stg      # Staging (default)
ir config --env prod     # Production
ir config --env ei       # Alias for stg
ir config                # Interactive arrow-key selector
```

Auth cookies are stored separately per environment — you can be logged into both stg and prod.

## Commands

### Alerts

```bash
ir alert list [--page N] [--per-page N] [--json]
ir alert view <id> [--json]
ir alert edit <id> [--title ...] [--status ...] [--owner ...] [--pre-triage-sev ...]
ir alert dismiss <id> [--reason FALSE_POSITIVE|DUPLICATE|...]
ir alert undismiss <id>
ir alert promote <id> [--case-type incident|tpd_case]
ir alert attach <id> --incident-id <inc_id>
ir alert detach <id>
```

### Incidents

```bash
ir incident list [--page N] [--per-page N] [--json]
ir incident view <id> [--json]
ir incident edit <id> [--title ...] [--status ...] [--owner ...] [--pre-triage-sev ...] [--post-triage-sev ...]
ir incident link <id> --incident-ids 1,2,3 [--primary 1] [--title "group name"]
ir incident unlink <id>
```

### Comments

```bash
ir incident comment add <id> [--content "..."]
ir incident comment edit <id> <comment_id> [--content "..."]
ir incident comment delete <id> <comment_id>
```

### Timeline

```bash
ir incident timeline list <id>
ir incident timeline add <id> --time 2026-03-10T14:00 --event "Status change" [--event-type Status] [--old-value Open] [--new-value Active]
ir incident timeline edit <id> <entry_id> [--time ...] [--event ...] [--old-value ...] [--new-value ...]
ir incident timeline delete <id> <entry_id>
```

### Undo

Every write command saves undo data. Revert the last change:

```bash
ir undo
```

### Help

Fetch enum reference values from the server:

```bash
ir help
```

## Interactive Mode

Edit commands with no flags enter interactive mode — fetching current values and prompting for each field:

```bash
ir alert edit 12345          # Prompts for each field with current values as defaults
ir incident edit 12345       # Same for incidents
ir incident comment edit 1 2 # Prompts for comment content
```

## JSON Output

All commands support `--json` for scripting:

```bash
ir alert list --json | jq '.[0].ID'
ir incident view 12345 --json | jq '.Status'
```

## Examples

### Rename an alert and undo it

```bash
$ ir alert edit 246850712 --title "test 2026-03-13 15:10:33"
Alert #246850712: test 2026-03-13 15:10:33

  Status   AUTO_ASSIGNED
  Owner    kjamthe
  ...

Updated: title: test → test 2026-03-13 15:10:33
Run `ir undo` to revert this change.

$ ir undo
Undoing: POST /html/alerts/246850712/edit
Alert #246850712: test
  ...
Undo applied. title: test 2026-03-13 15:10:33 → test
```

### Rewrite an incident timeline

Clear existing entries and build a new status progression:

```bash
# Check current timeline
$ ir incident timeline list 260391096

# Delete old entries
$ ir incident timeline delete 260391096 76 --yes
$ ir incident timeline delete 260391096 77 --yes

# Add new progression: Triaged on 3/12, Mitigated on 3/13, Completed on 3/13
$ ir incident timeline add 260391096 \
    --time "2026-03-12T09:00" --event "Triaged" \
    --event-type Status --old-value "Open" --new-value "Triaged"

$ ir incident timeline add 260391096 \
    --time "2026-03-13T10:00" --event "Mitigated" \
    --event-type Status --old-value "Triaged" --new-value "Mitigated"

$ ir incident timeline add 260391096 \
    --time "2026-03-13T15:00" --event "Completed" \
    --event-type Status --old-value "Mitigated" --new-value "Completed"

# Verify
$ ir incident timeline list 260391096
  ID  Time                 Timeline Event    Old Value    New Value    Actor
----  -------------------  ----------------  -----------  -----------  --------
  78  2026-03-12 09:00:00  Triaged           Open         Triaged      afernand
  79  2026-03-13 10:00:00  Mitigated         Triaged      Mitigated    afernand
  80  2026-03-13 15:00:00  Completed         Mitigated    Completed    afernand
```

### Bump incident severity

```bash
$ ir incident edit 260391096 --pre-triage-sev SEV3 --post-triage-sev SEV2
Incident #260391096: test

  Pre-Triage Sev   SEV3
  Post-Triage Sev  SEV2
  ...

pre_triage_sev_level: SEV4 → SEV3, post_triage_sev_level: SEV3 → SEV2
Run `ir undo` to revert this change.
```

### Quick list with jq

```bash
# Last 3 alerts, ID and title only
$ ir alert list --per-page 3 --json | jq -r '.[] | "\(.ID)  \(.Title)"'
246850712  test
246339223  Test IR Metric3
246339094  Test IR Metric 2
```

## Config Files

| File | Purpose |
|------|---------|
| `~/.config/ir/config.toml` | Environment, cert name, auth cookies per env |
| `~/.config/ir/last_undo.json` | Last undo action (single, not a stack) |
