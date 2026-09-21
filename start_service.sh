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
    docker run --rm --network none "$IMAGE_NAME" python -m pytest -q
    ok "Tests passed inside container"
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

if [ "$MODE" = "test" ]; then
  log "Running pytest"
  python -m pytest -q
  ok "All tests passed"
  exit 0
fi

kill_port

log "Starting Agent Gateway on http://127.0.0.1:$PORT"
exec python -m uvicorn service.main:app \
  --host 127.0.0.1 \
  --port "$PORT" \
  --workers 1 \
  --log-level info
