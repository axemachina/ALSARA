# shared/config.py
"""Shared configuration for MCP servers"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class APIConfig:
    """Configuration for API calls"""
    timeout: float = 15.0  # Reduced from 30s - PubMed typically responds in <1s
    max_retries: int = 3
    user_agent: str = "Mozilla/5.0 (compatible; ALS-Research-Bot/1.0)"


@dataclass
class RateLimitConfig:
    """Rate limiting configuration for different APIs"""
    # PubMed: 3 req/sec without key, 10 req/sec with key
    pubmed_delay: float = 0.34  # ~3 requests per second

    # ClinicalTrials.gov: conservative limit (API limit is ~50 req/min)
    clinicaltrials_delay: float = 1.5  # ~40 requests per minute (safe margin)

    # bioRxiv/medRxiv: be respectful
    biorxiv_delay: float = 1.0  # 1 request per second

    # General web fetching
    fetch_delay: float = 0.5


@dataclass
class ContentLimits:
    """Content size and length limits"""
    # Maximum content size for downloads (10MB)
    max_content_size: int = 10 * 1024 * 1024

    # Maximum characters for LLM context
    max_text_chars: int = 8000

    # Maximum abstract preview length
    max_abstract_preview: int = 300

    # Maximum description preview length
    max_description_preview: int = 500


@dataclass
class SecurityConfig:
    """Security-related configuration"""
    allowed_schemes: list[str] = None
    blocked_hosts: list[str] = None

    def __post_init__(self):
        if self.allowed_schemes is None:
            self.allowed_schemes = ['http', 'https']

        if self.blocked_hosts is None:
            self.blocked_hosts = [
                'localhost',
                '127.0.0.1',
                '0.0.0.0',
                '[::1]'
            ]

    def is_private_ip(self, hostname: str) -> bool:
        """Check if hostname is a private IP"""
        hostname_lower = hostname.lower()

        # Check exact matches
        if hostname_lower in self.blocked_hosts:
            return True

        # Check private IP ranges
        if hostname_lower.startswith(('192.168.', '10.')):
            return True

        # Check 172.16-31 range
        if hostname_lower.startswith('172.'):
            try:
                second_octet = int(hostname.split('.')[1])
                if 16 <= second_octet <= 31:
                    return True
            except (ValueError, IndexError):
                pass

        return False


@dataclass
class AppConfig:
    """Application-wide configuration"""
    # API configurations
    api: APIConfig = None
    rate_limits: RateLimitConfig = None
    content_limits: ContentLimits = None
    security: SecurityConfig = None

    # Environment variables
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-4-5-20250929"
    gradio_port: int = 7860
    log_level: str = "INFO"

    # PubMed email (optional, increases rate limit)
    pubmed_email: Optional[str] = None

    def __post_init__(self):
        # Initialize sub-configs
        if self.api is None:
            self.api = APIConfig()
        if self.rate_limits is None:
            self.rate_limits = RateLimitConfig()
        if self.content_limits is None:
            self.content_limits = ContentLimits()
        if self.security is None:
            self.security = SecurityConfig()

        # Load from environment
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", self.anthropic_api_key)
        self.anthropic_model = os.getenv("ANTHROPIC_MODEL", self.anthropic_model)
        self.gradio_port = int(os.getenv("GRADIO_SERVER_PORT", self.gradio_port))
        self.log_level = os.getenv("LOG_LEVEL", self.log_level)
        self.pubmed_email = os.getenv("PUBMED_EMAIL", self.pubmed_email)

    @classmethod
    def from_env(cls) -> 'AppConfig':
        """Create configuration from environment variables"""
        return cls()


# Global configuration instance
config = AppConfig.from_env()
