"""Hashed API keys. The plaintext is shown once at issue time, never stored."""

from __future__ import annotations

import hashlib
import hmac
import secrets


def generate_api_key() -> str:
    return "hm_" + secrets.token_urlsafe(32)


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()


def key_prefix(raw: str) -> str:
    body = raw.strip()
    return body[:16] + "…" if len(body) > 16 else body


def hashes_match(provided: str, stored_hash: str) -> bool:
    digest = hash_api_key(provided)
    if len(digest) != len(stored_hash):
        return False
    return hmac.compare_digest(digest, stored_hash)
