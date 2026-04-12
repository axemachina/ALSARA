# shared/cache.py
"""Simple in-memory cache for API responses"""

import time
import hashlib
import json
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)


class SimpleCache:
    """Simple TTL-based in-memory cache with size limits"""

    def __init__(self, ttl: int = 3600, max_size: int = 100):
        """
        Initialize cache with TTL and size limits

        Args:
            ttl: Time to live in seconds (default: 1 hour)
            max_size: Maximum number of cached entries (default: 100)
        """
        self.cache = {}
        self.ttl = ttl
        self.max_size = max_size

    def _make_key(self, tool_name: str, arguments: dict) -> str:
        """Create cache key from tool name and arguments"""
        # Sort dict for consistent hashing
        args_str = json.dumps(arguments, sort_keys=True)
        key_str = f"{tool_name}:{args_str}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, tool_name: str, arguments: dict) -> Optional[str]:
        """Get cached result if available and not expired"""
        key = self._make_key(tool_name, arguments)

        if key in self.cache:
            result, timestamp = self.cache[key]

            # Check if expired
            if time.time() - timestamp < self.ttl:
                logger.info(f"Cache HIT for {tool_name}")
                return result
            else:
                # Remove expired entry
                del self.cache[key]
                logger.info(f"Cache EXPIRED for {tool_name}")

        logger.info(f"Cache MISS for {tool_name}")
        return None

    def set(self, tool_name: str, arguments: dict, result: str) -> None:
        """Store result in cache with LRU eviction if at capacity"""
        key = self._make_key(tool_name, arguments)

        # Check if we need to evict an entry
        if len(self.cache) >= self.max_size and key not in self.cache:
            # Find and remove oldest entry (LRU based on timestamp)
            if self.cache:  # Safety check
                oldest_key = min(self.cache.keys(),
                               key=lambda k: self.cache[k][1])
                del self.cache[oldest_key]
                logger.debug(f"Evicted oldest cache entry to maintain size limit")

        self.cache[key] = (result, time.time())
        logger.debug(f"Cached result for {tool_name} (cache size: {len(self.cache)}/{self.max_size})")

    def clear(self) -> None:
        """Clear all cache entries"""
        self.cache.clear()
        logger.info("Cache cleared")

    def size(self) -> int:
        """Get number of cached items"""
        return len(self.cache)

    def cleanup_expired(self) -> int:
        """Remove all expired entries and return count of removed items"""
        expired_keys = []
        current_time = time.time()

        for key, (result, timestamp) in self.cache.items():
            if current_time - timestamp >= self.ttl:
                expired_keys.append(key)

        for key in expired_keys:
            del self.cache[key]

        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")

        return len(expired_keys)
