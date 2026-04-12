#!/usr/bin/env python3
"""
Shared HTTP client with connection pooling for better performance.
All MCP servers should use this instead of creating new clients for each request.
"""

import httpx
from typing import Optional

# Global HTTP client with connection pooling
# This maintains persistent connections to servers for faster subsequent requests
_http_client: Optional[httpx.AsyncClient] = None

def get_http_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """
    Get the shared HTTP client with connection pooling.

    NOTE: For different timeout values, use CustomHTTPClient context manager
    instead to avoid conflicts between servers.

    Args:
        timeout: Request timeout in seconds (default 30)

    Returns:
        Shared httpx.AsyncClient instance
    """
    global _http_client

    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(
                max_connections=100,      # Maximum number of connections
                max_keepalive_connections=20,  # Keep 20 connections alive for reuse
                keepalive_expiry=300      # Keep connections alive for 5 minutes
            ),
            # Follow redirects by default
            follow_redirects=True
        )

    return _http_client

async def close_http_client():
    """Close the shared HTTP client (call on shutdown)."""
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None

# Context manager for temporary clients with custom settings
class CustomHTTPClient:
    """Context manager for creating temporary HTTP clients with custom settings."""

    def __init__(self, timeout: float = 30.0, **kwargs):
        self.timeout = timeout
        self.kwargs = kwargs
        self.client = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            **self.kwargs
        )
        return self.client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()