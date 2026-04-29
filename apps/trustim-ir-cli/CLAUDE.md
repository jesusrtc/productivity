# trustim-ir-cli

CLI tool for InResponse (airp-web). The command is `ir`.

## Setup

```bash
# Install (if `ir --version` fails)
cd trustim-ir-cli && pip install -e .
pip install pyobjc-framework-CoreServices pyobjc-framework-Security  # macOS mTLS

# Configure
ir config --env stg          # set environment
ir config --list-certs       # verify mTLS cert detected
ir auth login --no-validate  # paste cookies from browser DevTools (Network tab > Cookie header)
ir auth status               # verify
```

**Errors**: "Connection failed" = check VPN + `ir config --list-certs`. "Session expired" = re-run `ir auth login --no-validate`. Wrong cert = `ir config --cert <ldap>`.

## Project Structure

```
trustim-ir-cli/trustim-ir-cli/     # The Python package (MP inner directory)
  src/trustimircli/                 # Source code
    cli.py                          # Root click group, registers all subcommands
    config.py                       # ~/.config/ir/config.toml + cookie storage, env switching
    client.py                       # HTTP via macOS NSURLSession (mTLS) with requests fallback
    parser.py                       # BeautifulSoup HTML -> structured data
    formatter.py                    # Structured data -> terminal tables (tabulate) + JSON
    undo.py                         # Last undo state in ~/.config/ir/last_undo.json
    commands/
      auth.py                       # ir auth login|status|logout
      alert.py                      # ir alert list|view|edit|dismiss|undismiss|promote|attach|detach
      incident.py                   # ir incident list|view|edit|link|unlink
      comment.py                    # ir incident comment add|edit|delete
      timeline.py                   # ir incident timeline list|add|edit|delete
      undo_cmd.py                   # ir undo
      config_cmd.py                 # ir config --env|--cert|--list-certs
    completions/enums.py            # Hardcoded enum values for click.Choice completions
  test/                             # Tests
    fixtures/                       # Sample HTML responses from airp-web
    test_parser.py                  # Parser tests
    test_formatter.py               # Formatter tests
  build.gradle                      # LinkedIn build config (li-python-cli plugin)
  setup.py                          # Entry point: ir = trustimircli.cli:cli
```

## How the CLI Works

1. All airp-web endpoints return HTML (not JSON)
2. `client.py` makes HTTP requests using macOS NSURLSession for mTLS (Trust Bridge requires client certs)
3. `parser.py` parses HTML responses with BeautifulSoup into structured data (tables, key-value pairs, undo forms)
4. `formatter.py` renders structured data as terminal tables or JSON (`--json` flag)
5. Write commands parse undo `<form>` data from responses and save to `last_undo.json`
6. `ir undo` replays the saved form POST

## Server-Side Reference (airp-web)

The HTML endpoints are in the airp-web repo:
- `airpweb/api/html_views.py` — list/detail routes for alerts and incidents
- `airpweb/api/html_alert_views.py` — alert edit/dismiss/undismiss/promote/attach/detach
- `airpweb/api/html_incident_views.py` — incident edit, comments, link/unlink
- `airpweb/api/html_timeline_views.py` — timeline CRUD
- `airpweb/models/enums.py` — all enum values (keep completions/enums.py in sync)

## Key Patterns

- **mTLS**: `client.py` finds the user's keychain cert by matching `os.getlogin()` against cert subjects. Configurable via `ir config --cert`.
- **Auth**: Cookies stored per-environment (stg/prod) in `~/.config/ir/config.toml`.
- **Undo**: Every write response contains a `<form>` with hidden fields for reverting. The CLI parses this and saves it. Only the last action is stored (not a stack).
- **Interactive mode**: Edit commands with no flags GET the edit form first, parse current values, then prompt for each field.
- **Environments**: `stg` and `prod`. `ei` is an alias for `stg`.

## Running Tests

```bash
# In the MP directory
mint build   # or locally: pip install -e . && pytest test/
```

## Adding New Commands

1. Add the command in `commands/`
2. Register it in `cli.py` (or in the parent group like `incident.py`)
3. Use `client.get()` / `client.post()` for HTTP
4. Use `parser.parse_*` to extract data from HTML responses
5. Use `formatter.format_*` for output
6. For write commands: call `parse_undo_form()` and `save_undo()` to enable `ir undo`

## Enum Updates

If airp-web adds new enum values, update `completions/enums.py` to match `airpweb/models/enums.py`.
