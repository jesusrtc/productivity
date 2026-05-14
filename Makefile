.PHONY: ls install uninstall test test-fast test-all test-slow start stop restart start-bg status pull-repos check-ui setup _stop-quiet _ensure-python

.DEFAULT_GOAL := ls

ls: ## list available make targets
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-][a-zA-Z0-9_-]*:.*##/ {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

LAB_VENV := apps/lab/.venv
SERVER_VENV := apps/server/.venv
BIN_DIR := $(HOME)/.local/bin
PID_FILE := .lab-server.pid
LOG_FILE := .lab-server.log
PORT := 3333
SERVER_CMD_PATTERN := apps/server/.venv/bin/python -m server

# Python bootstrap: we require >=3.11. Preference order (first hit wins):
#   1. Standalone pythons on PATH (python3.13/12/11, then /opt/homebrew/bin/python3)
#   2. A dedicated miniconda env created by `_ensure-python` — NOT base.
# We deliberately skip miniconda base so this project never installs deps
# into the user's base conda env.
CONDA_ENV_NAME    := productivity
CONDA_BASE        := /opt/homebrew/Caskroom/miniconda/base
CONDA_ENV_PYTHON  := $(CONDA_BASE)/envs/$(CONDA_ENV_NAME)/bin/python3

define find_python
for c in python3.13 python3.12 python3.11 /opt/homebrew/bin/python3 $(CONDA_ENV_PYTHON); do \
  if command -v "$$c" >/dev/null 2>&1 || [ -x "$$c" ]; then \
    v=$$("$$c" -c 'import sys; print("%d%02d" % sys.version_info[:2])' 2>/dev/null); \
    if [ -n "$$v" ] && [ "$$v" -ge 311 ]; then echo "$$c"; break; fi; \
  fi; \
done
endef

# Only `setup` depends on this — `install` assumes Python is already ready
# so it stays fast for re-installs. If no compatible Python is on PATH and
# miniconda is installed, create a dedicated env (name: $(CONDA_ENV_NAME)).
_ensure-python:
	@py=$$($(find_python)); \
	if [ -n "$$py" ]; then \
	  echo "Python ready: $$py ($$("$$py" --version))"; \
	  exit 0; \
	fi; \
	if [ -x "$(CONDA_BASE)/bin/conda" ]; then \
	  echo "No standalone Python 3.11+ on PATH — creating miniconda env '$(CONDA_ENV_NAME)' with Python 3.12…"; \
	  "$(CONDA_BASE)/bin/conda" create -y -n $(CONDA_ENV_NAME) python=3.12 >/dev/null; \
	  echo "Created $(CONDA_ENV_PYTHON)"; \
	else \
	  echo "ERROR: need Python 3.11+, and no fallback available."; \
	  echo "  Install a standalone Python:  brew install python@3.12"; \
	  echo "  Or install miniconda:         brew install --cask miniconda"; \
	  echo "                                (then re-run: make setup)"; \
	  exit 1; \
	fi

install: ## create venvs + install lab/lab-server CLIs (requires Python 3.11+; run `make setup` first time)
	@py=$$($(find_python)); \
	if [ -z "$$py" ]; then \
	  echo "ERROR: Python 3.11+ not found."; \
	  echo "       (python3 on PATH: $$(command -v python3 2>/dev/null) — $$(python3 --version 2>&1))"; \
	  echo; \
	  echo "  First-time? Run:   make setup   (auto-creates a miniconda env if you have miniconda)"; \
	  echo "  Or install Python: brew install python@3.12"; \
	  exit 1; \
	fi; \
	echo "Using Python: $$py ($$("$$py" --version))"; \
	mkdir -p $(BIN_DIR); \
	test -d $(LAB_VENV)    || "$$py" -m venv $(LAB_VENV); \
	test -d $(SERVER_VENV) || "$$py" -m venv $(SERVER_VENV)
	@$(LAB_VENV)/bin/pip install -e 'apps/lab[dev]' --quiet
	@ln -sf $(CURDIR)/apps/lab/lab $(BIN_DIR)/lab
	@$(SERVER_VENV)/bin/pip install -e 'apps/lab' --quiet
	@$(SERVER_VENV)/bin/pip install -e 'apps/server[dev]' --quiet
	@ln -sf $(CURDIR)/apps/server/server $(BIN_DIR)/lab-server
	@# `gdiff` stays as a muscle-memory alias pointing at the unified server.
	@ln -sf $(CURDIR)/apps/server/server $(BIN_DIR)/gdiff
	@# darwin-backups, trustim-ir-cli — symlinks only (they have their own dep management)
	@[ -f apps/darwin-backups/darwin-backups ] && ln -sf $(CURDIR)/apps/darwin-backups/darwin-backups $(BIN_DIR)/darwin-backups || true
	@[ -f apps/trustim-ir-cli/trustim-ir-cli ] && ln -sf $(CURDIR)/apps/trustim-ir-cli/trustim-ir-cli $(BIN_DIR)/trustim-ir-cli || true
	@# Clean up legacy shims from the pre-unification layout (incl. retired darwin-runner).
	@rm -f $(BIN_DIR)/lab-backend $(BIN_DIR)/darwin-runner
	@echo "Installed lab, lab-server (aka gdiff) → $(BIN_DIR)/"
	@echo "Ensure $(BIN_DIR) is on your PATH."
	@# Diagnostic: did another `lab` binary win? (Common culprit: miniconda
	@# has its own `lab` that shadows ours.) Tell the user how to fix.
	@resolved=$$(command -v lab 2>/dev/null || true); \
	ours="$(BIN_DIR)/lab"; \
	if [ -n "$$resolved" ] && [ "$$resolved" != "$$ours" ]; then \
		echo; \
		echo "⚠  'lab' resolves to $$resolved (not $$ours)"; \
		echo "   Another tool on your PATH is shadowing us. Fix options:"; \
		echo "     1) put $(BIN_DIR) ahead of the conflict in your shell rc:"; \
		echo "          export PATH=\"$(BIN_DIR):\$$PATH\""; \
		echo "     2) remove the conflicting binary (e.g. miniconda's: pip uninstall -y lab)"; \
		echo "   Escape hatch: invoke $$ours directly, or $(LAB_VENV)/bin/python -m lab ..."; \
	fi

uninstall: ## remove installed binaries and venvs
	@rm -f $(BIN_DIR)/lab $(BIN_DIR)/lab-server $(BIN_DIR)/lab-backend $(BIN_DIR)/gdiff $(BIN_DIR)/darwin-runner $(BIN_DIR)/darwin-backups $(BIN_DIR)/trustim-ir-cli
	@rm -rf $(LAB_VENV) $(SERVER_VENV)
	@echo "Uninstalled."

test: ## run pytest for lab and server (default: skips @slow)
	@$(LAB_VENV)/bin/pytest apps/lab/tests -v && $(SERVER_VENV)/bin/pytest apps/server/tests -v

test-fast: test ## alias for `make test` (skips @slow)

test-slow: ## run only the @slow tests (latency budgets, reconnect storms)
	@$(SERVER_VENV)/bin/pytest apps/server/tests -v -m slow -o "addopts=-ra --cov=server --cov-report=term-missing"

test-all: ## run every test, including @slow (latency budgets, reconnect storms)
	@$(LAB_VENV)/bin/pytest apps/lab/tests -v && \
	 $(SERVER_VENV)/bin/pytest apps/server/tests -v -o "addopts=-ra --cov=server --cov-report=term-missing"

# `_stop-quiet` reliably kills any prior server. We match on the exact module
# invocation so we can never touch other python processes. Only called when
# the user explicitly asks to replace a running server (stop / restart).
_stop-quiet:
	@pkill -TERM -f "$(SERVER_CMD_PATTERN)" 2>/dev/null || true
	@n=0; while pgrep -f "$(SERVER_CMD_PATTERN)" >/dev/null 2>&1 && [ $$n -lt 10 ]; do \
		sleep 0.2; n=$$((n+1)); \
	done
	@pkill -KILL -f "$(SERVER_CMD_PATTERN)" 2>/dev/null || true
	@rm -f $(PID_FILE)

# Foreground mode. No-op (exits 0) if a server is already running so running
# `make start` from a second terminal doesn't nuke the first one. Use
# `make restart` to forcibly replace.
start: ## run server in foreground (port 3333)
	@if pgrep -f "$(SERVER_CMD_PATTERN)" >/dev/null 2>&1; then \
		echo "server is already running (pid $$(pgrep -f "$(SERVER_CMD_PATTERN)" | head -1)) at http://localhost:$(PORT)/"; \
		echo "  - tail:  tail -f $(LOG_FILE)"; \
		echo "  - stop:  make stop"; \
		echo "  - swap:  make restart"; \
		exit 0; \
	elif lsof -nP -iTCP:$(PORT) -sTCP:LISTEN -t >/dev/null 2>&1; then \
		echo "ERROR: port $(PORT) held by another process:"; \
		lsof -nP -iTCP:$(PORT) -sTCP:LISTEN 2>/dev/null | head -5; \
		exit 1; \
	fi; \
	echo "Serving at http://localhost:$(PORT)/   (logs → $(LOG_FILE))"; \
	$(SERVER_VENV)/bin/python -m server 2>&1 | tee $(LOG_FILE)

# Background mode. Same "already-running" guard as foreground.
start-bg: ## run server in background (port 3333)
	@if pgrep -f "$(SERVER_CMD_PATTERN)" >/dev/null 2>&1; then \
		echo "server is already running (pid $$(pgrep -f "$(SERVER_CMD_PATTERN)" | head -1)) at http://localhost:$(PORT)/"; \
		echo "  - tail:  tail -f $(LOG_FILE)"; \
		echo "  - stop:  make stop"; \
		echo "  - swap:  make restart"; \
		exit 0; \
	elif lsof -nP -iTCP:$(PORT) -sTCP:LISTEN -t >/dev/null 2>&1; then \
		echo "ERROR: port $(PORT) held by another process:"; \
		lsof -nP -iTCP:$(PORT) -sTCP:LISTEN 2>/dev/null | head -5; \
		exit 1; \
	fi; \
	: > $(LOG_FILE); \
	nohup $(SERVER_VENV)/bin/python -m server >> $(LOG_FILE) 2>&1 & echo $$! > $(PID_FILE); \
	n=0; while ! lsof -nP -iTCP:$(PORT) -sTCP:LISTEN -t >/dev/null 2>&1 && [ $$n -lt 25 ]; do \
		if ! pgrep -f "$(SERVER_CMD_PATTERN)" >/dev/null 2>&1; then break; fi; \
		sleep 0.2; n=$$((n+1)); \
	done; \
	if lsof -nP -iTCP:$(PORT) -sTCP:LISTEN -t >/dev/null 2>&1; then \
		actual=$$(pgrep -f "$(SERVER_CMD_PATTERN)" | head -1); \
		[ -n "$$actual" ] && echo $$actual > $(PID_FILE); \
		echo "started — http://localhost:$(PORT)/   (pid $$(cat $(PID_FILE)), logs → $(LOG_FILE))"; \
	else \
		echo "server failed to start. Last log lines:"; \
		tail -30 $(LOG_FILE) 2>/dev/null | sed 's/^/  /'; \
		rm -f $(PID_FILE); \
		exit 1; \
	fi

stop: _stop-quiet ## stop the running server
	@echo "stopped."

# Explicit replace: kill any existing instance, then start fresh in the bg.
restart: _stop-quiet start-bg ## stop then start server in background

status: ## show server status and port holder
	@if pgrep -f "$(SERVER_CMD_PATTERN)" >/dev/null 2>&1; then \
		echo "server running: $$(pgrep -f "$(SERVER_CMD_PATTERN)" | tr '\n' ' ')"; \
		lsof -nP -iTCP:$(PORT) -sTCP:LISTEN 2>/dev/null | tail -n +2; \
	else \
		echo "no server running."; \
		other=$$(lsof -nP -iTCP:$(PORT) -sTCP:LISTEN -t 2>/dev/null); \
		if [ -n "$$other" ]; then \
			echo "NOTE: port $(PORT) held by another process:"; \
			lsof -nP -iTCP:$(PORT) -sTCP:LISTEN 2>/dev/null; \
		fi; \
	fi

check-ui: ## run UI smoke test script
	@scripts/check-ui.sh

push-productivity: ## push productivity to origin/main (errors if dirty)
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "productivity: working tree is dirty. Commit changes before pushing." >&2; \
		exit 1; \
	fi
	@git push origin main

push-content: ## stage + commit + push content to origin/main
	@git -C content add -A
	@git -C content diff --cached --quiet || \
		git -C content commit -m "Sync content $$(date +'%Y-%m-%d %H:%M')" >/dev/null
	@git -C content push origin main

push: push-productivity push-content ## push both repos, then run `g push`
	@/Users/jcortes/src/g/g.py push

# One-shot first-time bootstrap: ensures a compatible Python (creating a
# dedicated miniconda env if needed), installs venvs + CLI shims, clones
# every repo in repositories.list (idempotent), and (re)symlinks every
# project's CLAUDE.md to the canonical content/skills/project-CLAUDE.md.
setup: _ensure-python install pull-repos ## first-time bootstrap (ensure python + install + clone repos + relink)
	@$(LAB_VENV)/bin/python -m lab project relink || true
	@echo
	@echo "setup complete."
	@echo "  - lab CLI:    $(BIN_DIR)/lab"
	@echo "  - server:     make start  (http://localhost:$(PORT)/)"
	@echo "  - worktrees:  lab project add <project> <mp>"

pull-repos: ## clone/update repos listed in repositories.list
	@mkdir -p repositories
	@test -f repositories.list || echo "(no repositories.list yet — create it with one repo name per line)"
	@while read repo; do \
		[ -z "$$repo" ] && continue; \
		if [ ! -d repositories/$$repo ]; then \
			echo "cloning $$repo..."; \
			(cd repositories && mint clone $$repo 2>&1 | tail -3); \
		fi; \
		echo "updating $$repo..."; \
		default=$$(git -C repositories/$$repo remote show origin 2>/dev/null | awk '/HEAD branch/ {print $$NF}'); \
		if [ -z "$$default" ] || [ "$$default" = "(unknown)" ]; then \
			echo "  ↳ skip: origin has no default branch (empty remote?)"; \
			continue; \
		fi; \
		(cd repositories/$$repo && git checkout "$$default" --quiet 2>/dev/null && git pull --quiet) \
			|| echo "  ↳ skip: checkout/pull of $$default failed"; \
	done < repositories.list 2>/dev/null
