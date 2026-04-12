# biorxiv_server_fixed.py
from mcp.server.fastmcp import FastMCP
import httpx
import logging
from datetime import datetime, timedelta
import sys
from pathlib import Path
import re

# Add parent directory to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared import (
    config,
    RateLimiter,
    format_authors,
    ErrorFormatter,
    truncate_text
)
from shared.http_client import get_http_client, CustomHTTPClient

# Configure logging with DEBUG for detailed troubleshooting
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

mcp = FastMCP("biorxiv-server")

# Rate limiting using shared utility
rate_limiter = RateLimiter(config.rate_limits.biorxiv_delay)


def preprocess_query(query: str) -> tuple[list[str], list[str]]:
    """Preprocess query into search terms and handle synonyms.

    Returns:
        tuple of (primary_terms, all_search_terms)
    """
    # Convert to lowercase for matching
    query_lower = query.lower()

    # Common ALS-related synonyms and variations
    synonyms = {
        'als': ['amyotrophic lateral sclerosis', 'motor neuron disease', 'motor neurone disease', 'lou gehrig'],
        'amyotrophic lateral sclerosis': ['als', 'motor neuron disease'],
        'mnd': ['motor neuron disease', 'motor neurone disease', 'als'],
        'sod1': ['superoxide dismutase 1', 'cu/zn superoxide dismutase'],
        'tdp-43': ['tdp43', 'tardbp', 'tar dna binding protein'],
        'c9orf72': ['c9', 'chromosome 9 open reading frame 72'],
        'fus': ['fused in sarcoma', 'tls'],
    }

    # Split query into individual terms (handle multiple spaces and special chars)
    # Keep hyphenated words together (like TDP-43)
    terms = re.split(r'\s+', query_lower.strip())

    # Build comprehensive search term list
    all_terms = []
    primary_terms = []

    for term in terms:
        # Skip very short terms unless they're known abbreviations
        if len(term) < 3 and term not in ['als', 'mnd', 'fus', 'c9']:
            continue

        primary_terms.append(term)
        all_terms.append(term)

        # Add synonyms if they exist
        if term in synonyms:
            all_terms.extend(synonyms[term])

    # Remove duplicates while preserving order
    seen = set()
    all_terms = [t for t in all_terms if not (t in seen or seen.add(t))]
    primary_terms = [t for t in primary_terms if not (t in seen or seen.add(t))]

    return primary_terms, all_terms


def matches_query(paper: dict, primary_terms: list[str], all_terms: list[str], require_all: bool = False) -> bool:
    """Check if a paper matches the search query.

    Args:
        paper: Paper dictionary from bioRxiv API
        primary_terms: Main search terms from user query
        all_terms: All search terms including synonyms
        require_all: If True, require ALL primary terms. If False, require ANY term.

    Returns:
        True if paper matches search criteria
    """
    # Get searchable text
    title = paper.get("title", "").lower()
    abstract = paper.get("abstract", "").lower()
    searchable_text = f" {title} {abstract} "  # Add spaces for boundary matching

    # DEBUG: Log paper being checked
    paper_doi = paper.get("doi", "unknown")
    logger.debug(f"🔍 Checking paper: {title[:60]}... (DOI: {paper_doi})")

    if not searchable_text.strip():
        logger.debug(f"  ❌ Rejected: No title/abstract")
        return False

    # For ALS specifically, need to be careful about word boundaries
    has_any_match = False
    matched_term = None
    for term in all_terms:
        # For short terms like "ALS", require word boundaries
        if len(term) <= 3:
            # Check for word boundary match
            pattern = r'\b' + re.escape(term) + r'\b'
            if re.search(pattern, searchable_text, re.IGNORECASE):
                has_any_match = True
                matched_term = term
                break
        else:
            # For longer terms, can be more lenient
            if term.lower() in searchable_text:
                has_any_match = True
                matched_term = term
                break

    if not has_any_match:
        logger.debug(f"  ❌ Rejected: No term match. Terms searched: {all_terms[:3]}...")
        return False

    logger.debug(f"  ✅ Matched on term: '{matched_term}'")

    # If we only need any match, we're done
    if not require_all:
        return True

    # For require_all, check that all primary terms are present
    # Allow for word boundaries to avoid partial matches
    for term in primary_terms:
        # Create pattern that matches the term as a whole word or part of hyphenated word
        # This handles cases like "TDP-43" or "SOD1"
        pattern = r'\b' + re.escape(term) + r'(?:\b|[-])'
        if not re.search(pattern, searchable_text, re.IGNORECASE):
            return False

    return True


@mcp.tool()
async def search_preprints(
    query: str,
    server: str = "both",
    max_results: int = 10,
    days_back: int = 365
) -> str:
    """Search bioRxiv and medRxiv for ALS preprints. Returns recent preprints before peer review.

    Args:
        query: Search query (e.g., 'ALS TDP-43')
        server: Which server to search - one of: biorxiv, medrxiv, both (default: both)
        max_results: Maximum number of results (default: 10)
        days_back: Number of days to look back (default: 365 - about 1 year)
    """
    try:
        logger.info(f"🔎 Searching bioRxiv/medRxiv for: '{query}'")
        logger.info(f"   Parameters: server={server}, max_results={max_results}, days_back={days_back}")

        # Preprocess query for better matching
        primary_terms, all_terms = preprocess_query(query)
        logger.info(f"📝 Search terms: primary={primary_terms}, all={all_terms}")

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        # Format dates for API (YYYY-MM-DD)
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
        logger.info(f"📅 Date range: {start_date_str} to {end_date_str}")

        # bioRxiv/medRxiv API endpoint
        base_url = "https://api.biorxiv.org/details"

        all_results = []
        servers_to_search = []

        if server in ["biorxiv", "both"]:
            servers_to_search.append("biorxiv")
        if server in ["medrxiv", "both"]:
            servers_to_search.append("medrxiv")

        # Use a custom HTTP client with proper timeout for bioRxiv
        # Don't use shared client as it may have conflicting timeout settings
        async with CustomHTTPClient(timeout=15.0) as client:
            for srv in servers_to_search:
                try:
                    cursor = 0
                    found_in_server = []
                    max_iterations = 1  # Only check first page (100 papers) for much faster response
                    iteration = 0

                    while iteration < max_iterations:
                        # Rate limiting
                        await rate_limiter.wait()

                        # Search by date range with cursor for pagination
                        url = f"{base_url}/{srv}/{start_date_str}/{end_date_str}/{cursor}"

                        logger.info(f"🌐 Querying {srv} API (page {iteration+1}, cursor={cursor})")
                        logger.info(f"   URL: {url}")
                        response = await client.get(url)
                        response.raise_for_status()
                        data = response.json()

                        # Extract collection
                        collection = data.get("collection", [])

                        if not collection:
                            logger.info(f"📭 No more results from {srv}")
                            break

                        logger.info(f"📦 Fetched {len(collection)} papers from API")

                        # Show first few papers for debugging
                        if iteration == 0 and collection:
                            logger.info("   Sample papers from API:")
                            for i, paper in enumerate(collection[:3]):
                                logger.info(f"   {i+1}. {paper.get('title', 'No title')[:60]}...")

                        # Filter papers using improved matching
                        # Start with lenient matching (ANY term)
                        logger.debug(f"🔍 Starting to filter {len(collection)} papers...")
                        filtered = [
                            paper for paper in collection
                            if matches_query(paper, primary_terms, all_terms, require_all=False)
                        ]

                        logger.info(f"✅ Filtered results: {len(filtered)}/{len(collection)} papers matched")

                        if len(filtered) > 0:
                            logger.info("   Matched papers:")
                            for i, paper in enumerate(filtered[:3]):
                                logger.info(f"   {i+1}. {paper.get('title', 'No title')[:60]}...")

                        found_in_server.extend(filtered)
                        logger.info(f"📊 Running total for {srv}: {len(found_in_server)} papers")

                        # Check if we have enough results
                        if len(found_in_server) >= max_results:
                            logger.info(f"Reached max_results limit ({max_results})")
                            break

                        # Continue searching if we haven't found enough
                        if len(found_in_server) < 5 and iteration < max_iterations - 1:
                            # Keep searching for more results
                            pass
                        elif len(found_in_server) > 0 and iteration >= 3:
                            # Found some results after reasonable search
                            logger.info(f"Found {len(found_in_server)} results after {iteration+1} pages")
                            break

                        # Check for more pages
                        messages = data.get("messages", [])

                        # The API returns "cursor" in messages for next page
                        has_more = False
                        for msg in messages:
                            if "cursor=" in str(msg):
                                try:
                                    cursor_str = str(msg).split("cursor=")[1].split()[0]
                                    next_cursor = int(cursor_str)
                                    if next_cursor > cursor:
                                        cursor = next_cursor
                                        has_more = True
                                        break
                                except:
                                    pass

                        # Alternative: increment by collection size
                        if not has_more:
                            if len(collection) >= 100:
                                cursor += len(collection)
                            else:
                                # Less than full page means we've reached the end
                                break

                        iteration += 1

                    all_results.extend(found_in_server[:max_results])
                    logger.info(f"🏁 Total results from {srv}: {len(found_in_server)} papers found")

                except httpx.HTTPStatusError as e:
                    logger.warning(f"Error searching {srv}: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Unexpected error searching {srv}: {e}")
                    continue

        # If no results with lenient matching, provide helpful message
        if not all_results:
            logger.warning(f"⚠️ No preprints found for query: {query}")

            # Provide suggestions for improving search
            suggestions = []
            if len(primary_terms) > 3:
                suggestions.append("Try using fewer search terms")
            if not any(term in ['als', 'amyotrophic lateral sclerosis', 'motor neuron'] for term in all_terms):
                suggestions.append("Add 'ALS' or 'motor neuron disease' to your search")
            if days_back < 365:
                suggestions.append(f"Expand the time range beyond {days_back} days")

            suggestion_text = ""
            if suggestions:
                suggestion_text = "\n\nSuggestions:\n" + "\n".join(f"- {s}" for s in suggestions)

            return f"No preprints found for query: '{query}' in the last {days_back} days{suggestion_text}"

        # Sort by date (most recent first)
        all_results.sort(key=lambda x: x.get("date", ""), reverse=True)

        # Limit results
        all_results = all_results[:max_results]

        logger.info(f"🎯 FINAL RESULTS: Returning {len(all_results)} preprints for '{query}'")
        if all_results:
            logger.info("   Top results:")
            for i, paper in enumerate(all_results[:3], 1):
                logger.info(f"   {i}. {paper.get('title', 'No title')[:60]}...")
                logger.info(f"      DOI: {paper.get('doi', 'unknown')}, Date: {paper.get('date', 'unknown')}")

        # Format results
        result = f"Found {len(all_results)} preprints for query: '{query}'\n\n"

        for i, paper in enumerate(all_results, 1):
            title = paper.get("title", "No title")
            doi = paper.get("doi", "Unknown")
            date = paper.get("date", "Unknown")
            authors = paper.get("authors", "Unknown authors")
            authors_str = format_authors(authors, max_authors=3)

            abstract = paper.get("abstract", "No abstract available")
            category = paper.get("category", "")
            server_name = "bioRxiv" if "biorxiv" in doi else "medRxiv"

            result += f"{i}. **{title}**\n"
            result += f"   DOI: {doi} | {server_name} | Posted: {date}\n"
            result += f"   Authors: {authors_str}\n"
            if category:
                result += f"   Category: {category}\n"
            result += f"   Abstract: {truncate_text(abstract, max_chars=300, suffix='')}\n"
            result += f"   URL: https://doi.org/{doi}\n\n"

        logger.info(f"Successfully retrieved {len(all_results)} preprints")
        return result

    except httpx.TimeoutException:
        logger.error("bioRxiv/medRxiv API request timed out")
        return "Error: bioRxiv/medRxiv API request timed out. Please try again."
    except httpx.HTTPStatusError as e:
        logger.error(f"bioRxiv/medRxiv API error: {e}")
        return f"Error: bioRxiv/medRxiv API returned status code {e.response.status_code}"
    except Exception as e:
        logger.error(f"Unexpected error in search_preprints: {e}")
        return f"Error searching preprints: {str(e)}"


@mcp.tool()
async def get_preprint_details(doi: str) -> str:
    """Get full details for a specific bioRxiv/medRxiv preprint by DOI.

    Args:
        doi: The DOI of the preprint (e.g., '10.1101/2024.01.01.123456')
    """
    try:
        logger.info(f"Getting details for DOI: {doi}")

        # Ensure DOI is properly formatted
        if not doi.startswith("10.1101/"):
            doi = f"10.1101/{doi}"

        # Determine server from DOI
        # bioRxiv DOIs typically have format: 10.1101/YYYY.MM.DD.NNNNNN
        # medRxiv DOIs are similar but the content determines the server

        # Use shared HTTP client for connection pooling
        client = get_http_client(timeout=30.0)
        # Try the DOI endpoint
        url = f"https://api.biorxiv.org/details/{doi}"

        response = await client.get(url)

        if response.status_code == 404:
            # Try with both servers
            for server in ["biorxiv", "medrxiv"]:
                url = f"https://api.biorxiv.org/details/{server}/{doi}"
                response = await client.get(url)
                if response.status_code == 200:
                    break
            else:
                return f"Preprint with DOI {doi} not found"

        response.raise_for_status()
        data = response.json()

        collection = data.get("collection", [])
        if not collection:
            return f"No details found for DOI: {doi}"

        # Get the first (and should be only) paper
        paper = collection[0]

        title = paper.get("title", "No title")
        date = paper.get("date", "Unknown")
        authors = paper.get("authors", "Unknown authors")
        abstract = paper.get("abstract", "No abstract available")
        category = paper.get("category", "")
        server_name = paper.get("server", "Unknown")

        result = f"**{title}**\n\n"
        result += f"**DOI:** {doi}\n"
        result += f"**Server:** {server_name}\n"
        result += f"**Posted:** {date}\n"
        if category:
            result += f"**Category:** {category}\n"
        result += f"**Authors:** {authors}\n\n"
        result += f"**Abstract:**\n{abstract}\n\n"
        result += f"**Full Text URL:** https://doi.org/{doi}\n"

        return result

    except httpx.HTTPStatusError as e:
        logger.error(f"Error fetching preprint details: {e}")
        return f"Error fetching preprint details: HTTP {e.response.status_code}"
    except Exception as e:
        logger.error(f"Unexpected error getting preprint details: {e}")
        return f"Error getting preprint details: {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")