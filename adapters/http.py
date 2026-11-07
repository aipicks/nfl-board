"""Shared fetch helper: retries, raw-response cache, fallback to cached copy on network error."""
import time
from pathlib import Path
import requests

UA = {"User-Agent": "Mozilla/5.0 (nfl-board personal research)"}


def fetch(url: str, dest: Path, *, headers=None, params=None, retries=3, timeout=60, max_age_s=None):
    """Download url to dest. Returns (path, status) with status in fresh|cached|stale.
    max_age_s: reuse the cached file without a request if younger than this."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if max_age_s is not None and dest.exists() and time.time() - dest.stat().st_mtime < max_age_s:
        return dest, "cached"
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, headers={**UA, **(headers or {})}, params=params, timeout=timeout)
            r.raise_for_status()
            dest.write_bytes(r.content)
            return dest, "fresh"
        except requests.RequestException as e:
            last = e
            time.sleep(1.5 * (i + 1))
    if dest.exists():
        return dest, "stale"
    raise RuntimeError(f"fetch failed and no cache: {url}: {last}")
