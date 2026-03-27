#!/usr/bin/env python3
"""
Meta AI Cookie Manager — Cookie Rotation & Retirement.

Manages a pool of Meta AI cookie sets for video generation.
Each cookie set = {datr, abra_sess, ecto_1_sess}.

Features:
  - Round-robin rotation across cookie sets
  - Automatic retirement of failed cookies
  - Health tracking per cookie
  - JSON persistence for cookie pool state

Cookie pool file format (meta_cookies.json):
[
  {"datr": "...", "abra_sess": "...", "ecto_1_sess": "...", "label": "account_1"},
  {"datr": "...", "abra_sess": "...", "ecto_1_sess": "...", "label": "account_2"},
]
"""

import json
import os
import time
import threading
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_COOKIES_FILE = "meta_cookies.json"
FAIL_THRESHOLD = 3          # Retire after this many consecutive failures
RECOVERY_HOURS = 6          # Try retired cookies again after N hours
REQUIRED_KEYS = ["datr", "abra_sess", "ecto_1_sess"]

# ---------------------------------------------------------------------------
# Cookie Manager
# ---------------------------------------------------------------------------

class MetaCookieManager:
    """Thread-safe cookie rotation manager for Meta AI API."""

    def __init__(self, cookies_file: str = DEFAULT_COOKIES_FILE):
        self.cookies_file = Path(cookies_file)
        self._lock = threading.Lock()
        self._cookies = []        # List of cookie dicts
        self._health = {}         # label -> {fails: int, retired_at: float, successes: int}
        self._index = 0           # Round-robin index
        self._load()

    def _load(self):
        """Load cookies from JSON file."""
        if not self.cookies_file.exists():
            print(f"  ⚠ Cookie file not found: {self.cookies_file}")
            print(f"    Create {self.cookies_file} with your Meta AI cookies.")
            return

        try:
            data = json.loads(self.cookies_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self._cookies = data
            elif isinstance(data, dict) and "cookies" in data:
                self._cookies = data["cookies"]
                self._health = data.get("health", {})
            else:
                print(f"  ⚠ Invalid cookie file format: {self.cookies_file}")
                return
        except Exception as e:
            print(f"  ⚠ Failed to load cookies: {e}")
            return

        # Validate cookies
        valid = []
        for i, c in enumerate(self._cookies):
            label = c.get("label", f"cookie_{i}")
            c["label"] = label
            missing = [k for k in REQUIRED_KEYS if not c.get(k)]
            if missing:
                print(f"  ⚠ Cookie '{label}' missing keys: {missing} — skipping")
                continue
            valid.append(c)
            if label not in self._health:
                self._health[label] = {"fails": 0, "retired_at": 0, "successes": 0}

        self._cookies = valid
        print(f"  🍪 Loaded {len(self._cookies)} Meta AI cookie set(s)")

    def _save_health(self):
        """Persist health state back to the cookies file."""
        try:
            data = {
                "cookies": self._cookies,
                "health": self._health
            }
            self.cookies_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"  ⚠ Failed to save cookie health: {e}")

    def _is_retired(self, label: str) -> bool:
        """Check if a cookie is currently retired."""
        health = self._health.get(label, {})
        if health.get("fails", 0) < FAIL_THRESHOLD:
            return False
        retired_at = health.get("retired_at", 0)
        if retired_at and (time.time() - retired_at) > RECOVERY_HOURS * 3600:
            # Recovery period elapsed — try again
            return False
        return True

    @property
    def pool_size(self) -> int:
        """Total cookies in pool (including retired)."""
        return len(self._cookies)

    @property
    def active_count(self) -> int:
        """Number of non-retired cookies."""
        return sum(1 for c in self._cookies if not self._is_retired(c["label"]))

    def get_next(self) -> Optional[dict]:
        """Get the next available (non-retired) cookie set.

        Returns None if all cookies are retired.
        """
        with self._lock:
            if not self._cookies:
                return None

            n = len(self._cookies)
            for _ in range(n):
                cookie = self._cookies[self._index % n]
                self._index += 1
                label = cookie["label"]

                if self._is_retired(label):
                    # Check if recovery period has passed
                    health = self._health.get(label, {})
                    retired_at = health.get("retired_at", 0)
                    if retired_at and (time.time() - retired_at) > RECOVERY_HOURS * 3600:
                        # Reset and try again
                        health["fails"] = 0
                        health["retired_at"] = 0
                        print(f"    🔄 Cookie '{label}' recovered — trying again")
                    else:
                        continue

                return {
                    "datr": cookie["datr"],
                    "abra_sess": cookie["abra_sess"],
                    "ecto_1_sess": cookie["ecto_1_sess"],
                    "label": label,
                }

            return None  # All retired

    def report_success(self, label: str):
        """Mark a cookie as successful (reset fail counter)."""
        with self._lock:
            if label in self._health:
                self._health[label]["fails"] = 0
                self._health[label]["retired_at"] = 0
                self._health[label]["successes"] = self._health[label].get("successes", 0) + 1
            self._save_health()

    def report_failure(self, label: str, reason: str = ""):
        """Mark a cookie as failed. Retires after FAIL_THRESHOLD consecutive failures."""
        with self._lock:
            if label not in self._health:
                self._health[label] = {"fails": 0, "retired_at": 0, "successes": 0}

            self._health[label]["fails"] += 1
            fails = self._health[label]["fails"]

            if fails >= FAIL_THRESHOLD:
                self._health[label]["retired_at"] = time.time()
                print(f"    🚫 Cookie '{label}' RETIRED after {fails} consecutive failures")
                if reason:
                    print(f"       Last error: {reason}")
            else:
                print(f"    ⚠ Cookie '{label}' failure {fails}/{FAIL_THRESHOLD}")

            self._save_health()

    def get_status(self) -> dict:
        """Return current pool status."""
        with self._lock:
            statuses = []
            for c in self._cookies:
                label = c["label"]
                health = self._health.get(label, {})
                statuses.append({
                    "label": label,
                    "fails": health.get("fails", 0),
                    "successes": health.get("successes", 0),
                    "retired": self._is_retired(label),
                })
            return {
                "total": len(self._cookies),
                "active": self.active_count,
                "cookies": statuses,
            }


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def create_example_cookies_file(path: str = DEFAULT_COOKIES_FILE):
    """Create an example meta_cookies.json template."""
    example = [
        {
            "label": "account_1",
            "datr": "YOUR_DATR_COOKIE_HERE",
            "abra_sess": "YOUR_ABRA_SESS_COOKIE_HERE",
            "ecto_1_sess": "YOUR_ECTO_1_SESS_COOKIE_HERE"
        },
        {
            "label": "account_2",
            "datr": "YOUR_DATR_COOKIE_HERE",
            "abra_sess": "YOUR_ABRA_SESS_COOKIE_HERE",
            "ecto_1_sess": "YOUR_ECTO_1_SESS_COOKIE_HERE"
        }
    ]
    Path(path).write_text(json.dumps(example, indent=2), encoding="utf-8")
    print(f"Created example cookies file: {path}")
    print("Edit this file with your Meta AI cookies from https://meta.ai")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--create-example":
        create_example_cookies_file()
    else:
        mgr = MetaCookieManager()
        print(json.dumps(mgr.get_status(), indent=2))
