#!/bin/bash
# =============================================================================
# Video Clone Pipeline — Master Orchestrator (Windows/Linux compatible)
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GROK2API_DIR="$SCRIPT_DIR/grok2api"
AISTUDIO_DIR="$SCRIPT_DIR/AIStudio2API"
LOGS_DIR="$SCRIPT_DIR/logs"

mkdir -p "$LOGS_DIR"

# ---------------------------------------------------------------------------
# 1. Kill existing instances (cross-platform)
# ---------------------------------------------------------------------------
echo "🛑 Stopping existing services..."

if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OS" == "Windows_NT" ]]; then
    # Windows (Git Bash / MSYS2)
    taskkill //F //IM python.exe 2>/dev/null || true
    taskkill //F //IM uvicorn.exe 2>/dev/null || true
    # Kill processes on key ports
    for port in 8000 9000 2048 3001 3002; do
        pid=$(netstat -ano 2>/dev/null | grep ":$port " | grep LISTENING | awk '{print $5}' | head -1)
        if [ -n "$pid" ]; then
            taskkill //F //PID "$pid" 2>/dev/null || true
        fi
    done
else
    # Linux / macOS
    pkill -9 -f "grok2api/main.py" 2>/dev/null || true
    pkill -9 -f "launch_camoufox.py" 2>/dev/null || true
    pkill -9 -f "app_launcher.py" 2>/dev/null || true
    pkill -9 -f "bulk_processor.py" 2>/dev/null || true
    fuser -k 8000/tcp 9000/tcp 2048/tcp 2>/dev/null || true
fi

sleep 2

# ---------------------------------------------------------------------------
# 2. Start Grok2API (image + video generation)
# ---------------------------------------------------------------------------
echo "🚀 Starting Grok2API..."

cd "$GROK2API_DIR"

# Detect Python / uv
if command -v uv &>/dev/null; then
    PYTHON_CMD="uv run python"
elif command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
else
    PYTHON_CMD="python"
fi

# Start grok2api server
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OS" == "Windows_NT" ]]; then
    $PYTHON_CMD main.py > "$LOGS_DIR/grok2api.log" 2>&1 &
else
    nohup $PYTHON_CMD main.py > "$LOGS_DIR/grok2api.log" 2>&1 &
fi

GROK_PID=$!
echo "  Grok2API PID: $GROK_PID"
cd "$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# 3. Start AIStudio2API (TTS + script rewriting)
# ---------------------------------------------------------------------------
echo "🚀 Starting AIStudio2API..."

mkdir -p "$AISTUDIO_DIR/data"

# Auto-detect saved auth profiles
AUTH_DIR="$AISTUDIO_DIR/data/auth_profiles/saved"
if [ -d "$AUTH_DIR" ]; then
    PROFILES=($(ls -t "$AUTH_DIR"/auth_auto_*.json 2>/dev/null))
    PROFILE_1="${PROFILES[0]##*/}"
    PROFILE_2="${PROFILES[1]##*/}"
    echo "  Found profiles: $PROFILE_1 $PROFILE_2"
else
    PROFILE_1=""
    PROFILE_2=""
fi

# Write workers.json
if [ -n "$PROFILE_1" ] && [ -n "$PROFILE_2" ]; then
cat > "$AISTUDIO_DIR/data/workers.json" <<EOF
{
  "workers": [
    {"id": "w1", "profile": "$PROFILE_1", "port": 3001, "camoufox_port": 9223},
    {"id": "w2", "profile": "$PROFILE_2", "port": 3002, "camoufox_port": 9224}
  ],
  "settings": {"recovery_hours": 6}
}
EOF
elif [ -n "$PROFILE_1" ]; then
cat > "$AISTUDIO_DIR/data/workers.json" <<EOF
{
  "workers": [
    {"id": "w1", "profile": "$PROFILE_1", "port": 3001, "camoufox_port": 9223}
  ],
  "settings": {"recovery_hours": 6}
}
EOF
else
cat > "$AISTUDIO_DIR/data/workers.json" <<EOF
{"workers": [], "settings": {"recovery_hours": 6}}
EOF
fi

# Write gui_config.json
cat > "$AISTUDIO_DIR/data/gui_config.json" <<EOF
{
  "fastapi_port": 2048,
  "camoufox_debug_port": 9222,
  "stream_port": 3120,
  "stream_port_enabled": true,
  "proxy_enabled": false,
  "proxy_address": "",
  "helper_enabled": false,
  "helper_endpoint": "",
  "launch_mode": "headless",
  "script_injection_enabled": false,
  "worker_mode_enabled": true,
  "log_enabled": true
}
EOF

cd "$AISTUDIO_DIR"
export PYTHONPATH=src

if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OS" == "Windows_NT" ]]; then
    uv run python src/app_launcher.py > "$LOGS_DIR/aistudio.log" 2>&1 &
else
    nohup uv run python src/app_launcher.py > "$LOGS_DIR/aistudio.log" 2>&1 &
fi

AISTUDIO_PID=$!
echo "  AIStudio2API PID: $AISTUDIO_PID"
cd "$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# 4. Wait for services to be ready
# ---------------------------------------------------------------------------
echo "⏳ Waiting for services to initialize (45s)..."
sleep 45

# Health checks
echo "🔍 Checking services..."

check_service() {
    local url="$1"
    local name="$2"
    if curl -sf "$url" >/dev/null 2>&1; then
        echo "  ✓ $name is running"
        return 0
    else
        echo "  ⚠ $name not responding at $url"
        return 1
    fi
}

GROK_OK=0
AISTUDIO_OK=0

check_service "http://localhost:8000/v1/models" "Grok2API" && GROK_OK=1 || true
check_service "http://localhost:2048/health" "AIStudio2API" && AISTUDIO_OK=1 || true

# Trigger AIStudio worker start
if [ "$AISTUDIO_OK" -eq 1 ]; then
    curl -s -X POST http://127.0.0.1:9000/api/control/start \
        -H "Content-Type: application/json" \
        -d @"$AISTUDIO_DIR/data/gui_config.json" > /dev/null 2>&1 || true
fi

if [ "$GROK_OK" -eq 0 ]; then
    echo ""
    echo "  ⚠ Grok2API is not responding. Check logs/grok2api.log"
    echo "  Tip: Make sure grok2api/data/token.json has valid SSO tokens."
    echo "  Run: python utils/manage_grok_cookies.py <your_sso_token>"
    echo ""
fi

# ---------------------------------------------------------------------------
# 5. Export environment variables for the pipeline
# ---------------------------------------------------------------------------
export GROK_API_BASE="http://localhost:8000"
export GROK_API_KEY="grok2api"
export API_BASE_URL="http://localhost:2048"

# ---------------------------------------------------------------------------
# 6. Run Bulk Pipeline
# ---------------------------------------------------------------------------
echo "🎬 Launching Bulk Processor..."

# Detect venv python
if [ -f ".venv/bin/python" ]; then
    VENV_PYTHON=".venv/bin/python"
elif [ -f ".venv/Scripts/python.exe" ]; then
    VENV_PYTHON=".venv/Scripts/python.exe"
elif command -v python3 &>/dev/null; then
    VENV_PYTHON="python3"
else
    VENV_PYTHON="python"
fi

$VENV_PYTHON bulk_processor.py

echo "✅ Pipeline session finished."
