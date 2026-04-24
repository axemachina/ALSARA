"""Tool registry: imports functions directly from servers/ modules and maps
clean tool names to async callables + Anthropic-format schemas.

The server modules are imported at call time (lazy) so their module-level
logging.basicConfig(force=True) doesn't override the main app's logging.
"""
import asyncio
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-import helpers — avoid executing server module tops at import time
# ---------------------------------------------------------------------------

async def _search_pubmed(**kw):
    from servers.pubmed_server import search_pubmed
    return await search_pubmed(**kw)

async def _get_paper_details(**kw):
    from servers.pubmed_server import get_paper_details
    return await get_paper_details(**kw)

async def _search_als_trials(**kw):
    from servers.aact_server import search_als_trials
    return await search_als_trials(**kw)

async def _get_trial_details(**kw):
    from servers.aact_server import get_trial_details
    return await get_trial_details(**kw)

async def _find_trials_near_me(**kw):
    from servers.aact_server import find_trials_near_me
    return await find_trials_near_me(**kw)

async def _check_new_als_trials(**kw):
    from servers.aact_server import check_new_als_trials
    return await check_new_als_trials(**kw)

async def _fetch_url(**kw):
    from servers.fetch_server import fetch_url
    return await fetch_url(**kw)

async def _get_known_als_trials(**kw):
    from servers.clinicaltrials_links import get_known_als_trials
    return await get_known_als_trials(**kw)

async def _get_trial_link(**kw):
    from servers.clinicaltrials_links import get_trial_link
    return await get_trial_link(**kw)

# --- Optional: bioRxiv (enabled via ENABLE_BIORXIV) ---

async def _search_preprints(**kw):
    from servers.biorxiv_server import search_preprints
    return await search_preprints(**kw)

async def _get_preprint_details(**kw):
    from servers.biorxiv_server import get_preprint_details
    return await get_preprint_details(**kw)

# --- Optional: LlamaIndex RAG (enabled via ENABLE_RAG) ---

async def _semantic_search(**kw):
    from servers.llamaindex_server import semantic_search
    return await semantic_search(**kw)

async def _index_paper(**kw):
    from servers.llamaindex_server import index_paper
    return await index_paper(**kw)

async def _list_indexed_papers(**kw):
    from servers.llamaindex_server import list_indexed_papers
    return await list_indexed_papers(**kw)

async def _get_research_connections(**kw):
    from servers.llamaindex_server import get_research_connections
    return await get_research_connections(**kw)

async def _upload_now(**kw):
    from servers.llamaindex_server import upload_now
    return await upload_now(**kw)


# ---------------------------------------------------------------------------
# Registry: tool_name -> {function, schema}
# ---------------------------------------------------------------------------

# Core tools (always registered)
CORE_TOOLS: Dict[str, Dict[str, Any]] = {
    "pubmed__search_pubmed": {
        "function": _search_pubmed,
        "schema": {
            "name": "pubmed__search_pubmed",
            "description": "Search PubMed for ALS research papers. Returns titles, abstracts, PMIDs, and publication dates.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (e.g., 'ALS SOD1 therapy')"},
                    "max_results": {"type": "integer", "description": "Maximum results (default 10)", "default": 10},
                    "sort": {"type": "string", "enum": ["relevance", "date"], "default": "relevance"},
                },
                "required": ["query"],
            },
        },
    },
    "pubmed__get_paper_details": {
        "function": _get_paper_details,
        "schema": {
            "name": "pubmed__get_paper_details",
            "description": "Get full details for a specific PubMed paper by PMID.",
            "input_schema": {"type": "object", "properties": {"pmid": {"type": "string"}}, "required": ["pmid"]},
        },
    },
    "aact__search_als_trials": {
        "function": _search_als_trials,
        "schema": {
            "name": "aact__search_als_trials",
            "description": "Search for ALS clinical trials in the AACT database (559k+ trials). Intervention synonyms are expanded automatically.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "RECRUITING, ACTIVE_NOT_RECRUITING, COMPLETED, etc.", "default": "RECRUITING"},
                    "phase": {"type": "string", "description": "PHASE_1, PHASE_2, PHASE_3, PHASE_4, EARLY_PHASE_1"},
                    "intervention": {"type": "string", "description": "Intervention/treatment to search for (synonyms auto-expanded)"},
                    "location": {"type": "string", "description": "Country or region"},
                    "max_results": {"type": "integer", "default": 20},
                },
                "required": [],
            },
        },
    },
    "aact__get_trial_details": {
        "function": _get_trial_details,
        "schema": {
            "name": "aact__get_trial_details",
            "description": "Get detailed information about a specific clinical trial by NCT ID.",
            "input_schema": {"type": "object", "properties": {"nct_id": {"type": "string"}}, "required": ["nct_id"]},
        },
    },
    "aact__find_trials_near_me": {
        "function": _find_trials_near_me,
        "schema": {
            "name": "aact__find_trials_near_me",
            "description": "Find ALS clinical trials near a geographic location using proximity search.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number", "description": "Latitude (e.g. 48.86 for Paris)"},
                    "longitude": {"type": "number", "description": "Longitude (e.g. 2.35 for Paris)"},
                    "radius_miles": {"type": "integer", "default": 100},
                    "max_results": {"type": "integer", "default": 20},
                    "subtype": {"type": "string", "description": "ALS subtype filter: SOD1, C9orf72, bulbar, limb, familial, sporadic"},
                },
                "required": ["latitude", "longitude"],
            },
        },
    },
    "aact__check_new_als_trials": {
        "function": _check_new_als_trials,
        "schema": {
            "name": "aact__check_new_als_trials",
            "description": "Find ALS trials posted or updated in the last N days.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "days_back": {"type": "integer", "default": 30},
                    "max_results": {"type": "integer", "default": 20},
                    "subtype": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    "fetch__fetch_url": {
        "function": _fetch_url,
        "schema": {
            "name": "fetch__fetch_url",
            "description": "Fetch and extract text content from a URL (paper pages, news articles, trial pages).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "extract_text_only": {"type": "boolean", "default": True},
                },
                "required": ["url"],
            },
        },
    },
    "trials_links__get_known_als_trials": {
        "function": _get_known_als_trials,
        "schema": {
            "name": "trials_links__get_known_als_trials",
            "description": "Curated list of important ALS trials (fallback when AACT unavailable).",
            "input_schema": {
                "type": "object",
                "properties": {"status_filter": {"type": "string"}},
                "required": [],
            },
        },
    },
    "trials_links__get_trial_link": {
        "function": _get_trial_link,
        "schema": {
            "name": "trials_links__get_trial_link",
            "description": "Generate direct link to a ClinicalTrials.gov trial page.",
            "input_schema": {"type": "object", "properties": {"nct_id": {"type": "string"}}, "required": ["nct_id"]},
        },
    },
}

# Optional: bioRxiv tools (added when ENABLE_BIORXIV=true)
BIORXIV_TOOLS: Dict[str, Dict[str, Any]] = {
    "biorxiv__search_preprints": {
        "function": _search_preprints,
        "schema": {
            "name": "biorxiv__search_preprints",
            "description": "Search bioRxiv/medRxiv for ALS preprints.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 10},
                    "days_back": {"type": "integer", "default": 365},
                },
                "required": ["query"],
            },
        },
    },
    "biorxiv__get_preprint_details": {
        "function": _get_preprint_details,
        "schema": {
            "name": "biorxiv__get_preprint_details",
            "description": "Get full details for a specific bioRxiv/medRxiv preprint by DOI.",
            "input_schema": {"type": "object", "properties": {"doi": {"type": "string"}}, "required": ["doi"]},
        },
    },
}

# Optional: LlamaIndex RAG tools (added when ENABLE_RAG=true)
LLAMAINDEX_TOOLS: Dict[str, Dict[str, Any]] = {
    "llamaindex__semantic_search": {
        "function": _semantic_search,
        "schema": {
            "name": "llamaindex__semantic_search",
            "description": "Search persistent research memory using AI-powered semantic matching.",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "max_results": {"type": "integer", "default": 5}},
                "required": ["query"],
            },
        },
    },
    "llamaindex__index_paper": {
        "function": _index_paper,
        "schema": {
            "name": "llamaindex__index_paper",
            "description": "Save a paper to persistent memory for future retrieval.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"}, "abstract": {"type": "string"},
                    "authors": {"type": "string"}, "doi": {"type": "string"},
                    "year": {"type": "string"}, "url": {"type": "string"},
                    "finding": {"type": "string"},
                },
                "required": ["title"],
            },
        },
    },
    "llamaindex__list_indexed_papers": {
        "function": _list_indexed_papers,
        "schema": {
            "name": "llamaindex__list_indexed_papers",
            "description": "List all papers currently in memory.",
            "input_schema": {"type": "object", "properties": {}},
        },
    },
    "llamaindex__get_research_connections": {
        "function": _get_research_connections,
        "schema": {
            "name": "llamaindex__get_research_connections",
            "description": "Find papers in memory related to a given title.",
            "input_schema": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]},
        },
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

import os

def get_active_tools() -> Dict[str, Dict[str, Any]]:
    """Return the full set of tools active for the current configuration."""
    tools = dict(CORE_TOOLS)
    if os.getenv("ENABLE_BIORXIV", "false").lower() == "true":
        tools.update(BIORXIV_TOOLS)
    if os.getenv("ENABLE_RAG", "false").lower() == "true":
        tools.update(LLAMAINDEX_TOOLS)
    return tools


def get_tool_schemas() -> List[Dict[str, Any]]:
    """Return Anthropic-format tool definitions for all active tools."""
    return [t["schema"] for t in get_active_tools().values()]


async def call_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Dispatch a tool call by name. Returns the string result."""
    tools = get_active_tools()
    entry = tools.get(tool_name)
    if entry is None:
        return f"Error: Unknown tool '{tool_name}'"
    try:
        return await asyncio.wait_for(entry["function"](**arguments), timeout=90.0)
    except asyncio.TimeoutError:
        return f"Error: Tool '{tool_name}' timed out after 90 seconds"
    except Exception as e:
        logger.error(f"Tool '{tool_name}' failed: {e}")
        return f"Error: {str(e)}"


async def flush_llamaindex():
    """Flush chroma_db to HF Dataset (call on shutdown)."""
    if os.getenv("ENABLE_RAG", "false").lower() == "true":
        if os.getenv("CHROMA_SYNC_REPO") and os.getenv("HF_TOKEN"):
            try:
                await asyncio.wait_for(_upload_now(), timeout=15.0)
                logger.info("Chroma sync completed on shutdown")
            except Exception as e:
                logger.warning(f"Chroma sync on shutdown failed (non-fatal): {e}")
