.PHONY: ls install uninstall test test-fast test-integration test-all test-suite test-slow start stop restart start-bg status dev agent-install agent-uninstall agent-status agent-tail pull-repos check-ui setup _stop-quiet _ensure-python start-all stop-all

.DEFAULT_GOAL := ls

ls: ## list available make targets
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-][a-zA-Z0-9_-]*:.*##/ {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

LAB_VENV := apps/lab/.venv
CORE_VENV := core/.venv
PYTEST_STUBS := $(CURDIR)/scripts/pytest-stubs
BIN_DIR := $(HOME)/.local/bin
PID_FILE := .lab-server.pid
PORT_FILE := .lab-server.port
APP_LOG_DIR := logs
BACKEND_LOG := $(APP_LOG_DIR)/backend.log
FRONTEND_LOG := $(APP_LOG_DIR)/frontend.log
ERROR_LOG := $(APP_LOG_DIR)/errors.log
PROCESS_OUTPUT := /dev/null
# Port can be overridden per-run with any of these (in priority order):
#   make start PORT=4444     # canonical, all-caps
#   make start port=4444     # lowercase accepted for muscle-memory
# The chosen value is exported as LAB_PORT to the server subprocess and
# recorded in $(PORT_FILE) on startup so other tools (lab CLI, scripts,
# Claude curl examples) discover the actual running port without hardcoding.
# Note: ports below 1024 (e.g. 80, 443) need root to bind on macOS/Linux.
PORT ?= $(or $(port),8080)
CORE_CMD_PATTERN := core/.venv/bin/python -m core

# ─── LaunchAgent (always-on supervision) ────────────────────────────────────
# When installed, launchd auto-starts the server at login and respawns it on
# crash (KeepAlive). `make agent-install` writes + loads the plist below.
# The plist runs the python binary directly so launchd owns the real PID.
# Note: PORT is baked in at install time — reinstall to change ports.
AGENT_LABEL  := com.lab.server
AGENT_PLIST  := $(HOME)/Library/LaunchAgents/$(AGENT_LABEL).plist
AGENT_UID    := $(shell id -u)
AGENT_TARGET := gui/$(AGENT_UID)/$(AGENT_LABEL)

define AGENT_PLIST_CONTENT
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$(AGENT_LABEL)</string>
  <key>ProgramArguments</key>
  <array>
    <string>$(CURDIR)/$(CORE_VENV)/bin/python</string>
    <string>-m</string>
    <string>core</string>
  </array>
  <key>WorkingDirectory</key><string>$(CURDIR)</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>LAB_PORT</key><string>$(PORT)</string>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
  <key>StandardOutPath</key><string>$(PROCESS_OUTPUT)</string>
  <key>StandardErrorPath</key><string>$(PROCESS_OUTPUT)</string>
  <key>ProcessType</key><string>Interactive</string>
</dict>
</plist>
endef
export AGENT_PLIST_CONTENT

# ─── Reject unknown command-line variables ──────────────────────────────────
# Make silently accepts any `KEY=VALUE` on the CLI as a top-level variable,
# even if nothing reads it. That hides typos like `make start pot=3333`
# (which would silently fall back to the default port). Whitelist the keys
# we actually support and bail out on anything else.
ALLOWED_MAKE_VARS := PORT port
$(foreach _pair,$(MAKEOVERRIDES),\
  $(eval _key := $(firstword $(subst =, ,$(_pair))))\
  $(if $(filter $(_key),$(ALLOWED_MAKE_VARS)),,\
    $(error unknown make variable '$(_key)'. Allowed: $(ALLOWED_MAKE_VARS). Did you mean PORT=?)))

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

install: ## create venvs + install lab/core CLIs (requires Python 3.11+; run `make setup` first time)
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
	test -d $(CORE_VENV) || "$$py" -m venv $(CORE_VENV)
	@$(LAB_VENV)/bin/pip install -e 'apps/lab[dev]' --quiet
	@ln -sf $(CURDIR)/apps/lab/lab $(BIN_DIR)/lab
	@$(CORE_VENV)/bin/pip install -e 'apps/lab' --quiet
	@$(CORE_VENV)/bin/pip install -e 'core[dev]' --quiet
	@ln -sf $(CURDIR)/core/core $(BIN_DIR)/core
	@# `lab-server` + `gdiff` stay as muscle-memory aliases for the core server.
	@ln -sf $(CURDIR)/core/core $(BIN_DIR)/lab-server
	@ln -sf $(CURDIR)/core/core $(BIN_DIR)/gdiff
	@# darwin-backups, trustim-ir-cli — symlinks only (they have their own dep management)
	@[ -f apps/darwin-backups/darwin-backups ] && ln -sf $(CURDIR)/apps/darwin-backups/darwin-backups $(BIN_DIR)/darwin-backups || true
	@[ -f apps/trustim-ir-cli/trustim-ir-cli ] && ln -sf $(CURDIR)/apps/trustim-ir-cli/trustim-ir-cli $(BIN_DIR)/trustim-ir-cli || true
	@# Clean up legacy shims from the pre-unification layout (incl. retired darwin-runner).
	@rm -f $(BIN_DIR)/lab-backend $(BIN_DIR)/darwin-runner
	@echo "Installed lab, core (aka lab-server / gdiff) → $(BIN_DIR)/"
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
	@rm -f $(BIN_DIR)/lab $(BIN_DIR)/core $(BIN_DIR)/lab-server $(BIN_DIR)/lab-backend $(BIN_DIR)/gdiff $(BIN_DIR)/darwin-runner $(BIN_DIR)/darwin-backups $(BIN_DIR)/trustim-ir-cli
	@rm -rf $(LAB_VENV) $(CORE_VENV)
	@echo "Uninstalled."

test: ## run isolated unit + integration tests for lab/core (skips @slow)
	@PYTHONPATH="$(PYTEST_STUBS)$${PYTHONPATH:+:$$PYTHONPATH}" $(LAB_VENV)/bin/pytest apps/lab/tests -v && \
	 PYTHONPATH="$(PYTEST_STUBS)$${PYTHONPATH:+:$$PYTHONPATH}" $(CORE_VENV)/bin/pytest core/tests -v

test-fast: test ## alias for `make test` (skips @slow)

test-integration: ## run isolated integration tests for backend endpoints + UI events
	@PYTHONPATH="$(PYTEST_STUBS)$${PYTHONPATH:+:$$PYTHONPATH}" $(LAB_VENV)/bin/pytest apps/lab/tests/test_integration_e2e.py -v && \
	 PYTHONPATH="$(PYTEST_STUBS)$${PYTHONPATH:+:$$PYTHONPATH}" $(CORE_VENV)/bin/pytest \
		core/tests/test_integration_e2e.py \
		core/tests/test_frontend_terminal_ui.py \
		core/tests/test_frontend_logging.py \
		core/tests/test_logging_infra.py \
		core/tests/test_proxy_routes.py \
		core/tests/test_term_routes.py \
		core/tests/test_term_ws_reliability.py \
		-v

test-slow: ## run only the @slow tests (latency budgets, reconnect storms)
	@PYTHONPATH="$(PYTEST_STUBS)$${PYTHONPATH:+:$$PYTHONPATH}" $(CORE_VENV)/bin/pytest core/tests -v -m slow -o "addopts=-ra --cov=core --cov-report=term-missing"

test-all: ## run every isolated lab/core test, including @slow
	@PYTHONPATH="$(PYTEST_STUBS)$${PYTHONPATH:+:$$PYTHONPATH}" $(LAB_VENV)/bin/pytest apps/lab/tests -v && \
	 PYTHONPATH="$(PYTEST_STUBS)$${PYTHONPATH:+:$$PYTHONPATH}" $(CORE_VENV)/bin/pytest core/tests -v -o "addopts=-ra --cov=core --cov-report=term-missing"

test-suite: test-all ## run all unit + integration tests in isolated fixtures

# `_stop-quiet` reliably kills the running server. Strategy:
#   1. Kill whatever holds the port recorded in $(PORT_FILE) (port-accurate).
#   2. Sweep any remaining server processes by command-line pattern (safety
#      net — catches an orphaned PID whose port file got deleted, or a stale
#      instance from a previous shell). We match on the exact module
#      invocation so we never touch other python processes.
# Only called when the user explicitly asks to stop / restart.
_stop-quiet:
	@running_port=$$(cat $(PORT_FILE) 2>/dev/null); \
	if [ -n "$$running_port" ]; then \
		pids=$$(lsof -nP -iTCP:$$running_port -sTCP:LISTEN -t 2>/dev/null); \
		[ -n "$$pids" ] && kill -TERM $$pids 2>/dev/null || true; \
	fi
	@pkill -TERM -f "$(CORE_CMD_PATTERN)" 2>/dev/null || true
	@n=0; while pgrep -f "$(CORE_CMD_PATTERN)" >/dev/null 2>&1 && [ $$n -lt 10 ]; do \
		sleep 0.2; n=$$((n+1)); \
	done
	@running_port=$$(cat $(PORT_FILE) 2>/dev/null); \
	if [ -n "$$running_port" ]; then \
		pids=$$(lsof -nP -iTCP:$$running_port -sTCP:LISTEN -t 2>/dev/null); \
		[ -n "$$pids" ] && kill -KILL $$pids 2>/dev/null || true; \
	fi
	@pkill -KILL -f "$(CORE_CMD_PATTERN)" 2>/dev/null || true
	@rm -f $(PID_FILE) $(PORT_FILE)

# Background server. `make start` is always non-blocking — the server runs
# detached, and the bound port is written to $(PORT_FILE) by the server on
# startup. App logs are written by core itself to exactly:
# $(BACKEND_LOG), $(FRONTEND_LOG), and $(ERROR_LOG).
#
# Single-instance / single-port rule: at most one lab server may run, on at
# most one port. If a server is already up, the rules are:
#   - same port → no-op, exit 0 (running `make start` from a 2nd shell
#     doesn't clobber the first).
#   - different port → exit 1 with a clear error. The user must either keep
#     using the already-running port, or `make restart PORT=NNNN` to switch.
#
# Override the port per-run with `make start PORT=4444`. The chosen value is
# exported as $$LAB_PORT (honored by server/config.py).
start: ## start server in background (override port with PORT=NNNN)
	@if pgrep -f "$(CORE_CMD_PATTERN)" >/dev/null 2>&1; then \
		running_port=$$(cat $(PORT_FILE) 2>/dev/null || echo "$(PORT)"); \
		running_pid=$$(pgrep -f "$(CORE_CMD_PATTERN)" | head -1); \
		if [ "$$running_port" = "$(PORT)" ]; then \
			echo "server is already running (pid $$running_pid) at http://localhost:$$running_port/"; \
			echo "  - tail:  make agent-tail"; \
			echo "  - stop:  make stop"; \
			echo "  - swap:  make restart PORT=$$running_port"; \
			exit 0; \
		else \
			echo "ERROR: a lab server is already running on port $$running_port (pid $$running_pid)."; \
			echo "       Refusing to start a second instance on port $(PORT)."; \
			echo "       To switch ports:  make restart PORT=$(PORT)"; \
			echo "       To keep current:  open http://localhost:$$running_port/"; \
			exit 1; \
		fi; \
	elif lsof -nP -iTCP:$(PORT) -sTCP:LISTEN -t >/dev/null 2>&1; then \
		echo "ERROR: port $(PORT) held by another process:"; \
		lsof -nP -iTCP:$(PORT) -sTCP:LISTEN 2>/dev/null | head -5; \
		exit 1; \
	fi; \
	mkdir -p $(APP_LOG_DIR); \
	LAB_PORT=$(PORT) nohup $(CORE_VENV)/bin/python -m core >> $(PROCESS_OUTPUT) 2>&1 & echo $$! > $(PID_FILE); \
	n=0; while ! lsof -nP -iTCP:$(PORT) -sTCP:LISTEN -t >/dev/null 2>&1 && [ $$n -lt 25 ]; do \
		if ! pgrep -f "$(CORE_CMD_PATTERN)" >/dev/null 2>&1; then break; fi; \
		sleep 0.2; n=$$((n+1)); \
	done; \
	if lsof -nP -iTCP:$(PORT) -sTCP:LISTEN -t >/dev/null 2>&1; then \
		actual=$$(pgrep -f "$(CORE_CMD_PATTERN)" | head -1); \
		[ -n "$$actual" ] && echo $$actual > $(PID_FILE); \
		echo "started — http://localhost:$(PORT)/   (pid $$(cat $(PID_FILE)), logs → $(BACKEND_LOG), $(FRONTEND_LOG), $(ERROR_LOG))"; \
	else \
		echo "server failed to start. Last app log lines:"; \
		tail -30 $(BACKEND_LOG) $(ERROR_LOG) 2>/dev/null | sed 's/^/  /'; \
		rm -f $(PID_FILE); \
		exit 1; \
	fi

# Alias kept for existing callers (lab CLI, check-ui.sh) — `start` is already
# background, but `start-bg` still works.
start-bg: start ## alias for `start` (kept for back-compat)

stop: _stop-quiet ## stop the running server
	@if launchctl print $(AGENT_TARGET) >/dev/null 2>&1; then \
		echo "stopped — BUT launch agent is loaded; KeepAlive will respawn it."; \
		echo "         To stop permanently:  make agent-uninstall"; \
	else \
		echo "stopped."; \
	fi

# Explicit replace. If the launch agent is supervising, kickstart it (launchd
# would otherwise race our kill and respawn the process). Otherwise do the
# normal stop+start dance.
restart: ## stop then start the server (uses launchctl kickstart if agent is loaded)
	@if launchctl print $(AGENT_TARGET) >/dev/null 2>&1; then \
		echo "agent-supervised restart via launchctl kickstart…"; \
		launchctl kickstart -k $(AGENT_TARGET); \
		echo "kicked. (tail logs: make agent-tail)"; \
	else \
		$(MAKE) -s _stop-quiet start PORT=$(PORT); \
	fi

# Foreground dev server with uvicorn hot reload. Watches core/src/core
# only — edits there trigger an automatic restart, no make restart needed.
# Refuses to run if the launch agent is loaded (it would fight the dev process
# over the port and confuse reload).
dev: ## foreground server with hot reload (Ctrl-C to stop)
	@if launchctl print $(AGENT_TARGET) >/dev/null 2>&1; then \
		echo "ERROR: launch agent is supervising the server."; \
		echo "       Unload it first:  make agent-uninstall"; \
		exit 1; \
	fi
	@$(MAKE) -s _stop-quiet
	@echo "dev server (hot reload) — http://localhost:$(PORT)/   (Ctrl-C to stop)"
	@LAB_PORT=$(PORT) LAB_RELOAD=1 $(CORE_VENV)/bin/python -m core

status: ## show server status and port holder
	@if pgrep -f "$(CORE_CMD_PATTERN)" >/dev/null 2>&1; then \
		running_port=$$(cat $(PORT_FILE) 2>/dev/null || echo "$(PORT)"); \
		echo "server running: $$(pgrep -f "$(CORE_CMD_PATTERN)" | tr '\n' ' ')at http://localhost:$$running_port/"; \
		lsof -nP -iTCP:$$running_port -sTCP:LISTEN 2>/dev/null | tail -n +2; \
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

# ─── All project dev servers + core, one shot ──────────────────────────────
# The lab UI proxies into per-project dev servers declared in each
# project.json's `proxies` list (see core/src/core/routes/proxy.py), but it
# never starts them — you had to start each by hand. These targets do that:
# core itself, plus the dev server for every project that currently has one
# wired up. Each is idempotent (skipped if its port is already bound) and
# resume/CV already has its own make serve/stop, so we delegate to it.
RESUME_DIR := projects/resume/CV
PROGRAMMING_DIR := projects/programming/programming
PROGRAMMING_PORT := 8002
T_AND_R_DIR := projects/type-and-recall
T_AND_R_PORT := 8003

start-all: start ## start core (8080) + resume/programming/type-and-recall dev servers (8001/8002/8003)
	@if [ -d $(RESUME_DIR) ]; then $(MAKE) -s -C $(RESUME_DIR) serve; fi
	@if lsof -nP -iTCP:$(PROGRAMMING_PORT) -sTCP:LISTEN -t >/dev/null 2>&1; then \
		echo "programming dev server already running at http://localhost:$(PROGRAMMING_PORT)/"; \
	elif [ -d $(PROGRAMMING_DIR) ]; then \
		(cd $(PROGRAMMING_DIR) && nohup python3 -m http.server $(PROGRAMMING_PORT) > /dev/null 2>&1 & echo $$! > .devserver.pid); \
		echo "programming dev server started at http://localhost:$(PROGRAMMING_PORT)/"; \
	fi
	@if lsof -nP -iTCP:$(T_AND_R_PORT) -sTCP:LISTEN -t >/dev/null 2>&1; then \
		echo "type-and-recall dev server already running at http://localhost:$(T_AND_R_PORT)/"; \
	elif [ -d $(T_AND_R_DIR) ]; then \
		(cd $(T_AND_R_DIR) && nohup node_modules/.bin/vite > /dev/null 2>&1 & echo $$! > .devserver.pid); \
		echo "type-and-recall dev server started at http://localhost:$(T_AND_R_PORT)/"; \
	fi

stop-all: ## stop core + resume/programming/type-and-recall dev servers
	@if [ -d $(RESUME_DIR) ]; then $(MAKE) -s -C $(RESUME_DIR) stop; fi
	@if [ -f $(PROGRAMMING_DIR)/.devserver.pid ]; then \
		kill $$(cat $(PROGRAMMING_DIR)/.devserver.pid) 2>/dev/null || true; \
		rm -f $(PROGRAMMING_DIR)/.devserver.pid; \
	fi
	@if [ -f $(T_AND_R_DIR)/.devserver.pid ]; then \
		kill $$(cat $(T_AND_R_DIR)/.devserver.pid) 2>/dev/null || true; \
		rm -f $(T_AND_R_DIR)/.devserver.pid; \
	fi
	@$(MAKE) -s stop

# ─── Launch agent management ────────────────────────────────────────────────
# `agent-install`: writes the plist (with current PORT/paths baked in) and
# loads it via `launchctl bootstrap`. From then on launchd owns the server:
# it boots at login and respawns on crash. Re-run after changing PORT.
agent-install: ## install + load launchd agent (always-on, restart on crash)
	@mkdir -p $(HOME)/Library/LaunchAgents
	@$(MAKE) -s _stop-quiet
	@launchctl bootout $(AGENT_TARGET) 2>/dev/null || true
	@echo "$$AGENT_PLIST_CONTENT" > $(AGENT_PLIST)
	@launchctl bootstrap gui/$(AGENT_UID) $(AGENT_PLIST)
	@n=0; while ! lsof -nP -iTCP:$(PORT) -sTCP:LISTEN -t >/dev/null 2>&1 && [ $$n -lt 50 ]; do \
		sleep 0.2; n=$$((n+1)); \
	done
	@if lsof -nP -iTCP:$(PORT) -sTCP:LISTEN -t >/dev/null 2>&1; then \
		echo "installed — http://localhost:$(PORT)/   (plist: $(AGENT_PLIST))"; \
		echo "  - logs:    make agent-tail"; \
		echo "  - kick:    make restart"; \
		echo "  - status:  make agent-status"; \
		echo "  - remove:  make agent-uninstall"; \
	else \
		echo "agent loaded but server didn't come up. Last app log lines:"; \
		tail -30 $(BACKEND_LOG) $(ERROR_LOG) 2>/dev/null | sed 's/^/  /'; \
		exit 1; \
	fi

agent-uninstall: ## unload + remove the launchd agent
	@launchctl bootout $(AGENT_TARGET) 2>/dev/null || launchctl unload $(AGENT_PLIST) 2>/dev/null || true
	@rm -f $(AGENT_PLIST)
	@echo "agent removed."

agent-status: ## show launchd agent status
	@if launchctl print $(AGENT_TARGET) >/dev/null 2>&1; then \
		launchctl print $(AGENT_TARGET) | grep -E '^\s*(state|pid|last exit|program|path|domain) ' || true; \
	else \
		echo "agent not loaded. (install with: make agent-install)"; \
	fi

agent-tail: ## tail the agent's log file
	@mkdir -p $(APP_LOG_DIR); touch $(BACKEND_LOG) $(FRONTEND_LOG) $(ERROR_LOG)
	@tail -f $(BACKEND_LOG) $(FRONTEND_LOG) $(ERROR_LOG)

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
# every repo in repositories.list (idempotent), and unifies agent context —
# making AGENTS.md canonical with CLAUDE.md / Copilot / memory symlinked to it
# (see `lab agents sync`).
setup: _ensure-python install pull-repos ## first-time bootstrap (ensure python + install + clone repos + sync agents)
	@$(LAB_VENV)/bin/python -m lab agents sync || true
	@echo
	@echo "setup complete."
	@echo "  - lab CLI:    $(BIN_DIR)/lab"
	@echo "  - server:     make start              (http://localhost:$(PORT)/)"
	@echo "                make start PORT=4444    (override port)"
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
