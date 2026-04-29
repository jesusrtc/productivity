# Styling and Lint Conventions

## Python

### Linting (flake8)

- Maximum line length: 160 characters (configured in `trustim-investigation/setup.cfg`)

### Type Checking (mypy)

- All functions must have type annotations (`disallow_untyped_defs = true`)
- No implicit Optional (`no_implicit_optional = true`)
- Strict equality checks (`strict_equality = true`)
- No implicit re-exports (`implicit_reexport = false`)
- Warn on redundant casts, unused ignores, unreachable code, and return-any
- Full mypy configuration is in `trustim-investigation/setup.cfg` under `[mypy]`

### Code Style (from `tools/davi_runner.py`)

- Use `pathlib.Path` for all file path operations, not `os.path`
- Prefix private/internal functions with underscore (e.g., `_json_out`, `_ensure_dlc_python`, `_save_pid`)
- Use f-strings for string formatting
- Group imports by standard library, then third-party, then local
- Use docstrings in triple-double-quote format for functions and modules
- Module-level constants in UPPER_SNAKE_CASE

## Markdown (Skill Files)

### YAML Frontmatter

- Every `SKILL.md` must start with YAML frontmatter containing `name`, `description`, and `allowed-tools`
- `description` uses YAML block scalar (`>-`) for multi-line text

### Structure

- Start with an H1 heading matching the skill name
- Include a "How to Use This Skill" section at the top with numbered query construction guidelines
- Use Markdown tables for key tables, parameters, and reference data
- SQL code blocks use the `sql` language tag
- Python code blocks use the `python` language tag
- Bash code blocks use the `bash` language tag

### SQL Templates in Skills

- Parameterize with `{PLACEHOLDER}` syntax (curly braces, UPPER_SNAKE_CASE)
- Include a "When to use" description, "Parameters" list, and "Tables" reference for each named query
- Separate queries with horizontal rules (`---`)
