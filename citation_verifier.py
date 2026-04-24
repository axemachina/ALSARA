"""Post-synthesis citation verifier.

Extracts every NCT ID, PMID, and DOI from the agent's final response and
checks each one against the canonical registry (ClinicalTrials.gov, PubMed,
doi.org). Returns a list of citations with verification status so the caller
can append a warning block to the response.

Design notes:
- Verification runs AFTER the synthesis is complete and streamed. We don't
  block the user on it; it's a best-effort audit appended at the end.
- Each check is a short HEAD/GET with a hard timeout. Failures default to
  "unknown" rather than "invalid" — a network blip shouldn't accuse a real
  citation of being fake.
- Whitelist mode: if the caller provides the IDs that actually appeared in
  tool results during the conversation, any ID in the response that wasn't
  in a tool result is immediately flagged as "not-from-search" — this catches
  model hallucinations before we even hit the network.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Iterable, Literal, Optional

import httpx

logger = logging.getLogger(__name__)


# Permissive patterns. We match common formats; edge cases (e.g., PMC IDs
# with "PMC" prefix, registry IDs other than NCT) are out of scope.
NCT_RE = re.compile(r"\b(NCT\d{8})\b")
PMID_RE = re.compile(r"\bPMID[:\s]+(\d{6,9})\b", re.IGNORECASE)
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.IGNORECASE)


Status = Literal["ok", "not_found", "not_from_search", "unknown", "skipped"]


@dataclass
class Verification:
    kind: Literal["NCT", "PMID", "DOI"]
    value: str
    status: Status
    detail: str = ""


def extract_citations(text: str) -> dict[str, set[str]]:
    """Pull all NCT/PMID/DOI tokens out of the response text."""
    return {
        "NCT": set(NCT_RE.findall(text)),
        "PMID": {m for m in PMID_RE.findall(text)},
        "DOI": {_clean_doi(m) for m in DOI_RE.findall(text)},
    }


def _clean_doi(doi: str) -> str:
    # Strip trailing punctuation a URL wouldn't have
    return doi.rstrip(").,;:")


async def _check_nct(client: httpx.AsyncClient, nct: str) -> Verification:
    """Verify an NCT via ClinicalTrials.gov.

    Their CDN aggressively rate-limits API access from most IPs, so for
    NCTs the whitelist (IDs that came from AACT tool results this session)
    is the primary signal. If we got here, the NCT wasn't on the whitelist
    but we also can't reliably network-verify — flag as unknown.
    """
    # The CF edge returns 403 for most programmatic clients. Don't pretend
    # we can check this reliably; just report unknown so the user knows
    # to verify manually.
    return Verification(
        "NCT", nct, "unknown",
        "Not retrievable programmatically (ClinicalTrials.gov blocks CDN). Verify at https://clinicaltrials.gov/study/" + nct
    )


async def _check_pmid(client: httpx.AsyncClient, pmid: str) -> Verification:
    """PubMed E-utilities esummary returns a JSON body referencing the PMID if it exists."""
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    try:
        r = await client.get(url, params={"db": "pubmed", "id": pmid, "retmode": "json"}, timeout=8.0)
        if r.status_code != 200:
            return Verification("PMID", pmid, "unknown", f"HTTP {r.status_code}")
        data = r.json()
        # Esummary returns {"result": {"uids": ["..."], "<pmid>": {...}}} for valid PMIDs.
        # For invalid PMIDs it either omits the key or includes an "error" field.
        result = data.get("result", {})
        entry = result.get(pmid)
        if entry is None or "error" in entry:
            return Verification("PMID", pmid, "not_found", "PubMed returned no record")
        # Sanity-check: the entry should have at least a title
        if not entry.get("title"):
            return Verification("PMID", pmid, "not_found", "PubMed entry missing title")
        return Verification("PMID", pmid, "ok")
    except Exception as e:
        return Verification("PMID", pmid, "unknown", f"{type(e).__name__}: {e}")


async def _check_doi(client: httpx.AsyncClient, doi: str) -> Verification:
    """doi.org returns a redirect (301/302) for registered DOIs, 404 for unknown."""
    url = f"https://doi.org/{doi}"
    try:
        r = await client.head(url, timeout=8.0, follow_redirects=False)
        # doi.org redirects registered DOIs; 404 for unknown
        if r.status_code in (301, 302, 303, 307, 308):
            return Verification("DOI", doi, "ok")
        if r.status_code == 404:
            return Verification("DOI", doi, "not_found", "doi.org returned 404")
        # 200 is unusual but valid
        if r.status_code == 200:
            return Verification("DOI", doi, "ok")
        return Verification("DOI", doi, "unknown", f"HTTP {r.status_code}")
    except Exception as e:
        return Verification("DOI", doi, "unknown", f"{type(e).__name__}: {e}")


async def verify_citations(
    response_text: str,
    tool_result_ids: Optional[dict[str, Iterable[str]]] = None,
    max_concurrent: int = 10,
) -> list[Verification]:
    """Verify every citation found in response_text.

    Args:
        response_text: The agent's final synthesized response.
        tool_result_ids: Optional dict with keys {"NCT", "PMID", "DOI"}, each
            mapping to a collection of IDs that actually appeared in tool
            results during this conversation. Any ID in the response not in
            this set is flagged "not_from_search" without a network call.
        max_concurrent: Cap parallel HTTP requests.

    Returns a list of Verification results sorted by status (worst first).
    """
    extracted = extract_citations(response_text)
    total = sum(len(v) for v in extracted.values())
    if total == 0:
        return []

    logger.info(f"Verifying {total} citations: {[(k, len(v)) for k, v in extracted.items()]}")

    whitelist = tool_result_ids or {}
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _bounded_check(coro):
        async with semaphore:
            return await coro

    # Whitelist-first: if we know what IDs were in tool results, anything
    # not in that set is clearly fabricated — no need to hit the network.
    need_network: list = []
    results: list[Verification] = []

    # Per-kind whitelist: only enforce if we actually collected IDs of that
    # kind from tool results. An empty whitelist for a kind means we have
    # no ground truth and should fall back to network verification.
    def _use_whitelist(kind: str) -> set[str] | None:
        if not whitelist:
            return None
        kind_wl = set(whitelist.get(kind, []) or [])
        return kind_wl if kind_wl else None

    async with httpx.AsyncClient(
        headers={"User-Agent": "ALSARA/1.0 (citation-verifier)"}
    ) as client:
        nct_wl = _use_whitelist("NCT")
        for nct in extracted["NCT"]:
            if nct_wl is not None and nct not in nct_wl:
                results.append(Verification("NCT", nct, "not_from_search",
                                             "Not present in any tool result this session"))
            else:
                need_network.append(_bounded_check(_check_nct(client, nct)))

        pmid_wl = _use_whitelist("PMID")
        for pmid in extracted["PMID"]:
            if pmid_wl is not None and pmid not in pmid_wl:
                results.append(Verification("PMID", pmid, "not_from_search",
                                             "Not present in any tool result this session"))
            else:
                need_network.append(_bounded_check(_check_pmid(client, pmid)))

        doi_wl = _use_whitelist("DOI")
        for doi in extracted["DOI"]:
            if doi_wl is not None and doi not in doi_wl:
                results.append(Verification("DOI", doi, "not_from_search",
                                             "Not present in any tool result this session"))
            else:
                need_network.append(_bounded_check(_check_doi(client, doi)))

        network_results = await asyncio.gather(*need_network, return_exceptions=True)
        for r in network_results:
            if isinstance(r, Verification):
                results.append(r)
            else:
                logger.warning(f"Verification task raised: {r}")

    # Sort worst-first
    status_order = {"not_from_search": 0, "not_found": 1, "unknown": 2, "skipped": 3, "ok": 4}
    results.sort(key=lambda v: (status_order.get(v.status, 9), v.kind, v.value))
    return results


def collect_ids_from_tool_results(tool_results: list[str]) -> dict[str, set[str]]:
    """Extract all NCT/PMID/DOI from a list of raw tool result strings.

    Used to build the whitelist: every ID the agent legitimately saw during
    this conversation's tool calls.
    """
    acc = {"NCT": set(), "PMID": set(), "DOI": set()}
    for txt in tool_results:
        if not isinstance(txt, str):
            continue
        extracted = extract_citations(txt)
        for k in acc:
            acc[k].update(extracted[k])
    return acc


def format_verification_block(verifications: list[Verification]) -> str:
    """Render a markdown warning block to append to the response.

    Returns empty string if everything verified clean.
    """
    problems = [v for v in verifications if v.status in ("not_from_search", "not_found")]
    # `unknown` NCTs are expected (ClinicalTrials.gov blocks CDN); don't count
    # those as warnings — only unknown PMIDs/DOIs are worth noting.
    unknown_nonNCT = [v for v in verifications if v.status == "unknown" and v.kind != "NCT"]

    if not problems:
        return ""

    lines = ["", "---", "", "### ⚠️ Citation verification"]
    lines.append("")
    lines.append(
        "Automated post-check flagged these citations. They may be fabricated or mistyped — "
        "verify manually before acting on them:"
    )
    lines.append("")
    for v in problems:
        if v.status == "not_from_search":
            badge = "🚫 **not in search results**"
        else:  # not_found
            badge = "❌ **not found**"
        lines.append(f"- {badge} — {v.kind} `{v.value}`" + (f": {v.detail}" if v.detail else ""))

    if unknown_nonNCT:
        lines.append("")
        lines.append(f"<sub>{len(unknown_nonNCT)} citation(s) could not be verified due to network issues; these may still be valid.</sub>")

    return "\n".join(lines) + "\n"
