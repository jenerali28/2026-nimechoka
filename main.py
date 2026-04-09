#!/usr/bin/env python3
"""
Video Clone Pipeline — Main Orchestrator.

Connects all pipeline components to clone an English video into a Spanish version:

    1. Extract audio + transcribe (FFmpeg + Whisper)
    2. Analyze video visually (SEALCaM via AIStudio2API)
    3. Rewrite script to Spanish (AIStudio2API)
    4. Generate Spanish narration audio (AIStudio2API TTS)
    5. Generate image + video prompts from analysis
    6. Generate scene images (Imagen 3 via AIStudio2API)
    7. Generate video clips (Meta AI API — image-to-video with cookie rotation)
    8. Combine clips + overlay narration audio

Usage:
    python main.py input_videos/video.mp4
    python main.py input_videos/video.mp4 --output-dir outputs/
    python main.py input_videos/video.mp4 --skip-services
"""

import argparse
import math
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
UTILS_DIR = SCRIPT_DIR / "utils"

AISTUDIO_DIR = SCRIPT_DIR / "AIStudio2API"
METAAI_DIR = SCRIPT_DIR / "metaai-api"

DEFAULT_AISTUDIO_PORT = 2048
DEFAULT_META_PORT = 8000
DEFAULT_OUTPUT_DIR = "outputs"
DEFAULT_INPUT_DIR = "input_videos"

# Service health check URLs
AISTUDIO_HEALTH_URL = "http://localhost:{port}/v1/chat/completions"
METAAI_HEALTH_URL = "http://localhost:{port}/healthz"


# ---------------------------------------------------------------------------
# Service Management
# ---------------------------------------------------------------------------

_service_processes: list[subprocess.Popen] = []


def _cleanup_services():
    """Terminate all managed service processes on exit."""
    for proc in _service_processes:
        if proc.poll() is None:
            print(f"  Stopping service (PID: {proc.pid})...")
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass
    _service_processes.clear()


def _signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    print("\n\n⚠ Interrupted. Cleaning up services...")
    _cleanup_services()
    sys.exit(1)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def wait_for_service(url: str, name: str, timeout: int = 120) -> bool:
    """Wait for a service to become responsive.

    Does a simple connection probe (we don't need a full valid request,
    just need the server to be accepting connections).
    """
    import socket

    # Parse host and port from url
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 80

    print(f"  Waiting for {name} on port {port}...")
    start = time.time()

    while time.time() - start < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                elapsed = time.time() - start
                print(f"  ✓ {name} is ready ({elapsed:.1f}s)")
                return True
        except Exception:
            pass
        time.sleep(2)

    print(f"  ✗ {name} did not start within {timeout}s")
    return False


def is_port_open(port: int) -> bool:
    """Check if a service is already running on the given port."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex(("localhost", port))
    sock.close()
    return result == 0


def start_aistudio(port: int = DEFAULT_AISTUDIO_PORT) -> bool:
    """Start AIStudio2API service (headless mode)."""
    if is_port_open(port):
        print(f"  ✓ AIStudio2API already running on port {port}")
        return True

    print(f"  Starting AIStudio2API on port {port}...")

    if not AISTUDIO_DIR.exists():
        print(f"  ✗ AIStudio2API directory not found: {AISTUDIO_DIR}")
        return False

    env = os.environ.copy()
    env["PYTHONPATH"] = str(AISTUDIO_DIR / "src") + os.pathsep + env.get("PYTHONPATH", "")

    # Check if uv is available
    uv_path = _find_uv()

    if uv_path:
        cmd = [
            uv_path, "run", "python",
            str(AISTUDIO_DIR / "src" / "launch_camoufox.py"),
            "--headless",
            "--server-port", str(port),
        ]
    else:
        cmd = [
            sys.executable,
            str(AISTUDIO_DIR / "src" / "launch_camoufox.py"),
            "--headless",
            "--server-port", str(port),
        ]

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(AISTUDIO_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        _service_processes.append(proc)
        print(f"  Launched AIStudio2API (PID: {proc.pid})")

        # Wait for it to be ready
        return wait_for_service(
            f"http://localhost:{port}",
            "AIStudio2API",
            timeout=120,
        )
    except Exception as e:
        print(f"  ✗ Failed to start AIStudio2API: {e}")
        return False


def start_metaai(port: int = DEFAULT_META_PORT) -> bool:
    """Start Meta AI API server."""
    if is_port_open(port):
        print(f"  ✓ Meta AI API already running on port {port}")
        return True

    print(f"  Starting Meta AI API on port {port}...")

    if not METAAI_DIR.exists():
        print(f"  ✗ metaai-api directory not found: {METAAI_DIR}")
        return False

    env = os.environ.copy()
    env["SERVER_PORT"] = str(port)

    # Load .env file from metaai-api directory if it exists
    env_file = METAAI_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                env[key.strip()] = val.strip()

    try:
        cmd = [
            sys.executable, "-m", "uvicorn",
            "metaai_api.api_server:app",
            "--host", "0.0.0.0",
            "--port", str(port),
        ]
        proc = subprocess.Popen(
            cmd,
            cwd=str(METAAI_DIR / "src"),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        _service_processes.append(proc)
        print(f"  Launched Meta AI API (PID: {proc.pid})")

        return wait_for_service(
            f"http://localhost:{port}",
            "Meta AI API",
            timeout=60,
        )
    except Exception as e:
        print(f"  ✗ Failed to start Meta AI API: {e}")
        return False


def _find_uv() -> str | None:
    """Find the uv package manager executable."""
    import shutil
    return shutil.which("uv")


# ---------------------------------------------------------------------------
# Pipeline Steps
# ---------------------------------------------------------------------------


def run_step(step_name: str, cmd: list[str], cwd: str | None = None) -> bool:
    """Run a pipeline step as a subprocess.

    Returns True on success, False on failure.
    """
    print(f"\n  Running: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=False,  # Let output flow to the terminal
    )

    if result.returncode != 0:
        print(f"\n  ✗ {step_name} failed (exit code {result.returncode})")
        return False

    return True


def pipeline(
    video_path: Path,
    output_dir: Path,
    api_base: str,
    meta_api_base: str,
    whisper_model: str,
    ai_model: str,
    tts_voice: str,
    skip_services: bool,
    aistudio_port: int,
    meta_port: int,
):
    """Execute the full video clone pipeline."""

    python = sys.executable

    # Define output paths
    script_dir = output_dir / "script"
    audio_dir = output_dir / "audio"
    analysis_file = output_dir / "analysis.yaml"
    english_script = script_dir / "english_script.txt"
    spanish_script = script_dir / "spanish_script.txt"
    prompts_file = output_dir / "prompts.yaml"
    images_dir = output_dir / "images"
    clips_dir = output_dir / "clips"
    keyframes_dir = output_dir / "keyframes"
    narration_file = audio_dir / "narration.wav"
    final_video = output_dir / "final_video.mp4"

    # Create directories
    for d in [script_dir, audio_dir, images_dir, clips_dir, keyframes_dir]:
        d.mkdir(parents=True, exist_ok=True)

    total_steps = 8
    step = 0

    # Helper: get duration of media file via ffprobe
    def _get_duration(path: Path) -> float:
        import shutil
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return 0.0
        try:
            result = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                capture_output=True, text=True, timeout=30
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    # ======================================================================
    # Step 0: Start services (if not skipped)
    # ======================================================================
    if not skip_services:
        print("\n" + "=" * 60)
        print("  [0/8] Starting API Services")
        print("=" * 60)

        # AIStudio2API skipped - no longer used for TTS, script rewrite, or images
        print("  (AIStudio2API skipped - no longer needed for current pipeline)")

        meta_ok = start_metaai(meta_port)
        if not meta_ok:
            print("\n  ⚠ Meta AI API failed to start.")
            print("    You can start it manually and re-run with --skip-services")
            answer = input("    Continue anyway? (y/n): ").strip().lower()
            if answer != "y":
                return False

    # ======================================================================
    # Step 1: Extract audio + transcribe
    # ======================================================================
    step += 1
    print("\n" + "=" * 60)
    print(f"  [{step}/{total_steps}] Extract Audio & Transcribe (Whisper)")
    print("=" * 60)

    ok = run_step("Extract Script", [
        python, str(UTILS_DIR / "extract_script.py"),
        str(video_path),
        "-o", str(english_script),
        "--whisper-model", whisper_model,
        "--audio-output", str(audio_dir / "original_audio.wav"),
    ])
    if not ok:
        print("  \u2717 Script extraction failed. Cannot continue with audio pipeline.")
        return False

    # ======================================================================
    # Step 2: Gemini Multimodal Flow (Analysis only — prompts come later)
    # ======================================================================
    step += 1
    print("\n" + "=" * 60)
    print(f"  [{step}/{total_steps}] Gemini Multimodal Flow (Analysis)")
    print("=" * 60)

    # Note: We run multimodal with prompts AFTER TTS so we know clip count.
    # For now, just do analysis. We'll generate prompts after TTS.

    # ======================================================================
    # Step 3: Extract Reference Keyframes (SKIPPED in text-to-video mode)
    # ======================================================================
    # step += 1
    # print("\n" + "=" * 60)
    # print(f"  [{step}/{total_steps}] Extract Reference Keyframes")
    # ...

    # ======================================================================
    # Step 4: Rewrite script to Spanish
    # ======================================================================
    step += 1
    print("\n" + "=" * 60)
    print(f"  [{step}/{total_steps}] Rewrite Script \u2192 Spanish")
    print("=" * 60)

    ok = run_step("Rewrite Script", [
        python, str(UTILS_DIR / "rewrite_script.py"),
        str(english_script),
        "-o", str(spanish_script),
        "--api-base", api_base,
        "--model", ai_model,
    ])
    if not ok:
        print("  \u2717 Script rewriting failed.")
        return False

    # ======================================================================
    # Step 5: Generate Spanish narration audio (TTS — BEFORE prompts)
    # ======================================================================
    step += 1
    print("\n" + "=" * 60)
    print(f"  [{step}/{total_steps}] Generate Spanish Narration Audio (TTS)")
    print("=" * 60)

    audio_chunks_dir = audio_dir / "audio_chunks"
    manifest_file = audio_chunks_dir / "chunks_manifest.json"

    ok = run_step("Generate Audio", [
        python, str(UTILS_DIR / "generate_audio_chunks.py"),
        str(spanish_script),
        "-o", str(audio_chunks_dir),
        "--api-base", api_base,
        "--voice", tts_voice,
        "--language", "es"
    ])
    if not ok:
        print("  \u2717 Audio generation failed.")
        return False

    if manifest_file.exists():
        import json
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        clip_count = manifest.get("total_clips", 0)
        narration_duration = manifest.get("total_duration", 0)
        narration_file = audio_chunks_dir / manifest.get("combined_audio", "narration.wav")
    else:
        print("  ❌ Chunked audio generation manifest missing")
        return False

    CLIP_LENGTH = 6  # seconds per video clip
    coverage = clip_count * CLIP_LENGTH
    print(f"  🎬 Narration: {narration_duration:.1f}s → {clip_count} clips × {CLIP_LENGTH}s = {coverage}s")

    # ======================================================================
    # Step 2 (continued): Generate Prompts with clip count (batched)
    # ======================================================================
    print("\n" + "=" * 60)
    print(f"  [2/{total_steps}] Gemini Multimodal Flow (Analysis + {clip_count}-Scene Prompts)")
    print("=" * 60)

    ok = run_step("Gemini Multimodal Flow", [
        python, str(UTILS_DIR / "multimodal_orchestrator.py"),
        str(video_path),
        str(analysis_file),
        str(prompts_file),
        "--clip-count", str(clip_count),
        "--script", str(spanish_script),
    ])
    if not ok:
        print("  \u2717 Multimodal flow failed. Cannot continue.")
        return False

    # ======================================================================
    # Step 6: Generate scene images (SKIPPED in text-to-video mode)
    # ======================================================================
    # step += 1
    # print("\n" + "=" * 60)
    # print(f"  [{step}/{total_steps}] Generate Scene Images")
    # ...

    # ======================================================================
    # Step 7: Generate video clips (Meta AI — Text-to-Video)
    # ======================================================================
    step += 1
    print("\n" + "=" * 60)
    print(f"  [{step}/{total_steps}] Generate Video Clips (Meta AI — Text-to-Video)")
    print("=" * 60)

    gen_videos_cmd = [
        python, str(UTILS_DIR / "generate_videos.py"),
        str(prompts_file),
        "-o", str(clips_dir),
        "--meta-api-base", meta_api_base,
        "--retries", "5",
    ]
    if analysis_file.exists():
        gen_videos_cmd.extend(["--analysis-file", str(analysis_file)])
    
    # We NO LONGER pass --images-dir here
    
    ok = run_step("Generate Videos", gen_videos_cmd)
    if not ok:
        print("  Video generation failed.")
        return False

    # ======================================================================
    # Step 8: Combine clips at native speed + overlay narration
    # ======================================================================
    step += 1
    print("\n" + "=" * 60)
    print(f"  [{step}/{total_steps}] Combine Clips + Narration Audio (Native Speed)")
    print("=" * 60)

    combine_cmd = [
        python, str(UTILS_DIR / "combine_all.py"),
        "--clips-dir", str(clips_dir),
        "--prompts-file", str(prompts_file),
        "-o", str(final_video),
    ]

    # Add narration as background music/audio if it was generated
    if narration_file.exists():
        combine_cmd.extend(["--music", str(narration_file)])
        
    if manifest_file.exists():
        combine_cmd.extend(["--chunk-manifest", str(manifest_file)])

    ok = run_step("Combine All", combine_cmd)
    if not ok:
        print("  \u2717 Video combining failed.")
        return False

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Video Clone Pipeline — Clone an English video into Spanish.\n\n"
            "Orchestrates the full pipeline: transcription → Spanish rewrite → "
            "TTS narration → visual analysis → image generation → video generation → final assembly."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py input_videos/video.mp4\n"
            "  python main.py input_videos/video.mp4 --output-dir outputs/\n"
            "  python main.py input_videos/video.mp4 --skip-services\n"
            "  python main.py input_videos/video.mp4 --whisper-model medium --voice Fenrir\n"
        ),
    )
    parser.add_argument(
        "video_path",
        type=str,
        help="Path to the input video file (English)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Base output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--api-base",
        type=str,
        default=os.environ.get("API_BASE_URL", f"http://localhost:{DEFAULT_AISTUDIO_PORT}"),
        help="AIStudio2API base URL (default: $API_BASE_URL or http://localhost:2048)",
    )
    parser.add_argument(
        "--meta-api-base",
        type=str,
        default=os.environ.get("META_API_BASE", f"http://localhost:{DEFAULT_META_PORT}"),
        help="Meta AI API base URL (default: $META_API_BASE or http://localhost:8000)",
    )
    parser.add_argument(
        "--aistudio-port",
        type=int,
        default=DEFAULT_AISTUDIO_PORT,
        help=f"Port for AIStudio2API (default: {DEFAULT_AISTUDIO_PORT})",
    )
    parser.add_argument(
        "--meta-port",
        type=int,
        default=DEFAULT_META_PORT,
        help=f"Port for Meta AI API (default: {DEFAULT_META_PORT})",
    )
    # BWC
    parser.add_argument("--grok-api-base", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--grok-port", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--whisper-model",
        type=str,
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size for transcription (default: base)",
    )
    parser.add_argument(
        "--ai-model",
        type=str,
        default="moonshotai/kimi-k2.5",
        help="AI model for analysis and rewriting (default: moonshotai/kimi-k2.5)",
    )
    parser.add_argument(
        "--voice",
        type=str,
        default="Charon",
        help="TTS voice for Spanish narration (default: Charon — deep male voice)",
    )
    parser.add_argument(
        "--skip-services",
        action="store_true",
        help="Skip starting AIStudio2API and Meta AI API (assume they're already running)",
    )

    args = parser.parse_args()

    # -- Validate input --
    video_path = Path(args.video_path).resolve()
    if not video_path.exists():
        print(f"Error: Video file not found: {video_path}")
        sys.exit(1)

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # -- Grand Banner --
    print("\n" + "█" * 60)
    print("█" + " " * 58 + "█")
    print("█   VIDEO CLONE PIPELINE — English → Spanish              █")
    print("█" + " " * 58 + "█")
    print("█" * 60)
    print(f"\n  Input Video   : {video_path.name}")
    print(f"  Output Dir    : {output_dir}")
    print(f"  AIStudio API  : {args.api_base}")
    meta_api_base = args.meta_api_base or args.grok_api_base or f"http://localhost:{DEFAULT_META_PORT}"
    meta_port = args.meta_port or args.grok_port or DEFAULT_META_PORT
    print(f"  Meta AI API   : {meta_api_base}")
    print(f"  Whisper Model : {args.whisper_model}")
    print(f"  AI Model      : {args.ai_model}")
    print(f"  TTS Voice     : {args.voice}")
    print(f"  Auto-start    : {'No (--skip-services)' if args.skip_services else 'Yes'}")
    print()

    start_time = time.time()

    try:
        success = pipeline(
            video_path=video_path,
            output_dir=output_dir,
            api_base=args.api_base,
            meta_api_base=meta_api_base,
            whisper_model=args.whisper_model,
            ai_model=args.ai_model,
            tts_voice=args.voice,
            skip_services=args.skip_services,
            aistudio_port=args.aistudio_port,
            meta_port=meta_port,
        )
    finally:
        # Always clean up services
        _cleanup_services()

    elapsed = time.time() - start_time
    minutes = int(elapsed) // 60
    seconds = int(elapsed) % 60

    print("\n" + "█" * 60)
    if success:
        final_video = output_dir / "final_video.mp4"
        print("█" + " " * 58 + "█")
        print("█   ✅ PIPELINE COMPLETE                                   █")
        print("█" + " " * 58 + "█")
        print("█" * 60)
        print(f"\n  Final Video  : {final_video}")
        print(f"  Total Time   : {minutes}m {seconds}s")
        print(f"  Output Dir   : {output_dir}")
        print(f"\n  Generated files:")
        for f in sorted(output_dir.rglob("*")):
            if f.is_file():
                size = f.stat().st_size
                if size > 1_048_576:
                    size_str = f"{size / 1_048_576:.1f} MB"
                elif size > 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size} B"
                rel = f.relative_to(output_dir)
                print(f"    {rel}  ({size_str})")
    else:
        print("█" + " " * 58 + "█")
        print("█   ✗ PIPELINE FAILED                                      █")
        print("█" + " " * 58 + "█")
        print("█" * 60)
        print(f"\n  Elapsed Time : {minutes}m {seconds}s")
        print("  Check the output above for error details.")
        sys.exit(1)

    print("\nDone.")


if __name__ == "__main__":
    main()
