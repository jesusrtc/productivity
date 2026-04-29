PYTHON     ?= python3
HOST       ?= 127.0.0.1
PORT       ?= 4000
REPO_ROOT  ?= $(CURDIR)/repos
LOG_FILE   ?= $(CURDIR)/server.log
PID_FILE   ?= $(CURDIR)/server.pid

.PHONY: start startbg stop status logs

start:
	@mkdir -p "$(REPO_ROOT)"
	HOST=$(HOST) PORT=$(PORT) REPO_ROOT="$(REPO_ROOT)" \
		$(PYTHON) server/server.py

startbg:
	@mkdir -p "$(REPO_ROOT)"
	@if [ -f "$(PID_FILE)" ] && kill -0 $$(cat "$(PID_FILE)") 2>/dev/null; then \
		echo "already running (pid $$(cat $(PID_FILE)))"; exit 1; \
	fi
	@HOST=$(HOST) PORT=$(PORT) REPO_ROOT="$(REPO_ROOT)" \
		nohup $(PYTHON) server/server.py >"$(LOG_FILE)" 2>&1 & \
		echo $$! >"$(PID_FILE)"; \
		echo "started pid $$(cat $(PID_FILE)) on $(HOST):$(PORT) -> $(LOG_FILE)"

stop:
	@if [ -f "$(PID_FILE)" ]; then \
		pid=$$(cat "$(PID_FILE)"); \
		if kill -0 $$pid 2>/dev/null; then echo "killing $$pid"; kill $$pid; \
		else echo "stale pidfile (pid $$pid not running)"; fi; \
		rm -f "$(PID_FILE)"; \
	else \
		pid=$$(lsof -tiTCP:$(PORT) -sTCP:LISTEN 2>/dev/null); \
		if [ -n "$$pid" ]; then echo "killing $$pid"; kill $$pid; \
		else echo "nothing listening on :$(PORT)"; fi; \
	fi

status:
	@lsof -iTCP:$(PORT) -sTCP:LISTEN || echo "not running on :$(PORT)"

logs:
	@tail -n 50 -f "$(LOG_FILE)"
