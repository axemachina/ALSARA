# pubmed_server.py
from mcp.server.fastmcp import FastMCP
import httpx
import logging
import sys
from pathlib import Path

# Add parent directory to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared import (
    config,
    RateLimiter,
    format_authors,
    ErrorFormatter,
    truncate_text
)
from shared.http_client import get_http_client

# Configure logging — force=True so we override any root handler FastMCP installed
logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger(__name__)

# Create FastMCP server
mcp = FastMCP("pubmed-server")

# Rate limiting using shared utility
rate_limiter = RateLimiter(config.rate_limits.pubmed_delay)


@mcp.tool()
async def search_pubmed(
    query: str,
    max_results: int = 10,
    sort: str = "relevance"
) -> str:
    """Search PubMed for ALS research papers. Returns titles, abstracts, PMIDs, and publication dates.

    Args:
        query: Search query (e.g., 'ALS SOD1 therapy')
        max_results: Maximum number of results (default: 10)
        sort: Sort order - 'relevance' or 'date' (default: 'relevance')
    """
    try:
        logger.info(f"Searching PubMed for: {query}")

        # PubMed E-utilities API (no auth required)
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

        # Rate limiting
        await rate_limiter.wait()

        # Step 1: Search for PMIDs
        search_params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "sort": sort
        }

        # Use shared HTTP client for connection pooling
        client = get_http_client(timeout=config.api.timeout)

        # Get PMIDs
        search_resp = await client.get(f"{base_url}/esearch.fcgi", params=search_params)
        search_resp.raise_for_status()
        search_data = search_resp.json()
        pmids = search_data.get("esearchresult", {}).get("idlist", [])

        if not pmids:
            logger.info(f"No results found for query: {query}")
            return ErrorFormatter.no_results(query)

        # Rate limiting
        await rate_limiter.wait()

        # Step 2: Fetch details for PMIDs
        fetch_params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml"
        }

        fetch_resp = await client.get(f"{base_url}/efetch.fcgi", params=fetch_params)
        fetch_resp.raise_for_status()

        # Parse XML and extract key info
        papers = parse_pubmed_xml(fetch_resp.text)

        result = f"Found {len(papers)} papers for query: '{query}'\n\n"
        for i, paper in enumerate(papers, 1):
            result += f"{i}. **{paper['title']}**\n"
            result += f"   PMID: {paper['pmid']} | Published: {paper['date']}\n"
            result += f"   Authors: {paper['authors']}\n"
            result += f"   URL: https://pubmed.ncbi.nlm.nih.gov/{paper['pmid']}/\n"
            result += f"   Abstract: {truncate_text(paper['abstract'], max_chars=300, suffix='')}...\n\n"

        logger.info(f"Successfully retrieved {len(papers)} papers")
        return result

    except httpx.TimeoutException:
        logger.error("PubMed API request timed out")
        return "Error: PubMed API request timed out. Please try again."
    except httpx.HTTPStatusError as e:
        logger.error(f"PubMed API error: {e}")
        return f"Error: PubMed API returned status {e.response.status_code}"
    except Exception as e:
        logger.error(f"Unexpected error in search_pubmed: {e}")
        return f"Error: {str(e)}"


@mcp.tool()
async def get_paper_details(pmid: str) -> str:
    """Get full details for a specific PubMed paper by PMID.

    Args:
        pmid: PubMed ID
    """
    try:
        logger.info(f"Fetching details for PMID: {pmid}")

        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

        # Rate limiting
        await rate_limiter.wait()

        fetch_params = {
            "db": "pubmed",
            "id": pmid,
            "retmode": "xml"
        }

        # Use shared HTTP client for connection pooling
        client = get_http_client(timeout=config.api.timeout)
        fetch_resp = await client.get(f"{base_url}/efetch.fcgi", params=fetch_params)
        fetch_resp.raise_for_status()

        papers = parse_pubmed_xml(fetch_resp.text)

        if not papers:
            return ErrorFormatter.not_found("paper", pmid)

        paper = papers[0]

        # Format detailed response
        result = f"**{paper['title']}**\n\n"
        result += f"**PMID:** {paper['pmid']}\n"
        result += f"**Published:** {paper['date']}\n"
        result += f"**Authors:** {paper['authors']}\n\n"
        result += f"**Abstract:**\n{paper['abstract']}\n\n"
        result += f"**Journal:** {paper.get('journal', 'N/A')}\n"
        result += f"**DOI:** {paper.get('doi', 'N/A')}\n"
        result += f"**PubMed URL:** https://pubmed.ncbi.nlm.nih.gov/{pmid}/\n"

        logger.info(f"Successfully retrieved details for PMID: {pmid}")
        return result

    except httpx.TimeoutException:
        logger.error("PubMed API request timed out")
        return "Error: PubMed API request timed out. Please try again."
    except httpx.HTTPStatusError as e:
        logger.error(f"PubMed API error: {e}")
        return f"Error: PubMed API returned status {e.response.status_code}"
    except Exception as e:
        logger.error(f"Unexpected error in get_paper_details: {e}")
        return f"Error: {str(e)}"


def parse_pubmed_xml(xml_text: str) -> list[dict]:
    """Parse PubMed XML response into structured data with error handling"""
    import xml.etree.ElementTree as ET

    papers = []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.error(f"XML parsing error: {e}")
        return papers

    for article in root.findall(".//PubmedArticle"):
        try:
            # Extract title
            title_elem = article.find(".//ArticleTitle")
            title = "".join(title_elem.itertext()) if title_elem is not None else "No title"

            # Extract abstract (may have multiple AbstractText elements)
            abstract_parts = []
            for abstract_elem in article.findall(".//AbstractText"):
                if abstract_elem is not None and abstract_elem.text:
                    label = abstract_elem.get("Label", "")
                    text = "".join(abstract_elem.itertext())
                    if label:
                        abstract_parts.append(f"{label}: {text}")
                    else:
                        abstract_parts.append(text)
            abstract = " ".join(abstract_parts) if abstract_parts else "No abstract available"

            # Extract PMID
            pmid_elem = article.find(".//PMID")
            pmid = pmid_elem.text if pmid_elem is not None else "Unknown"

            # Extract date - correct path in MedlineCitation
            pub_date = article.find(".//MedlineCitation/Article/Journal/JournalIssue/PubDate")
            if pub_date is not None:
                year_elem = pub_date.find("Year")
                month_elem = pub_date.find("Month")
                year = year_elem.text if year_elem is not None else "Unknown"
                month = month_elem.text if month_elem is not None else ""
                date_str = f"{month} {year}" if month else year
            else:
                # Try alternative date location
                date_completed = article.find(".//DateCompleted")
                if date_completed is not None:
                    year_elem = date_completed.find("Year")
                    year = year_elem.text if year_elem is not None else "Unknown"
                    date_str = year
                else:
                    date_str = "Unknown"

            # Extract authors
            authors = []
            for author in article.findall(".//Author"):
                last = author.find("LastName")
                first = author.find("ForeName")
                collective = author.find("CollectiveName")

                if collective is not None and collective.text:
                    authors.append(collective.text)
                elif last is not None and first is not None:
                    authors.append(f"{first.text} {last.text}")
                elif last is not None:
                    authors.append(last.text)

            # Format authors using shared utility
            authors_str = format_authors("; ".join(authors), max_authors=3) if authors else "Unknown authors"

            # Extract journal name
            journal_elem = article.find(".//Journal/Title")
            journal = journal_elem.text if journal_elem is not None else "Unknown"

            # Extract DOI
            doi = None
            for article_id in article.findall(".//ArticleId"):
                if article_id.get("IdType") == "doi":
                    doi = article_id.text
                    break

            papers.append({
                "title": title,
                "abstract": abstract,
                "pmid": pmid,
                "date": date_str,
                "authors": authors_str,
                "journal": journal,
                "doi": doi or "N/A"
            })

        except Exception as e:
            logger.warning(f"Error parsing article: {e}")
            continue

    return papers


if __name__ == "__main__":
    # Run with stdio transport
    mcp.run(transport="stdio")
