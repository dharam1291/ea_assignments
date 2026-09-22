#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# start_service.sh — Single entry point for the Observable Agent Gateway
#
# Usage:
#   ./start_service.sh            # Native OS (auto-creates venv, installs deps)
#   ./start_service.sh --docker   # Build & run via Docker
#   ./start_service.sh --test     # Run pytest only (native)
#   ./start_service.sh --docker --test  # Run pytest inside Docker (--network none)
# ──────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

IMAGE_NAME="dharmendra-agent-gateway"
PORT="${PORT:-8000}"
VENV_DIR=".venv"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=11
MODE="serve"
USE_DOCKER=false

# ── Parse arguments ──────────────────────────────────────────────────

for arg in "$@"; do
  case "$arg" in
    --docker)  USE_DOCKER=true ;;
    --test)    MODE="test" ;;
    --helper)
      echo ""
      printf "\033[1;36m  Observable Agent Gateway — Command Reference\033[0m\n"
      echo "  ─────────────────────────────────────────────────────────"
      echo ""
      printf "\033[1;33m  NATIVE (no Docker required)\033[0m\n"
      echo ""
      printf "    \033[1m./start_service.sh\033[0m\n"
      echo "        Start the gateway on http://127.0.0.1:8000"
      echo "        Auto-detects python3.11+, creates .venv, installs deps"
      echo "        Kills any existing process on the port before starting"
      echo ""
      printf "    \033[1m./start_service.sh --test\033[0m\n"
      echo "        Run the full pytest suite (40 tests) and exit"
      echo "        Sets up .venv if needed, does not start the server"
      echo ""
      printf "    \033[1mPORT=9000 ./start_service.sh\033[0m\n"
      echo "        Start natively on a custom port (default: 8000)"
      echo ""
      printf "\033[1;33m  DOCKER\033[0m\n"
      echo ""
      printf "    \033[1m./start_service.sh --docker\033[0m\n"
      echo "        Build the image and start the container on port 8000"
      echo "        Kills any existing process on the port before starting"
      echo ""
      printf "    \033[1m./start_service.sh --docker --test\033[0m\n"
      echo "        Build the image and run pytest inside the container"
      echo "        Uses --network none (proves no external calls needed)"
      echo "        Does NOT start the server — exits after tests pass"
      echo ""
      printf "    \033[1mPORT=9000 ./start_service.sh --docker\033[0m\n"
      echo "        Run container, map to a custom host port"
      echo ""
      printf "\033[1;33m  ACCEPTANCE CHECK (run in a separate terminal)\033[0m\n"
      echo ""
      printf "    \033[1mpython tools/acceptance_check.py --base-url http://127.0.0.1:8000\033[0m\n"
      echo "        Run the 14-point HTTP acceptance checker against a running server"
      echo ""
      printf "\033[1;33m  HELPER\033[0m\n"
      echo ""
      printf "    \033[1m./start_service.sh --helper\033[0m\n"
      echo "        Show this guide"
      echo ""
      echo "  ─────────────────────────────────────────────────────────"
      printf "  \033[2mImage: $IMAGE_NAME  |  Port: \$PORT (default $PORT)\033[0m\n"
      echo ""
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg"
      echo "Run $0 --helper for usage."
      exit 1
      ;;
  esac
done

# ── Utility functions ────────────────────────────────────────────────

log()  { printf "\033[1;34m▶ %s\033[0m\n" "$1"; }
ok()   { printf "\033[1;32m✔ %s\033[0m\n" "$1"; }
warn() { printf "\033[1;33m⚠ %s\033[0m\n" "$1"; }
fail() { printf "\033[1;31m✖ %s\033[0m\n" "$1"; exit 1; }

REPORT_FILE="$SCRIPT_DIR/docs/assessment_report.html"

update_pytest_report() {
  local output_file="$1"
  [ -f "$REPORT_FILE" ] || return 0
  "$SCRIPT_DIR/$VENV_DIR/bin/python" -c "
import re, sys, html as h
raw = open('$output_file').read()

# Parse summary: '40 passed in 0.75s' or '38 passed, 2 failed in 0.80s'
m = re.search(r'(\d+) passed', raw)
passed = int(m.group(1)) if m else 0
m = re.search(r'(\d+) failed', raw)
failed = int(m.group(1)) if m else 0
total = passed + failed
m = re.search(r'in ([\d.]+)s', raw)
duration = m.group(1) if m else '?'

report = open('$REPORT_FILE').read()

# Build pytest output HTML
lines = []
for line in raw.splitlines():
    line_esc = h.escape(line)
    if ' PASSED' in line:
        name = line.split('::',1)[-1].split(' ')[0] if '::' in line else line_esc
        cls_test = line.rsplit('::',1)
        short = cls_test[-1].split(' ')[0] if len(cls_test)>1 else name
        cls_name = cls_test[0].rsplit('::',1)[-1] if len(cls_test)>1 else ''
        label = f'{cls_name}::{short}' if cls_name else short
        lines.append(f'<span class=\"pass\">PASSED</span> {h.escape(label)}')
    elif ' FAILED' in line:
        name = line.split('::',1)[-1].split(' ')[0] if '::' in line else line_esc
        cls_test = line.rsplit('::',1)
        short = cls_test[-1].split(' ')[0] if len(cls_test)>1 else name
        cls_name = cls_test[0].rsplit('::',1)[-1] if len(cls_test)>1 else ''
        label = f'{cls_name}::{short}' if cls_name else short
        lines.append(f'<span class=\"fail\" style=\"color:var(--red)\">FAILED</span> {h.escape(label)}')
pytest_lines = chr(10).join(lines)

badge = 'badge-pass' if failed == 0 else 'badge-fail'
summary_text = f'{passed} passed' if failed == 0 else f'{passed} passed, {failed} failed'
summary_class = 'pass' if failed == 0 else 'fail\" style=\"color:var(--red)'
all_text = 'ALL PASS' if failed == 0 else f'{failed} FAILED'

pytest_block = f'''      <div id=\"pytest\" class=\"tab-content active\">
        <div class=\"code-block\" style=\"white-space:pre-wrap!important;word-break:break-word!important;font-family:'JetBrains Mono','Fira Code',monospace!important;\">
<span class=\"header\">\$ python -m pytest service/tests/ -v</span>

{pytest_lines}

<span class=\"{summary_class}\">========== {summary_text} in {duration}s ==========</span>
        </div>
      </div>'''

# Replace pytest output
report = re.sub(
    r'<!-- PYTEST_OUTPUT_START -->.*?<!-- PYTEST_OUTPUT_END -->',
    f'<!-- PYTEST_OUTPUT_START -->\n{pytest_block}\n      <!-- PYTEST_OUTPUT_END -->',
    report, flags=re.DOTALL)

# Update hero test stats
hero_test = f'<div class=\"meta-item\">Tests: <span>{summary_text}</span></div>'
report = re.sub(
    r'<!-- HERO_TEST_STATS_START -->.*?<!-- HERO_TEST_STATS_END -->',
    f'<!-- HERO_TEST_STATS_START -->{hero_test}<!-- HERO_TEST_STATS_END -->',
    report, flags=re.DOTALL)

# Update stat card
stat_card = f'''<div class=\"card stat-card\">
        <div class=\"number\">{passed}</div>
        <div class=\"label\">Tests Passed</div>
      </div>'''
report = re.sub(
    r'<!-- STAT_TESTS_START -->.*?<!-- STAT_TESTS_END -->',
    f'<!-- STAT_TESTS_START -->{stat_card}<!-- STAT_TESTS_END -->',
    report, flags=re.DOTALL)

open('$REPORT_FILE','w').write(report)
print(f'Report updated: {passed} passed, {failed} failed in {duration}s')
" 2>/dev/null && ok "Assessment report updated (docs/assessment_report.html)" || true
}

kill_port() {
  local pids
  pids=$(lsof -ti "tcp:$PORT" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    warn "Port $PORT in use — killing existing process(es): $pids"
    echo "$pids" | xargs kill -9 2>/dev/null || true
    sleep 1
    ok "Port $PORT freed"
  fi
}

find_python() {
  local candidates=("python3.13" "python3.12" "python3.11" "python3")
  for cmd in "${candidates[@]}"; do
    if command -v "$cmd" &>/dev/null; then
      local ver
      ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
      local major minor
      major=$(echo "$ver" | cut -d. -f1)
      minor=$(echo "$ver" | cut -d. -f2)
      if [ "$major" -ge "$MIN_PYTHON_MAJOR" ] && [ "$minor" -ge "$MIN_PYTHON_MINOR" ]; then
        echo "$cmd"
        return 0
      fi
    fi
  done
  return 1
}

setup_venv() {
  local py="$1"

  if [ ! -d "$VENV_DIR" ]; then
    log "Creating virtual environment with $py"
    "$py" -m venv "$VENV_DIR"
    ok "Virtual environment created at $VENV_DIR"
  fi

  source "$VENV_DIR/bin/activate"

  local installed_hash="" requirements_hash=""
  requirements_hash=$(md5sum requirements.txt 2>/dev/null | cut -d' ' -f1 || md5 -q requirements.txt 2>/dev/null || echo "none")

  if [ -f "$VENV_DIR/.requirements_hash" ]; then
    installed_hash=$(cat "$VENV_DIR/.requirements_hash")
  fi

  if [ "$installed_hash" != "$requirements_hash" ]; then
    log "Installing / updating dependencies"
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
    echo "$requirements_hash" > "$VENV_DIR/.requirements_hash"
    ok "Dependencies installed"
  else
    ok "Dependencies up to date"
  fi
}

# ── Docker mode ──────────────────────────────────────────────────────

if $USE_DOCKER; then
  command -v docker &>/dev/null || fail "Docker is not installed or not in PATH"

  log "Building Docker image: $IMAGE_NAME"
  docker build -t "$IMAGE_NAME" . || fail "Docker build failed"
  ok "Image built: $IMAGE_NAME"

  if [ "$MODE" = "test" ]; then
    log "Running pytest inside container (--network none)"
    PYTEST_LOG=$(mktemp)
    set +e
    docker run --rm --network none "$IMAGE_NAME" python -m pytest service/tests/ -v 2>&1 | tee "$PYTEST_LOG"
    DOCKER_EXIT=${PIPESTATUS[0]}
    set -e
    if [ -f "$REPORT_FILE" ]; then
      HOST_PY=$(find_python 2>/dev/null || echo "")
      if [ -n "$HOST_PY" ]; then
        VENV_DIR=".venv"
        if [ -f "$SCRIPT_DIR/$VENV_DIR/bin/python" ]; then
          update_pytest_report "$PYTEST_LOG"
        fi
      fi
    fi
    rm -f "$PYTEST_LOG"
    if [ "$DOCKER_EXIT" -eq 0 ]; then
      ok "Tests passed inside container"
    else
      fail "Tests failed inside container (exit code $DOCKER_EXIT)"
    fi
    exit "$DOCKER_EXIT"
  else
    kill_port
    log "Starting container on port $PORT"
    docker run --rm -p "127.0.0.1:${PORT}:8000" "$IMAGE_NAME" &
    CONTAINER_PID=$!
    sleep 2

    if kill -0 "$CONTAINER_PID" 2>/dev/null; then
      ok "Service running at http://127.0.0.1:$PORT  (PID $CONTAINER_PID)"
      echo ""
      echo "  Health check:  curl http://127.0.0.1:$PORT/health"
      echo "  Stop:          kill $CONTAINER_PID  (or Ctrl+C)"
      echo ""
      wait "$CONTAINER_PID"
    else
      fail "Container exited unexpectedly — check docker logs"
    fi
  fi
  exit 0
fi

# ── Native mode ──────────────────────────────────────────────────────

PYTHON=$(find_python) || fail "Python $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR+ not found. Install it and retry."
ok "Found Python: $PYTHON ($($PYTHON --version 2>&1))"

setup_venv "$PYTHON"

VENV_PYTHON="$SCRIPT_DIR/$VENV_DIR/bin/python"

if [ "$MODE" = "test" ]; then
  log "Running pytest"
  PYTEST_LOG=$(mktemp)
  set +e
  "$VENV_PYTHON" -m pytest service/tests/ -v 2>&1 | tee "$PYTEST_LOG"
  PYTEST_EXIT=${PIPESTATUS[0]}
  set -e
  update_pytest_report "$PYTEST_LOG"
  rm -f "$PYTEST_LOG"
  if [ "$PYTEST_EXIT" -eq 0 ]; then
    ok "All tests passed"
  else
    fail "Some tests failed (exit code $PYTEST_EXIT)"
  fi
  exit "$PYTEST_EXIT"
fi

kill_port

log "Starting Agent Gateway on http://127.0.0.1:$PORT"
exec "$VENV_PYTHON" -m uvicorn service.main:app \
  --host 127.0.0.1 \
  --port "$PORT" \
  --workers 1 \
  --log-level info
