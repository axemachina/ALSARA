# fetch_server.py
from mcp.server.fastmcp import FastMCP
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import logging
import sys
from pathlib import Path

# Add parent directory to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared import (
    config,
    clean_whitespace,
    truncate_text
)
from shared.http_client import get_http_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("fetch-server")

def validate_url(url: str) -> tuple[bool, str]:
    """Validate URL for security concerns. Returns (is_valid, error_message)"""
    try:
        parsed = urlparse(url)

        # Check scheme using shared config
        if parsed.scheme not in config.security.allowed_schemes:
            return False, f"Invalid URL scheme. Only {', '.join(config.security.allowed_schemes)} are allowed."

        # Check for blocked hosts (SSRF protection)
        hostname = parsed.hostname
        if not hostname:
            return False, "Invalid URL: no hostname found."

        # Use shared security config for SSRF checks
        if config.security.is_private_ip(hostname):
            return False, "Access to localhost/private IPs is not allowed."

        return True, ""

    except Exception as e:
        return False, f"Invalid URL: {str(e)}"

def parse_clinical_trial_page(soup: BeautifulSoup, url: str) -> str:
    """Parse ClinicalTrials.gov trial detail page for structured data."""
    # Check if this is a ClinicalTrials.gov page
    if "clinicaltrials.gov" not in url.lower():
        return None

    # Extract NCT ID from URL
    import re
    nct_match = re.search(r'NCT\d{8}', url)
    nct_id = nct_match.group() if nct_match else "Unknown"

    # Try to extract key trial information
    trial_info = []
    trial_info.append(f"**NCT ID:** {nct_id}")
    trial_info.append(f"**URL:** {url}")

    # Look for title
    title = soup.find('h1')
    if title:
        trial_info.append(f"**Title:** {title.get_text(strip=True)}")

    # Look for status (various patterns)
    status_patterns = [
        soup.find('span', string=re.compile(r'Recruiting|Active|Completed|Enrolling', re.I)),
        soup.find('div', string=re.compile(r'Recruitment Status', re.I))
    ]
    for pattern in status_patterns:
        if pattern:
            status_text = pattern.get_text(strip=True) if hasattr(pattern, 'get_text') else str(pattern)
            trial_info.append(f"**Status:** {status_text}")
            break

    # Look for study description
    desc_section = soup.find('div', {'class': re.compile('description', re.I)})
    if desc_section:
        desc_text = desc_section.get_text(strip=True)[:500]
        trial_info.append(f"**Description:** {desc_text}...")

    # Look for conditions
    conditions = soup.find_all(string=re.compile(r'Condition', re.I))
    if conditions:
        for cond in conditions[:1]:  # Just first mention
            parent = cond.parent
            if parent:
                trial_info.append(f"**Condition:** {parent.get_text(strip=True)[:200]}")
                break

    # Look for interventions
    interventions = soup.find_all(string=re.compile(r'Intervention', re.I))
    if interventions:
        for inter in interventions[:1]:  # Just first mention
            parent = inter.parent
            if parent:
                trial_info.append(f"**Intervention:** {parent.get_text(strip=True)[:200]}")
                break

    # Look for sponsor
    sponsor = soup.find(string=re.compile(r'Sponsor', re.I))
    if sponsor and sponsor.parent:
        trial_info.append(f"**Sponsor:** {sponsor.parent.get_text(strip=True)[:100]}")

    # Locations/Sites
    locations = soup.find_all(string=re.compile(r'Location|Site', re.I))
    if locations:
        location_texts = []
        for loc in locations[:3]:  # First 3 locations
            if loc.parent:
                location_texts.append(loc.parent.get_text(strip=True)[:50])
        if location_texts:
            trial_info.append(f"**Locations:** {', '.join(location_texts)}")

    if len(trial_info) > 2:  # If we found meaningful data
        return "\n\n".join(trial_info) + "\n\n**Note:** This is extracted from the trial webpage. Some details may be incomplete due to page structure variations."

    return None

@mcp.tool()
async def fetch_url(url: str, extract_text_only: bool = True) -> str:
    """Fetch content from a URL (paper abstract page, news article, etc.).

    Args:
        url: URL to fetch
        extract_text_only: Extract only main text content (default: True)
    """
    try:
        logger.info(f"Fetching URL: {url}")

        # Validate URL
        is_valid, error_msg = validate_url(url)
        if not is_valid:
            logger.warning(f"URL validation failed: {error_msg}")
            return f"Error: {error_msg}"

        # Use shared HTTP client for connection pooling
        client = get_http_client(timeout=config.api.timeout)
        response = await client.get(url, headers={
            "User-Agent": config.api.user_agent
        })
        response.raise_for_status()

        # Check content size using shared config
        content_length = response.headers.get('content-length')
        if content_length and int(content_length) > config.content_limits.max_content_size:
            logger.warning(f"Content too large: {content_length} bytes")
            return f"Error: Content size ({content_length} bytes) exceeds maximum allowed size of {config.content_limits.max_content_size} bytes"

        # Check actual content size
        if len(response.content) > config.content_limits.max_content_size:
            logger.warning(f"Content too large: {len(response.content)} bytes")
            return f"Error: Content size exceeds maximum allowed size of {config.content_limits.max_content_size} bytes"

        if extract_text_only:
            soup = BeautifulSoup(response.text, 'html.parser')

            # Check if this is a clinical trial page and try enhanced parsing
            trial_data = parse_clinical_trial_page(soup, url)
            if trial_data:
                logger.info(f"Successfully parsed clinical trial page: {url}")
                return trial_data

            # Otherwise, do standard text extraction
            # Remove script and style elements
            for script in soup(["script", "style", "meta", "link"]):
                script.decompose()

            # Get text
            text = soup.get_text()

            # Clean up whitespace using shared utility
            text = clean_whitespace(text)

            # Limit to reasonable size for LLM context using shared utility
            text = truncate_text(text, max_chars=config.content_limits.max_text_chars)

            logger.info(f"Successfully fetched and extracted text from {url}")
            return text
        else:
            # Return raw HTML, but still limit size using shared utility
            html = truncate_text(response.text, max_chars=config.content_limits.max_text_chars)

            logger.info(f"Successfully fetched raw HTML from {url}")
            return html

    except httpx.TimeoutException:
        logger.error(f"Request to {url} timed out")
        return f"Error: Request timed out after {config.api.timeout} seconds"
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching {url}: {e}")
        return f"Error: HTTP {e.response.status_code} - {e.response.reason_phrase}"
    except httpx.RequestError as e:
        logger.error(f"Request error fetching {url}: {e}")
        return f"Error: Failed to fetch URL - {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error fetching {url}: {e}")
        return f"Error: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport="stdio")
