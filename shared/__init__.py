# shared/__init__.py
"""Shared utilities and configuration for ALS Research Agent"""

from .config import config, AppConfig, APIConfig, RateLimitConfig, ContentLimits, SecurityConfig
from .utils import (
    RateLimiter,
    safe_api_call,
    truncate_text,
    format_authors,
    clean_whitespace,
    ErrorFormatter,
    create_citation
)
from .cache import SimpleCache

__all__ = [
    # Configuration
    'config',
    'AppConfig',
    'APIConfig',
    'RateLimitConfig',
    'ContentLimits',
    'SecurityConfig',
    # Utilities
    'RateLimiter',
    'safe_api_call',
    'truncate_text',
    'format_authors',
    'clean_whitespace',
    'ErrorFormatter',
    'create_citation',
    # Cache
    'SimpleCache',
]
