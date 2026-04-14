"""Cryptographic hashing utilities for incremental document and chunk tracking."""

import hashlib
import re


def compute_sha256(content: str | bytes) -> str:
    """Compute the SHA256 hex digest for string or byte content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def normalize_query_for_cache(query: str) -> str:
    """
    Normalize user query string to generate stable cache keys:
    - Lowercase
    - Strip leading/trailing whitespaces and normalize internal whitespace
    - Strip trailing punctuation (?, !, .)
    """
    q = query.strip().lower()
    # Strip terminal punctuation
    q = re.sub(r"[?!.,:;]+$", "", q)
    # Collapse multiple whitespaces
    q = re.sub(r"\s+", " ", q).strip()
    return q


def compute_cache_key(index_version: int, mode: str, query: str) -> str:
    """Generate version-namespaced Redis cache key."""
    q_hash = compute_sha256(normalize_query_for_cache(query))
    return f"docsqa:cache:v{index_version}:{mode}:{q_hash}"
