# shared/utils.py
"""Shared utilities for MCP servers"""

import asyncio
import time
import logging
from typing import Optional, Callable, Any
from mcp.types import TextContent
import httpx

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter for API calls"""

    def __init__(self, delay: float):
        """
        Initialize rate limiter

        Args:
            delay: Minimum delay between requests in seconds
        """
        self.delay = delay
        self.last_request_time: Optional[float] = None

    async def wait(self) -> None:
        """Wait if necessary to respect rate limit"""
        if self.last_request_time is not None:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.delay:
                await asyncio.sleep(self.delay - elapsed)
        self.last_request_time = time.time()


async def safe_api_call(
    func: Callable,
    *args: Any,
    timeout: float = 30.0,
    error_prefix: str = "API",
    **kwargs: Any
) -> list[TextContent]:
    """
    Safely execute an API call with comprehensive error handling

    Args:
        func: Async function to call
        *args: Positional arguments for func
        timeout: Timeout in seconds
        error_prefix: Prefix for error messages
        **kwargs: Keyword arguments for func

    Returns:
        list[TextContent]: Result or error message
    """
    try:
        return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)

    except asyncio.TimeoutError:
        logger.error(f"{error_prefix} request timed out after {timeout}s")
        return [TextContent(
            type="text",
            text=f"Error: {error_prefix} request timed out after {timeout} seconds. Please try again."
        )]

    except httpx.TimeoutException:
        logger.error(f"{error_prefix} request timed out")
        return [TextContent(
            type="text",
            text=f"Error: {error_prefix} request timed out. Please try again."
        )]

    except httpx.HTTPStatusError as e:
        logger.error(f"{error_prefix} error: HTTP {e.response.status_code}")
        return [TextContent(
            type="text",
            text=f"Error: {error_prefix} returned status {e.response.status_code}"
        )]

    except httpx.RequestError as e:
        logger.error(f"{error_prefix} request error: {e}")
        return [TextContent(
            type="text",
            text=f"Error: Failed to connect to {error_prefix}. Please check your connection."
        )]

    except Exception as e:
        logger.error(f"Unexpected error in {error_prefix}: {e}", exc_info=True)
        return [TextContent(
            type="text",
            text=f"Error: {str(e)}"
        )]


def truncate_text(text: str, max_chars: int = 8000, suffix: str = "...") -> str:
    """
    Truncate text to maximum length with suffix

    Args:
        text: Text to truncate
        max_chars: Maximum character count
        suffix: Suffix to add when truncated

    Returns:
        Truncated text
    """
    if len(text) <= max_chars:
        return text

    return text[:max_chars] + f"\n\n[Content truncated at {max_chars} characters]{suffix}"


def format_authors(authors: str, max_authors: int = 3) -> str:
    """
    Format author list with et al. if needed

    Args:
        authors: Semicolon-separated author list
        max_authors: Maximum authors to show

    Returns:
        Formatted author string
    """
    if not authors or authors == "Unknown":
        return "Unknown authors"

    author_list = [a.strip() for a in authors.split(";")]

    if len(author_list) <= max_authors:
        return ", ".join(author_list)

    return ", ".join(author_list[:max_authors]) + " et al."


def clean_whitespace(text: str) -> str:
    """
    Clean up excessive whitespace in text

    Args:
        text: Text to clean

    Returns:
        Cleaned text
    """
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    return '\n'.join(chunk for chunk in chunks if chunk)


class ErrorFormatter:
    """Consistent error message formatting"""

    @staticmethod
    def not_found(resource_type: str, identifier: str) -> str:
        """Format not found error"""
        return f"No {resource_type} found with identifier: {identifier}"

    @staticmethod
    def no_results(query: str, time_period: str = "") -> str:
        """Format no results error"""
        time_str = f" {time_period}" if time_period else ""
        return f"No results found for query: {query}{time_str}"

    @staticmethod
    def validation_error(field: str, issue: str) -> str:
        """Format validation error"""
        return f"Validation error: {field} - {issue}"

    @staticmethod
    def api_error(service: str, status_code: int) -> str:
        """Format API error"""
        return f"Error: {service} API returned status {status_code}"


def create_citation(
    identifier: str,
    identifier_type: str,
    url: Optional[str] = None
) -> str:
    """
    Create a formatted citation string

    Args:
        identifier: Citation identifier (PMID, DOI, NCT ID)
        identifier_type: Type of identifier
        url: Optional URL

    Returns:
        Formatted citation
    """
    citation = f"{identifier_type}: {identifier}"
    if url:
        citation += f" | URL: {url}"
    return citation
