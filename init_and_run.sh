#!/bin/bash

# =============================================================================
# Video Clone Pipeline — Master Orchestrator
# =============================================================================

# Configuration
AISTUDIO_DIR="AIStudio2API"
METAAI_DIR="metaai-api"
VENV_BIN=".venv/bin/python"

# 1. Kill any existing instances
echo "🛑 Stopping existing services and clearing ports..."
pkill -9 -f "launch_camoufox.py"
pkill -9 -f "metaai-api"
pkill -9 -f "api_server:app"
pkill -9 -f "bulk_processor.py"
pkill -9 -f "app_launcher.py"
pkill -9 -f "gateway.py"
pkill -9 -f "grok2api/main.py"

# Force kill processes on key ports
fuser -k 9000/tcp 2048/tcp 8000/tcp 3001/tcp 3002/tcp 3003/tcp 3004/tcp 9222/tcp 9223/tcp 9224/tcp 9225/tcp 9226/tcp 2>/dev/null || true

sleep 2

# 2. Re-authentication / Worker Setup
echo "🔑 Setting up AI Studio Workers..."
mkdir -p "$AISTUDIO_DIR/data"

# Auto-detect the latest saved auth profiles
AUTH_DIR="$AISTUDIO_DIR/data/auth_profiles/saved"
if [ -d "$AUTH_DIR" ]; then
    PROFILES=($(ls -t "$AUTH_DIR"/auth_auto_*.json 2>/dev/null))
    PROFILE_1="${PROFILES[0]##*/}"
    PROFILE_2="${PROFILES[1]##*/}"
    echo "  Found profiles: $PROFILE_1, $PROFILE_2"
else
    echo "  ⚠ No saved auth profiles found in $AUTH_DIR"
    PROFILE_1=""
    PROFILE_2=""
fi

if [ -n "$PROFILE_1" ] && [ -n "$PROFILE_2" ]; then
cat <<EOF > "$AISTUDIO_DIR/data/workers.json"
{
  "workers": [
    {"id": "w1", "profile": "$PROFILE_1", "port": 3001, "camoufox_port": 9223},
    {"id": "w2", "profile": "$PROFILE_2", "port": 3002, "camoufox_port": 9224}
  ],
  "settings": {"recovery_hours": 6}
}
EOF
elif [ -n "$PROFILE_1" ]; then
cat <<EOF > "$AISTUDIO_DIR/data/workers.json"
{
  "workers": [
    {"id": "w1", "profile": "$PROFILE_1", "port": 3001, "camoufox_port": 9223}
  ],
  "settings": {"recovery_hours": 6}
}
EOF
else
cat <<EOF > "$AISTUDIO_DIR/data/workers.json"
{
  "workers": [],
  "settings": {"recovery_hours": 6}
}
EOF
fi

# Create gui_config.json to ensure worker mode is enabled
cat <<EOF > "$AISTUDIO_DIR/data/gui_config.json"
{
  "fastapi_port": 2048,
  "camoufox_debug_port": 9222,
  "stream_port": 3120,
  "stream_port_enabled": true,
  "proxy_enabled": false,
  "proxy_address": "http://127.0.0.1:7890",
  "helper_enabled": false,
  "helper_endpoint": "",
  "launch_mode": "headless",
  "script_injection_enabled": false,
  "worker_mode_enabled": true,
  "log_enabled": true
}
EOF

# 3. Start AIStudio2API (Multi-worker mode via Manager)
echo "🚀 Starting AI Studio Workers Pool..."
cd "$AISTUDIO_DIR"
export PYTHONPATH=src
# Start the manager which will orchestrate workers and gateway
nohup uv run python src/app_launcher.py > ../logs/manager.log 2>&1 &
sleep 5
# Trigger the service start (Worker Mode)
curl -s -X POST http://127.0.0.1:9000/api/control/start -H "Content-Type: application/json" -d @data/gui_config.json > /dev/null
cd ..

# 4. Start Meta AI API Server (replaces grok2api)
echo "🚀 Starting Meta AI API Server..."
cd "$METAAI_DIR"
# Load cookies from .env file if present
if [ -f ".env" ]; then
    echo "  ✓ Loading cookies from .env"
    export $(grep -v '^#' .env | xargs)
fi
nohup uvicorn metaai_api.api_server:app --host 0.0.0.0 --port 8000 > ../logs/metaai.log 2>&1 &
cd ..

# 5. Wait for health check
echo "⏳ Waiting for services to initialize (30s)..."
sleep 30

# Health check
echo "🔍 Checking services..."
AISTUDIO_OK=$(curl -s http://localhost:2048/health 2>/dev/null | grep -c "ok" || true)
METAAI_OK=$(curl -s http://localhost:8000/healthz 2>/dev/null | grep -c "ok" || true)

if [ "$AISTUDIO_OK" -gt 0 ]; then
    echo "  ✓ AIStudio2API is running"
else
    echo "  ⚠ AIStudio2API not responding (image gen may fail)"
fi

if [ "$METAAI_OK" -gt 0 ]; then
    echo "  ✓ Meta AI API is running"
else
    echo "  ⚠ Meta AI API not responding (video gen may fail)"
fi

# 6. Run Bulk Pipeline
echo "🎬 Launching Bulk Processor..."
$VENV_BIN bulk_processor.py

echo "✅ Pipeline session finished."
