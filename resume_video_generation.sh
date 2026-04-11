#!/bin/bash
# Resume video generation from last checkpoint

PROJECT_DIR="outputs/Why it Sucks to Be an Egyptian Concubine"
PROMPTS_FILE="$PROJECT_DIR/prompts.yaml"
CLIPS_DIR="$PROJECT_DIR/clips"

echo "=========================================="
echo "  Resume Video Generation"
echo "=========================================="

# Check if progress file exists
if [ -f "$PROJECT_DIR/video_generation_progress.json" ]; then
    echo "✓ Found progress file"
    NEXT_SCENE=$(jq -r '.next_scene_to_generate' "$PROJECT_DIR/video_generation_progress.json")
    COMPLETED=$(jq -r '.completed_scenes | length' "$PROJECT_DIR/video_generation_progress.json")
    TOTAL=$(jq -r '.total_scenes' "$PROJECT_DIR/video_generation_progress.json")
    echo "  Progress: $COMPLETED/$TOTAL scenes completed"
    echo "  Next scene: $NEXT_SCENE"
else
    echo "⚠ No progress file found - will start from scene 1"
fi

echo ""
echo "Starting video generation..."
echo ""

# Run the video generator with resume flag
uv run utils/generate_videos.py \
    "$PROMPTS_FILE" \
    -o "$CLIPS_DIR" \
    --resume \
    --grok-api-base "http://localhost:8001" \
    --retries 5

echo ""
echo "=========================================="
echo "  Generation Complete"
echo "=========================================="

# Show final status
if [ -f "$PROJECT_DIR/video_generation_progress.json" ]; then
    COMPLETED=$(jq -r '.completed_scenes | length' "$PROJECT_DIR/video_generation_progress.json")
    FAILED=$(jq -r '.failed_scenes | length' "$PROJECT_DIR/video_generation_progress.json")
    TOTAL=$(jq -r '.total_scenes' "$PROJECT_DIR/video_generation_progress.json")
    echo "  Completed: $COMPLETED/$TOTAL"
    echo "  Failed: $FAILED"
fi
