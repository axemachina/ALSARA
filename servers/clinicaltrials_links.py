#!/usr/bin/env python3
"""
Simplified ClinicalTrials.gov Link Generator
Provides direct links and known trials as fallback when AACT is unavailable
"""

from mcp.server.fastmcp import FastMCP
import logging
from typing import Optional
from urllib.parse import quote_plus

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("clinicaltrials-links")

# Known important ALS trials (updated periodically)
KNOWN_ALS_TRIALS = {
    "NCT05112094": {
        "title": "Tofersen (ATLAS)",
        "description": "SOD1-targeted antisense therapy for SOD1-ALS",
        "status": "Active",
        "sponsor": "Biogen"
    },
    "NCT04856982": {
        "title": "HEALEY ALS Platform Trial",
        "description": "Multiple drugs tested simultaneously",
        "status": "Recruiting",
        "sponsor": "Massachusetts General Hospital"
    },
    "NCT04768972": {
        "title": "Ravulizumab",
        "description": "Complement C5 inhibition",
        "status": "Active",
        "sponsor": "Alexion"
    },
    "NCT05370950": {
        "title": "Pridopidine",
        "description": "Sigma-1 receptor agonist",
        "status": "Recruiting",
        "sponsor": "Prilenia"
    },
    "NCT04632225": {
        "title": "NurOwn",
        "description": "MSC-NTF cells (mesenchymal stem cells)",
        "status": "Active",
        "sponsor": "BrainStorm Cell"
    },
    "NCT07204977": {
        "title": "Acamprosate",
        "description": "C9orf72 hexanucleotide repeat expansion treatment",
        "status": "Recruiting",
        "sponsor": "Mayo Clinic"
    },
    "NCT07161999": {
        "title": "COYA 302",
        "description": "Regulatory T-cell therapy",
        "status": "Recruiting",
        "sponsor": "Coya Therapeutics"
    },
    "NCT07023835": {
        "title": "Usnoflast",
        "description": "Anti-inflammatory for ALS",
        "status": "Recruiting",
        "sponsor": "Seelos Therapeutics"
    }
}


@mcp.tool()
async def get_trial_link(nct_id: str) -> str:
    """Generate direct link to a ClinicalTrials.gov trial page.

    Args:
        nct_id: NCT identifier (e.g., 'NCT05112094')
    """
    nct_id = nct_id.upper()
    url = f"https://clinicaltrials.gov/study/{nct_id}"

    result = f"**Direct link to trial {nct_id}:**\n{url}\n\n"

    # Add info if it's a known trial
    if nct_id in KNOWN_ALS_TRIALS:
        trial = KNOWN_ALS_TRIALS[nct_id]
        result += f"**{trial['title']}**\n"
        result += f"Description: {trial['description']}\n"
        result += f"Status: {trial['status']}\n"
        result += f"Sponsor: {trial['sponsor']}\n"

    return result


@mcp.tool()
async def get_search_link(
    condition: str = "ALS",
    status: Optional[str] = None,
    intervention: Optional[str] = None,
    location: Optional[str] = None
) -> str:
    """Generate direct search link for ClinicalTrials.gov.

    Args:
        condition: Medical condition (default: ALS)
        status: Trial status (recruiting, active, completed)
        intervention: Treatment/drug name
        location: Country or city
    """
    base_url = "https://clinicaltrials.gov/search"
    params = []

    # Add condition
    params.append(f"cond={quote_plus(condition)}")

    # Map status to ClinicalTrials.gov format
    if status:
        status_lower = status.lower()
        if "recruit" in status_lower:
            params.append("recrs=a")  # Recruiting
        elif "active" in status_lower:
            params.append("recrs=d")  # Active, not recruiting
        elif "complet" in status_lower:
            params.append("recrs=e")  # Completed

    # Add intervention
    if intervention:
        params.append(f"intr={quote_plus(intervention)}")

    # Add location
    if location:
        params.append(f"locn={quote_plus(location)}")

    # Build URL
    search_url = f"{base_url}?{'&'.join(params)}"

    result = f"**Direct search on ClinicalTrials.gov:**\n\n"
    result += f"Search parameters:\n"
    result += f"- Condition: {condition}\n"
    if status:
        result += f"- Status: {status}\n"
    if intervention:
        result += f"- Intervention: {intervention}\n"
    if location:
        result += f"- Location: {location}\n"
    result += f"\n🔗 **Search URL:** {search_url}\n"
    result += f"\nClick the link above to see results on ClinicalTrials.gov"

    return result


@mcp.tool()
async def get_known_als_trials(
    status_filter: Optional[str] = None
) -> str:
    """Get list of known important ALS trials.

    Args:
        status_filter: Filter by status (recruiting, active, all)
    """
    result = "**Important ALS Clinical Trials:**\n\n"

    if not KNOWN_ALS_TRIALS:
        return "No known trials available in offline database."

    count = 0
    for nct_id, trial in KNOWN_ALS_TRIALS.items():
        # Apply status filter if provided
        if status_filter:
            filter_lower = status_filter.lower()
            trial_status = trial['status'].lower()

            if filter_lower == "recruiting" and "recruit" not in trial_status:
                continue
            elif filter_lower == "active" and "active" not in trial_status:
                continue
            elif filter_lower == "completed" and "complet" not in trial_status:
                continue

        count += 1
        result += f"{count}. **{trial['title']}** ({nct_id})\n"
        result += f"   {trial['description']}\n"
        result += f"   Status: {trial['status']} | Sponsor: {trial['sponsor']}\n"
        result += f"   🔗 https://clinicaltrials.gov/study/{nct_id}\n\n"

    if count == 0:
        result += f"No trials found with status filter: {status_filter}\n"
    else:
        result += f"\n📌 *This is a curated list. For comprehensive search, use AACT database server.*"

    return result


@mcp.tool()
async def get_trial_resources() -> str:
    """Get helpful resources for finding clinical trials."""

    resources = """**Clinical Trials Resources for ALS:**

**Official Databases:**
1. **ClinicalTrials.gov**: https://clinicaltrials.gov/search?cond=ALS
   - Official US trials registry
   - Most comprehensive for US trials

2. **WHO ICTRP**: https://trialsearch.who.int/
   - International trials from all countries
   - Includes non-US trials

3. **EU Clinical Trials Register**: https://www.clinicaltrialsregister.eu/
   - European trials database

**ALS-Specific Resources:**
1. **Northeast ALS Consortium (NEALS)**: https://www.neals.org/
   - Network of ALS clinical trial sites
   - Trial matching service

2. **ALS Therapy Development Institute**: https://www.als.net/clinical-trials/
   - Independent ALS research organization
   - Trial tracker and updates

3. **I AM ALS Registry**: https://iamals.org/get-help/clinical-trials/
   - Patient-focused trial information
   - Trial matching assistance

**Major ALS Clinical Centers:**
- Massachusetts General Hospital (Healey Center)
- Johns Hopkins ALS Clinic
- Mayo Clinic ALS Center
- Cleveland Clinic Lou Ruvo Center
- UCSF ALS Center

**Tips for Finding Trials:**
1. Use condition terms: "ALS", "Amyotrophic Lateral Sclerosis", "Motor Neuron Disease"
2. Check recruiting AND not-yet-recruiting trials
3. Consider trials at different phases (1, 2, 3)
4. Look for platform trials testing multiple drugs
5. Contact trial coordinators directly for eligibility

**Note:** For programmatic access to trial data, use the AACT database server which provides complete ClinicalTrials.gov data without API restrictions.
"""

    return resources


if __name__ == "__main__":
    mcp.run(transport="stdio")