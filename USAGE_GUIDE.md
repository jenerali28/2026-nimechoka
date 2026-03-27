# Video Clone Pipeline — Usage Guide

This guide covers the advanced features of the pipeline, including bulk processing, automated cookie management, state tracking, and high-fidelity synchronization.

## ⚡ 0. Quick Start (Everything)
You can now start all services and the entire bulk processing pipeline with a single command:
```bash
./init_and_run.sh
```
This script handles stopping old processes, starting workers, and triggering the processor.

---

## 📥 1. Bulk YouTube Video Downloader
Before processing, you can download videos directly into the `input_videos/` directory.

### How to use:
```bash
python utils/download_shorts.py [URL or CHANNEL_URL] --limit 5
```

---

## 🔄 2. Tight Sync (Whisper Alignment)
The pipeline now uses **Whisper AI** to perfectly align audio and video.
1.  **Single Audio**: It generates one full Spanish narration file (Step 4).
2.  **Transcription**: It uses a local Whisper model to transcribe that audio and find exact timestamps for each sentence.
3.  **Speed Matching**: Each visual clip is automatically slowed down or sped up to match those timestamps precisely.

---

## 👥 3. Multi-Worker Setup (Load Balancing)
The pipeline is pre-configured for **2 Workers**. This allows the API to handle more requests simultaneously.

### Adding a second account:
1.  Run AIStudio2API in debug mode manually:
    ```bash
    cd AIStudio2API && uv run python src/launch_camoufox.py --debug --server-port 2049
    ```
2.  Login with your second Google account.
3.  The new profile will be saved in `data/auth_profiles/saved/`.
4.  Update `AIStudio2API/data/workers.json` to point `w2` to your new profile file.

---

## 🍪 4. Grok Cookie Management
Manage Grok cookies in bulk:
```bash
python utils/manage_grok_cookies.py
```
*   **Auto-Retire**: Cookies are retired after **2 consecutive failures**.

---

## 📊 5. Tracking & Resuming
*   **State Tracking**: Progress is saved in `status.json`. Completed steps are skipped on rerun.
*   **Consolidated Metadata**: Each video folder contains a `full_metadata.json` with all scripts, prompts, and asset paths.
