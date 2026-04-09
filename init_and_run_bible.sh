#!/bin/bash

# =============================================================================
# Bible Narration Pipeline — Master Orchestrator
# Generates Swahili Bible narration videos for Tanzanian audience.
# 
# Usage: ./init_and_run_bible.sh [count]
#   count = number of videos to generate (default: 1)
#
# This is SEPARATE from init_and_run.sh (the Spanish clone pipeline).
# =============================================================================

VIDEO_COUNT="${1:-1}"

# Configuration
AISTUDIO_DIR="AIStudio2API"
METAAI_DIR="metaai-api"
VENV_BIN=".venv/bin/python"

echo "============================================================"
echo "  📖 Bible Narration Pipeline — Swahili / Tanzania"
echo "  Videos to generate: $VIDEO_COUNT"
echo "============================================================"

# 1. Kill any existing instances
echo "🛑 Stopping existing services and clearing ports..."
pkill -9 -f "launch_camoufox.py"
pkill -9 -f "metaai-api"
pkill -9 -f "api_server:app"
pkill -9 -f "bible_pipeline.py"
pkill -9 -f "app_launcher.py"
pkill -9 -f "gateway.py"
pkill -9 -f "grok2api/main.py"

# Force kill processes on key ports
fuser -k 9000/tcp 2048/tcp 8000/tcp 3001/tcp 3002/tcp 3003/tcp 3004/tcp 9222/tcp 9223/tcp 9224/tcp 9225/tcp 9226/tcp 2>/dev/null || true

sleep 2

# 2. Start Meta AI API Server (replaces grok2api)
echo "🚀 Starting Meta AI API Server..."
cd "$METAAI_DIR"
# Load cookies from .env file if present
if [ -f ".env" ]; then
    echo "  ✓ Loading cookies from .env"
    export $(grep -v '^#' .env | xargs)
fi
nohup uvicorn metaai_api.api_server:app --host 0.0.0.0 --port 8000 > ../logs/metaai.log 2>&1 &
cd ..

# 3. Wait for health check
echo "⏳ Waiting for services to initialize (15s)..."
sleep 15

# Health check
echo "🔍 Checking services..."
METAAI_OK=$(curl -s http://localhost:8000/healthz 2>/dev/null | grep -c "ok" || true)

if [ "$METAAI_OK" -gt 0 ]; then
    echo "  ✓ Meta AI API is running (video generation)"
else
    echo "  ⚠ Meta AI API not responding (video gen may fail)"
fi

if [ "$METAAI_OK" -gt 0 ]; then
    echo "  ✓ Meta AI API is running (video generation)"
else
    echo "  ⚠ Meta AI API not responding (video gen may fail)"
fi

# 6. Create logs directory
mkdir -p logs

# 7. Run Bible Pipeline
echo "📖 Launching Bible Narration Pipeline..."
export PYTHONPATH="$(pwd):$PYTHONPATH"
$VENV_BIN bible/bible_pipeline.py --count "$VIDEO_COUNT"

echo "✅ Bible Pipeline session finished."
