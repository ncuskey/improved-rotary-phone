from __future__ import annotations

import base64
import json
import os
import threading
import time
from pathlib import Path
from typing import Optional

import requests

CACHE_PATH = Path.home() / ".isbn_lot_optimizer" / "ebay_bearer.json"
_LOCK = threading.Lock()


def _save_token(tok: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(tok), encoding="utf-8")


def _load_token() -> Optional[dict]:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_bearer_token(session: requests.Session | None = None) -> Optional[str]:
    """Client credentials OAuth for Browse API. Cache until near expiry."""
    client_id = os.getenv("EBAY_CLIENT_ID")
    client_secret = os.getenv("EBAY_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    sess = session or requests.Session()

    with _LOCK:
        now = int(time.time())
        cached = _load_token()
        if cached and cached.get("access_token") and now < cached.get("exp", 0) - 60:
            return cached["access_token"]

        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        response = sess.post(
            "https://api.ebay.com/identity/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data="grant_type=client_credentials&scope=https%3A%2F%2Fapi.ebay.com%2Foauth%2Fapi_scope",
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload["access_token"]
        ttl = int(payload.get("expires_in", 7200))
        _save_token({"access_token": token, "exp": now + ttl})
        return token
