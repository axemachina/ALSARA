# biorxiv_server.py — bioRxiv preprint search via website scraping
# The bioRxiv API has no keyword search; only chronological listing.
# This server scrapes bioRxiv's website search (relevance-ranked, keyword-aware).
from mcp.server.fastmcp import FastMCP
import httpx
import logging
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import quote

# Add parent directory to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared import (
    config,
    RateLimiter,
    format_authors,
    truncate_text,
)
from shared.http_client import CustomHTTPClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True,  # Override root handler installed by FastMCP at import time
)
logger = logging.getLogger(__name__)

mcp = FastMCP("biorxiv-server")
rate_limiter = RateLimiter(config.rate_limits.biorxiv_delay)

# ---------- helpers ----------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

# Regex to pull results from bioRxiv search HTML
_RESULT_RE = re.compile(
    r'<a\s+href="(/content/([^"]+?)v\d+)"\s*[^>]*class="highwire-cite-linked-title"[^>]*>'
    r'<span class="highwire-cite-title">(.*?)</span></a>',
    re.DOTALL,
)

_AUTHORS_RE = re.compile(
    r'<span\s+class="highwire-citation-authors"[^>]*>(.*?)</span>\s*</div>',
    re.DOTALL,
)

_SNIPPET_RE = re.compile(
    r'<span\s+class="highwire-cite-snippet"[^>]*>(.*?)</span>',
    re.DOTALL,
)


def _clean_html(text: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _build_search_url(
    query: str,
    num_results: int = 10,
    sort: str = "relevance-rank",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> str:
    """Build a bioRxiv website search URL.

    bioRxiv search supports inline directives:
      numresults:N  sort:relevance-rank|publication-date
      limit_from:YYYY-MM-DD  limit_to:YYYY-MM-DD
    """
    parts = [quote(query)]
    parts.append(f"numresults%3A{num_results}")
    parts.append(f"sort%3A{sort}")
    if date_from:
        parts.append(f"limit_from%3A{quote(date_from)}")
    if date_to:
        parts.append(f"limit_to%3A{quote(date_to)}")
    return "https://www.biorxiv.org/search/" + "%20".join(parts)


async def _scrape_search(url: str, client: httpx.AsyncClient) -> list[dict]:
    """Fetch a bioRxiv search page and parse results."""
    await rate_limiter.wait()
    resp = await client.get(url, headers=HEADERS)
    resp.raise_for_status()
    html = resp.text

    # Pull each result block
    hrefs = _RESULT_RE.findall(html)
    author_blocks = _AUTHORS_RE.findall(html)
    snippet_blocks = _SNIPPET_RE.findall(html)

    results = []
    for i, (href, doi_fragment, raw_title) in enumerate(hrefs):
        title = _clean_html(raw_title)
        # DOI: newer papers use 10.64898/, older use 10.1101/
        doi = doi_fragment.rstrip("/")
        if not doi.startswith("10."):
            doi = f"10.1101/{doi}"

        authors = _clean_html(author_blocks[i]) if i < len(author_blocks) else ""
        snippet = _clean_html(snippet_blocks[i]) if i < len(snippet_blocks) else ""

        results.append({
            "title": title,
            "doi": doi,
            "authors": authors,
            "abstract_snippet": snippet,
            "url": f"https://www.biorxiv.org{href}",
        })

    return results


# ---------- MCP tools ----------

@mcp.tool()
async def search_preprints(
    query: str,
    max_results: int = 10,
    days_back: int = 365,
) -> str:
    """Search bioRxiv for preprints by keyword with relevance ranking.

    Args:
        query: Search query (e.g., 'ALS TDP-43 gene therapy')
        max_results: Maximum results to return (default 10, max 75)
        days_back: Limit to papers posted within this many days (default 365)
    """
    try:
        logger.info(f"Searching bioRxiv for: '{query}' (max={max_results}, days_back={days_back})")

        max_results = min(max_results, 75)

        # Build date range
        from datetime import datetime, timedelta
        date_to = datetime.now().strftime("%Y-%m-%d")
        date_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        url = _build_search_url(
            query=query,
            num_results=max_results,
            date_from=date_from,
            date_to=date_to,
        )
        logger.info(f"Search URL: {url}")

        async with CustomHTTPClient(timeout=20.0) as client:
            results = await _scrape_search(url, client)

        if not results:
            suggestions = []
            if days_back < 730:
                suggestions.append("Try increasing days_back to search a wider window")
            suggestions.append("Try broader or alternative search terms")
            hint = "\n".join(f"- {s}" for s in suggestions)
            return f"No bioRxiv preprints found for '{query}' in the last {days_back} days.\n\nSuggestions:\n{hint}"

        # Format output
        out = [f"Found {len(results)} bioRxiv preprints for: '{query}'\n"]
        for i, p in enumerate(results, 1):
            out.append(f"{i}. **{p['title']}**")
            out.append(f"   DOI: {p['doi']} | bioRxiv")
            if p['authors']:
                out.append(f"   Authors: {format_authors(p['authors'], max_authors=3)}")
            if p['abstract_snippet']:
                out.append(f"   Abstract: {truncate_text(p['abstract_snippet'], max_chars=300, suffix='')}")
            out.append(f"   URL: {p['url']}")
            out.append("")

        logger.info(f"Returning {len(results)} results")
        return "\n".join(out)

    except httpx.TimeoutException:
        logger.error("bioRxiv search timed out")
        return "Error: bioRxiv search timed out. Try again or use fewer search terms."
    except httpx.HTTPStatusError as e:
        logger.error(f"bioRxiv HTTP error: {e}")
        return f"Error: bioRxiv returned HTTP {e.response.status_code}"
    except Exception as e:
        logger.error(f"bioRxiv search error: {e}", exc_info=True)
        return f"Error searching bioRxiv: {str(e)}"


@mcp.tool()
async def get_preprint_details(doi: str) -> str:
    """Get full metadata for a bioRxiv/medRxiv preprint by DOI.

    Args:
        doi: The DOI (e.g., '10.1101/2024.01.01.123456')
    """
    try:
        logger.info(f"Fetching details for DOI: {doi}")

        # Normalize DOI
        doi = doi.strip()
        if doi.startswith("https://doi.org/"):
            doi = doi[len("https://doi.org/"):]

        # Try bioRxiv API details endpoint (works for DOI lookups)
        async with CustomHTTPClient(timeout=20.0) as client:
            for server in ["biorxiv", "medrxiv"]:
                url = f"https://api.biorxiv.org/details/{server}/{doi}/na/json"
                await rate_limiter.wait()
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    collection = data.get("collection", [])
                    if collection:
                        paper = collection[0]
                        title = paper.get("title", "No title")
                        date = paper.get("date", "Unknown")
                        authors = paper.get("authors", "Unknown")
                        abstract = paper.get("abstract", "No abstract")
                        category = paper.get("category", "")
                        srv = paper.get("server", server)

                        result = f"**{title}**\n\n"
                        result += f"**DOI:** {doi}\n"
                        result += f"**Server:** {srv}\n"
                        result += f"**Posted:** {date}\n"
                        if category:
                            result += f"**Category:** {category}\n"
                        result += f"**Authors:** {authors}\n\n"
                        result += f"**Abstract:**\n{abstract}\n\n"
                        result += f"**URL:** https://doi.org/{doi}\n"
                        return result

        return f"Preprint with DOI {doi} not found on bioRxiv or medRxiv."

    except Exception as e:
        logger.error(f"Error fetching preprint details: {e}")
        return f"Error: {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
