#!/bin/bash
# Complete workflow: Regenerate prompts and resume video generation

set -e  # Exit on error

PROJECT_DIR="outputs/Why it Sucks to Be an Egyptian Concubine"
PROMPTS_FILE="$PROJECT_DIR/prompts.yaml"
SCRIPT_FILE="$PROJECT_DIR/spanish_script.txt"
CLIPS_DIR="$PROJECT_DIR/clips"
PROGRESS_FILE="$PROJECT_DIR/video_generation_progress.json"

echo "=========================================="
echo "  Complete Video Generation Workflow"
echo "=========================================="
echo ""

# Step 1: Check current status
echo "📊 Current Status:"
if [ -f "$PROGRESS_FILE" ]; then
    COMPLETED=$(jq -r '.completed_scenes | length' "$PROGRESS_FILE")
    TOTAL=$(jq -r '.total_scenes' "$PROGRESS_FILE")
    NEXT=$(jq -r '.next_scene_to_generate' "$PROGRESS_FILE")
    echo "  ✓ Progress file found"
    echo "  ✓ Completed: $COMPLETED/$TOTAL scenes"
    echo "  ✓ Next scene: $NEXT"
else
    echo "  ⚠ No progress file found"
    NEXT=33
fi

echo ""
read -p "Do you want to regenerate video prompts for scenes $NEXT-200? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "=========================================="
    echo "  Step 1: Regenerating Video Prompts"
    echo "=========================================="
    echo ""
    
    uv run regenerate_video_prompts_preserve_style.py \
        --prompts-file "$PROMPTS_FILE" \
        --script-file "$SCRIPT_FILE" \
        --start-scene "$NEXT"
    
    if [ $? -ne 0 ]; then
        echo ""
        echo "❌ Prompt regeneration failed!"
        exit 1
    fi
    
    echo ""
    echo "🎨 Fixing prompt format to include MS Paint style..."
    uv run fix_video_prompts_format.py --prompts-file "$PROMPTS_FILE"
    
    echo ""
    echo "✅ Prompts regenerated successfully!"
    echo ""
fi

echo ""
read -p "Do you want to start video generation now? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "=========================================="
    echo "  Step 2: Generating Videos"
    echo "=========================================="
    echo ""
    
    uv run utils/generate_videos.py \
        "$PROMPTS_FILE" \
        -o "$CLIPS_DIR" \
        --resume \
        --grok-api-base "http://localhost:8001" \
        --retries 5
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ All videos generated successfully!"
    elif [ $? -eq 1 ]; then
        echo ""
        echo "⚠ Some videos failed but enough exist for assembly"
    else
        echo ""
        echo "❌ Too many videos failed - check logs"
        exit 1
    fi
fi

echo ""
echo "=========================================="
echo "  Workflow Complete"
echo "=========================================="
echo ""

# Show final status
if [ -f "$PROGRESS_FILE" ]; then
    echo "📊 Final Status:"
    COMPLETED=$(jq -r '.completed_scenes | length' "$PROGRESS_FILE")
    FAILED=$(jq -r '.failed_scenes | length' "$PROGRESS_FILE")
    TOTAL=$(jq -r '.total_scenes' "$PROGRESS_FILE")
    echo "  ✓ Completed: $COMPLETED/$TOTAL"
    echo "  ✗ Failed: $FAILED"
    echo ""
    
    if [ $COMPLETED -eq $TOTAL ]; then
        echo "🎉 All scenes completed! Ready for final assembly."
    else
        REMAINING=$((TOTAL - COMPLETED))
        echo "📝 $REMAINING scenes remaining"
        echo ""
        echo "To continue later, run:"
        echo "  ./complete_video_workflow.sh"
    fi
fi
