#!/usr/bin/env python3
"""
AACT Database MCP Server with Connection Pooling
Provides access to ClinicalTrials.gov data through the AACT PostgreSQL database.

AACT (Aggregate Analysis of ClinicalTrials.gov) is maintained by Duke University
and FDA, providing complete ClinicalTrials.gov data updated daily.

Database access: aact-db.ctti-clinicaltrials.org
"""

import os
import sys
import json
import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path for shared imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.config import config

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        logging.info(f"Loaded .env file from {env_path}")
except ImportError:
    pass

# Try both asyncpg (preferred) and psycopg2 (fallback)
try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

from mcp.server.fastmcp import FastMCP

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize MCP server
mcp = FastMCP("aact-database")

# Intervention synonym map — AACT stores trials with a single canonical
# intervention name (e.g., "Acetyl-l-carnitine"), so a search for the common
# abbreviation "ALCAR" never matches. Each key gets expanded into an OR-search
# across all listed forms (lowercased, substring match).
_INTERVENTION_SYNONYMS = {
    # ALS supplements / nutritional
    "alcar": ["acetyl-l-carnitine", "acetyl l carnitine", "levocarnitine", "acetylcarnitine"],
    "acetyl-l-carnitine": ["alcar", "levocarnitine", "acetylcarnitine"],
    "carnitine": ["acetyl-l-carnitine", "alcar", "levocarnitine"],
    "vitamin d": ["cholecalciferol", "ergocalciferol", "vitamin d3", "vitamin d2", "calcitriol"],
    "omega-3": ["dha", "epa", "docosahexaenoic", "eicosapentaenoic", "fish oil"],
    "omega 3": ["dha", "epa", "docosahexaenoic", "eicosapentaenoic", "fish oil"],
    "coenzyme q10": ["coq10", "ubiquinone", "ubiquinol"],
    "coq10": ["coenzyme q10", "ubiquinone", "ubiquinol"],
    "creatine": ["creatine monohydrate"],
    # Approved + emerging ALS drugs (research code ↔ brand/generic)
    "tofersen": ["biib067", "qalsody"],
    "biib067": ["tofersen", "qalsody"],
    "qalsody": ["tofersen", "biib067"],
    "edaravone": ["radicava", "mci-186"],
    "radicava": ["edaravone"],
    "amx0035": ["relyvrio", "albrioza", "sodium phenylbutyrate", "taurursodiol", "tudca"],
    "relyvrio": ["amx0035", "sodium phenylbutyrate", "taurursodiol"],
    "masitinib": ["ab1010"],
    "reldesemtiv": ["ck-2127107", "ck2127107"],
    "ck-2127107": ["reldesemtiv"],
    "arimoclomol": [],
    "pridopidine": [],
    "ravulizumab": ["ultomiris"],
    "cnm-au8": ["cnmau8", "gold nanocrystal"],
    "cuatsm": ["copper-atsm", "copper atsm"],
    "verdiperstat": ["bhv-3241", "azd3241"],
    "zilucoplan": [],
    "ezogabine": ["retigabine"],
    # Cell therapies
    "nurown": ["msc-ntf", "debamestrocel"],
    "msc-ntf": ["nurown", "debamestrocel"],
    # Riluzole forms
    "riluzole": ["rilutek", "tiglutik", "exservan"],
}


def _expand_intervention_synonyms(intervention: str) -> list[str]:
    """Return all known forms of an intervention (lowercase, deduped)."""
    key = intervention.lower().strip()
    forms = {key}
    if key in _INTERVENTION_SYNONYMS:
        forms.update(_INTERVENTION_SYNONYMS[key])
    return sorted(forms)


# Database configuration
AACT_HOST = os.getenv("AACT_HOST", "aact-db.ctti-clinicaltrials.org")
AACT_PORT = os.getenv("AACT_PORT", "5432")
AACT_DB = os.getenv("AACT_DB", "aact")
AACT_USER = os.getenv("AACT_USER", "aact")
AACT_PASSWORD = os.getenv("AACT_PASSWORD", "")

# Global connection pool (initialized once)
_connection_pool: Optional[asyncpg.Pool] = None

async def get_connection_pool() -> asyncpg.Pool:
    """Get or create the global connection pool"""
    global _connection_pool

    if _connection_pool is None or _connection_pool._closed:
        logger.info("Creating new database connection pool...")

        # Build connection URL
        if AACT_PASSWORD:
            dsn = f"postgresql://{AACT_USER}:{AACT_PASSWORD}@{AACT_HOST}:{AACT_PORT}/{AACT_DB}"
        else:
            dsn = f"postgresql://{AACT_USER}@{AACT_HOST}:{AACT_PORT}/{AACT_DB}"

        try:
            _connection_pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=2,    # Minimum connections in pool
                max_size=10,   # Maximum connections in pool
                max_queries=50000,  # Max queries per connection before recycling
                max_inactive_connection_lifetime=300,  # Close idle connections after 5 min
                command_timeout=60.0,  # Query timeout
                statement_cache_size=20,  # Cache prepared statements
            )
            logger.info("Connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise

    return _connection_pool

async def execute_query_pooled(query: str, params: tuple = ()) -> List[Dict]:
    """Execute query using connection pool (asyncpg)"""
    pool = await get_connection_pool()

    async with pool.acquire() as conn:
        # Convert rows to dicts
        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]

def execute_query_sync(query: str, params: tuple = ()) -> List[Dict]:
    """Fallback: Execute query synchronously (psycopg2)"""
    conn = None
    cursor = None
    try:
        # Build connection string
        conn_params = {
            "host": AACT_HOST,
            "port": AACT_PORT,
            "dbname": AACT_DB,
            "user": AACT_USER,
        }

        if AACT_PASSWORD:
            conn_params["password"] = AACT_PASSWORD

        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query, params)
        results = cursor.fetchall()

        return [dict(row) for row in results]

    except Exception as e:
        logger.error(f"Database query failed: {e}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

async def execute_query(query: str, params: tuple = ()) -> List[Dict]:
    """Execute query using best available method"""
    if ASYNCPG_AVAILABLE:
        # Prefer asyncpg with connection pooling
        return await execute_query_pooled(query, params)
    elif POSTGRES_AVAILABLE:
        # Fallback to synchronous psycopg2
        return await asyncio.to_thread(execute_query_sync, query, params)
    else:
        raise RuntimeError("No PostgreSQL driver available (install asyncpg or psycopg2)")

@mcp.tool()
async def search_als_trials(
    status: Optional[str] = "RECRUITING",
    phase: Optional[str] = None,
    intervention: Optional[str] = None,
    location: Optional[str] = None,
    max_results: int = 20
) -> str:
    """Search for ALS clinical trials in the AACT database.

    Args:
        status: Trial status (RECRUITING, ENROLLING_BY_INVITATION, ACTIVE_NOT_RECRUITING, COMPLETED)
        phase: Trial phase (PHASE_1, PHASE_2, PHASE_3, PHASE_4, EARLY_PHASE_1)
        intervention: Type of intervention to search for
        location: Country or region
        max_results: Maximum number of results to return
    """

    if not (ASYNCPG_AVAILABLE or POSTGRES_AVAILABLE):
        return json.dumps({
            "error": "Database not available",
            "message": "PostgreSQL driver not installed. Install asyncpg or psycopg2-binary."
        })

    logger.info(f"🔎 AACT Search: status={status}, phase={phase}, intervention={intervention}, location={location}")

    try:
        # Build the query with proper filters
        base_query = """
        SELECT
            s.nct_id,
            s.brief_title,
            s.overall_status,
            s.phase,
            s.enrollment,
            s.start_date,
            s.completion_date,
            s.study_type,
            s.official_title,
            d.name as sponsor,
            STRING_AGG(DISTINCT i.name, ', ') as interventions,
            STRING_AGG(DISTINCT c.name, ', ') as conditions,
            COUNT(DISTINCT f.id) as num_locations
        FROM studies s
        LEFT JOIN sponsors sp ON s.nct_id = sp.nct_id AND sp.lead_or_collaborator = 'lead'
        LEFT JOIN responsible_parties d ON sp.nct_id = d.nct_id
        LEFT JOIN interventions i ON s.nct_id = i.nct_id
        LEFT JOIN conditions c ON s.nct_id = c.nct_id
        LEFT JOIN facilities f ON s.nct_id = f.nct_id
        WHERE (
            LOWER(c.name) LIKE '%amyotrophic lateral sclerosis%' OR
            LOWER(c.name) LIKE '%als %' OR
            LOWER(c.name) LIKE '% als' OR
            LOWER(c.name) LIKE '%motor neuron disease%' OR
            LOWER(c.name) LIKE '%lou gehrig%' OR
            LOWER(s.brief_title) LIKE '%amyotrophic lateral sclerosis%' OR
            LOWER(s.brief_title) LIKE '%als %' OR
            LOWER(s.brief_title) LIKE '% als' OR
            LOWER(s.official_title) LIKE '%amyotrophic lateral sclerosis%' OR
            LOWER(s.official_title) LIKE '%als %' OR
            LOWER(s.official_title) LIKE '% als'
        )
        """

        # Apply filters
        conditions = []
        params = []
        param_count = 1

        if status:
            conditions.append(f"UPPER(s.overall_status) = ${param_count}")
            params.append(status.upper())
            param_count += 1

        if phase:
            # Normalize phase input to match DB values (PHASE1, PHASE2, PHASE3, etc.)
            normalized = phase.upper().replace(' ', '').replace('_', '')
            # Also match combined phases like PHASE1/PHASE2, PHASE2/PHASE3
            conditions.append(f"UPPER(REPLACE(s.phase, '/', '/')) LIKE ${param_count}")
            params.append(f"%{normalized}%")
            param_count += 1

        if intervention:
            # Expand abbreviations (e.g. ALCAR → acetyl-l-carnitine) so a search
            # for the abbreviation matches the canonical name AACT actually stores.
            forms = _expand_intervention_synonyms(intervention)
            like_clauses = []
            for form in forms:
                like_clauses.append(f"LOWER(i.name) LIKE ${param_count}")
                params.append(f"%{form}%")
                param_count += 1
            conditions.append("(" + " OR ".join(like_clauses) + ")")

        if location:
            base_query = base_query.replace("LEFT JOIN facilities f", "INNER JOIN facilities f")
            conditions.append(f"(LOWER(f.country) LIKE ${param_count} OR LOWER(f.state) LIKE ${param_count + 1})")
            params.append(f"%{location.lower()}%")
            params.append(f"%{location.lower()}%")
            param_count += 2

        # Add conditions to query
        if conditions:
            base_query += " AND " + " AND ".join(conditions)

        # Add GROUP BY and ORDER BY
        base_query += f"""
        GROUP BY s.nct_id, s.brief_title, s.overall_status, s.phase,
                 s.enrollment, s.start_date, s.completion_date,
                 s.study_type, s.official_title, d.name
        ORDER BY
            CASE s.overall_status
                WHEN 'RECRUITING' THEN 1
                WHEN 'ENROLLING_BY_INVITATION' THEN 2
                WHEN 'ACTIVE_NOT_RECRUITING' THEN 3
                WHEN 'NOT_YET_RECRUITING' THEN 4
                ELSE 5
            END,
            s.start_date DESC NULLS LAST
        LIMIT ${param_count}
        """
        params.append(max_results)

        # Execute query
        logger.debug(f"📊 Executing query with {len(params)} parameters")
        results = await execute_query(base_query, tuple(params))

        logger.info(f"✅ AACT Results: Found {len(results) if results else 0} trials")

        if not results:
            return json.dumps({
                "message": "No ALS trials found matching your criteria",
                "total": 0,
                "trials": []
            })

        # Format results
        trials = []
        for row in results:
            trial = {
                "nct_id": row['nct_id'],
                "title": row['brief_title'],
                "status": row['overall_status'],
                "phase": row['phase'],
                "enrollment": row['enrollment'],
                "sponsor": row['sponsor'],
                "interventions": row['interventions'],
                "conditions": row['conditions'],
                "locations_count": row['num_locations'],
                "start_date": str(row['start_date']) if row['start_date'] else None,
                "completion_date": str(row['completion_date']) if row['completion_date'] else None,
                "url": f"https://clinicaltrials.gov/study/{row['nct_id']}"
            }
            trials.append(trial)

        return json.dumps({
            "message": f"Found {len(trials)} ALS clinical trials",
            "total": len(trials),
            "trials": trials
        }, indent=2)

    except Exception as e:
        logger.error(f"❌ AACT Database query failed: {e}")
        logger.error(f"   Query type: search_als_trials")
        logger.error(f"   Parameters: status={status}, phase={phase}, intervention={intervention}")
        return json.dumps({
            "error": "Database query failed",
            "message": str(e)
        })

@mcp.tool()
async def get_trial_details(nct_id: str) -> str:
    """Get detailed information about a specific clinical trial.

    Args:
        nct_id: The NCT ID of the trial (e.g., 'NCT04856982')
    """

    if not (ASYNCPG_AVAILABLE or POSTGRES_AVAILABLE):
        return json.dumps({
            "error": "Database not available",
            "message": "PostgreSQL driver not installed."
        })

    try:
        # Main trial information
        main_query = """
        SELECT
            s.nct_id,
            s.brief_title,
            s.official_title,
            s.overall_status,
            s.phase,
            s.study_type,
            s.enrollment,
            s.start_date,
            s.primary_completion_date,
            s.completion_date,
            s.study_first_posted_date as first_posted_date,
            s.last_update_posted_date,
            s.why_stopped,
            b.description as brief_summary,
            dd.description as detailed_description,
            e.criteria as eligibility_criteria,
            e.gender,
            e.minimum_age,
            e.maximum_age,
            e.healthy_volunteers,
            rp.name as sponsor,
            rp.responsible_party_type
        FROM studies s
        LEFT JOIN brief_summaries b ON s.nct_id = b.nct_id
        LEFT JOIN detailed_descriptions dd ON s.nct_id = dd.nct_id
        LEFT JOIN eligibilities e ON s.nct_id = e.nct_id
        LEFT JOIN responsible_parties rp ON s.nct_id = rp.nct_id
        WHERE s.nct_id = $1
        """

        results = await execute_query(main_query, (nct_id,))

        if not results:
            return json.dumps({
                "error": "Trial not found",
                "message": f"No trial found with NCT ID: {nct_id}"
            })

        trial_info = results[0]

        # Get outcomes
        outcomes_query = """
        SELECT outcome_type, title as measure, time_frame, description
        FROM outcomes
        WHERE nct_id = $1
        ORDER BY outcome_type, id
        LIMIT 20
        """
        outcomes = await execute_query(outcomes_query, (nct_id,))

        # Get interventions
        interventions_query = """
        SELECT intervention_type, name, description
        FROM interventions
        WHERE nct_id = $1
        """
        interventions = await execute_query(interventions_query, (nct_id,))

        # Get locations
        locations_query = """
        SELECT name, city, state, country, status
        FROM facilities
        WHERE nct_id = $1
        LIMIT 50
        """
        locations = await execute_query(locations_query, (nct_id,))

        # Format the response
        return json.dumps({
            "nct_id": trial_info['nct_id'],
            "title": trial_info['brief_title'],
            "official_title": trial_info['official_title'],
            "status": trial_info['overall_status'],
            "phase": trial_info['phase'],
            "study_type": trial_info['study_type'],
            "enrollment": trial_info['enrollment'],
            "sponsor": trial_info['sponsor'],
            "dates": {
                "start": str(trial_info['start_date']) if trial_info['start_date'] else None,
                "primary_completion": str(trial_info['primary_completion_date']) if trial_info['primary_completion_date'] else None,
                "completion": str(trial_info['completion_date']) if trial_info['completion_date'] else None,
                "first_posted": str(trial_info['first_posted_date']) if trial_info['first_posted_date'] else None,
                "last_updated": str(trial_info['last_update_posted_date']) if trial_info['last_update_posted_date'] else None
            },
            "summary": trial_info['brief_summary'],
            "detailed_description": trial_info['detailed_description'],
            "eligibility": {
                "criteria": trial_info['eligibility_criteria'],
                "gender": trial_info['gender'],
                "age_range": f"{trial_info['minimum_age'] or 'N/A'} - {trial_info['maximum_age'] or 'N/A'}",
                "healthy_volunteers": trial_info['healthy_volunteers']
            },
            "outcomes": [
                {
                    "type": o['outcome_type'],
                    "measure": o['measure'],
                    "time_frame": o['time_frame'],
                    "description": o['description']
                } for o in outcomes
            ],
            "interventions": [
                {
                    "type": i['intervention_type'],
                    "name": i['name'],
                    "description": i['description']
                } for i in interventions
            ],
            "locations": [
                {
                    "name": l['name'],
                    "city": l['city'],
                    "state": l['state'],
                    "country": l['country'],
                    "status": l['status']
                } for l in locations
            ],
            "url": f"https://clinicaltrials.gov/study/{nct_id}"
        }, indent=2)

    except Exception as e:
        logger.error(f"Failed to get trial details: {e}")
        return json.dumps({
            "error": "Database query failed",
            "message": str(e)
        })

@mcp.tool()
async def find_trials_near_me(
    zip_code: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius_miles: int = 200,
    status: str = "RECRUITING",
    subtype: Optional[str] = None,
    max_results: int = 25,
) -> str:
    """Find ALS clinical trials near a location. Provide EITHER zip_code, city+state, OR latitude+longitude.

    Args:
        zip_code: US ZIP code (e.g., '10001' for NYC). Preferred for US locations.
        city: City name (e.g., 'Boston'). Use with state for best results.
        state: US state name (e.g., 'Massachusetts') or country for international.
        latitude: Latitude coordinate (e.g., 40.7128 for NYC).
        longitude: Longitude coordinate (e.g., -74.0060 for NYC).
        radius_miles: Search radius in miles (default: 200, max: 500). Use 300+ for European countries.
        status: Trial status filter (RECRUITING, ACTIVE_NOT_RECRUITING, COMPLETED).
        subtype: ALS subtype filter — one of: SOD1, C9orf72, FUS, TDP-43, bulbar, limb, familial, sporadic.
        max_results: Maximum results (default: 15).
    """
    if not (ASYNCPG_AVAILABLE or POSTGRES_AVAILABLE):
        return json.dumps({"error": "Database not available"})

    radius_miles = min(radius_miles, 500)

    # Resolve location to coordinates
    lat, lng = None, None
    location_label = ""

    if latitude is not None and longitude is not None:
        lat, lng = latitude, longitude
        location_label = f"({lat:.2f}, {lng:.2f})"
    elif zip_code or (city and state):
        # Look up coordinates from the facilities table itself
        if zip_code:
            lookup_query = """
                SELECT latitude, longitude, city, state
                FROM ctgov.facilities
                WHERE zip LIKE $1 AND latitude IS NOT NULL
                LIMIT 1
            """
            rows = await execute_query(lookup_query, (f"{zip_code}%",))
            location_label = f"ZIP {zip_code}"
        else:
            # Try city+state first, then city-only fallback (state values are inconsistent internationally)
            lookup_query = """
                SELECT latitude, longitude, city, state
                FROM ctgov.facilities
                WHERE LOWER(city) = $1 AND LOWER(state) = $2 AND latitude IS NOT NULL
                LIMIT 1
            """
            rows = await execute_query(lookup_query, (city.lower(), state.lower()))
            location_label = f"{city}, {state}"

            if not rows:
                # Fallback: city only (handles international locations with non-standard state values)
                lookup_query = """
                    SELECT latitude, longitude, city, state, country
                    FROM ctgov.facilities
                    WHERE LOWER(city) = $1 AND latitude IS NOT NULL
                    LIMIT 1
                """
                rows = await execute_query(lookup_query, (city.lower(),))

        if rows:
            lat = float(rows[0]['latitude'])
            lng = float(rows[0]['longitude'])
            location_label = f"{rows[0]['city']}, {rows[0].get('state') or rows[0].get('country', '')}"
        else:
            return json.dumps({
                "error": f"Could not find coordinates for {location_label}. Try providing latitude/longitude directly, or use a nearby major city."
            })
    elif city:
        # City without state — try best match
        lookup_query = """
            SELECT latitude, longitude, city, state, country
            FROM ctgov.facilities
            WHERE LOWER(city) = $1 AND latitude IS NOT NULL
            LIMIT 1
        """
        rows = await execute_query(lookup_query, (city.lower(),))
        if rows:
            lat = float(rows[0]['latitude'])
            lng = float(rows[0]['longitude'])
            location_label = f"{rows[0]['city']}, {rows[0].get('state') or rows[0].get('country', '')}"
        else:
            return json.dumps({"error": f"Could not find coordinates for '{city}'. Try adding state or country."})
    else:
        return json.dumps({"error": "Please provide a location: zip_code, city+state, or latitude+longitude."})

    logger.info(f"Searching ALS trials within {radius_miles} miles of {location_label} ({lat}, {lng})")

    # Build subtype condition
    subtype_condition = ""
    subtype_params = []
    param_offset = 4  # $1=lat, $2=lng, $3=radius, $4 onward

    if subtype:
        subtype_lower = subtype.lower().strip()
        subtype_map = {
            "sod1": ["sod1", "superoxide dismutase"],
            "c9orf72": ["c9orf72", "c9", "chromosome 9"],
            "fus": ["fus", "fused in sarcoma"],
            "tdp-43": ["tdp-43", "tdp43", "tardbp"],
            "bulbar": ["bulbar"],
            "limb": ["limb-onset", "limb onset", "spinal onset"],
            "familial": ["familial", "fals", "genetic"],
            "sporadic": ["sporadic", "sals"],
        }
        terms = subtype_map.get(subtype_lower, [subtype_lower])
        like_clauses = []
        for term in terms:
            like_clauses.append(f"LOWER(s.brief_title) LIKE ${param_offset}")
            subtype_params.append(f"%{term}%")
            param_offset += 1
            like_clauses.append(f"LOWER(s.official_title) LIKE ${param_offset}")
            subtype_params.append(f"%{term}%")
            param_offset += 1
            like_clauses.append(f"LOWER(COALESCE(i.name, '')) LIKE ${param_offset}")
            subtype_params.append(f"%{term}%")
            param_offset += 1
        subtype_condition = f"AND ({' OR '.join(like_clauses)})"

    # Status condition
    status_condition = ""
    if status:
        status_condition = f"AND UPPER(s.overall_status) = ${param_offset}"
        subtype_params.append(status.upper())
        param_offset += 1

    query = f"""
        SELECT t.*, iv.interventions FROM (
            SELECT DISTINCT ON (s.nct_id)
                s.nct_id, s.brief_title, s.overall_status, s.phase,
                s.enrollment, s.start_date,
                f.name as facility, f.city, f.state, f.zip, f.country, f.status as site_status,
                (3959 * acos(
                    LEAST(1.0, GREATEST(-1.0,
                        cos(radians($1)) * cos(radians(f.latitude)) *
                        cos(radians(f.longitude) - radians($2)) +
                        sin(radians($1)) * sin(radians(f.latitude))
                    ))
                )) as distance_miles
            FROM ctgov.facilities f
            JOIN ctgov.studies s ON f.nct_id = s.nct_id
            JOIN ctgov.conditions c ON s.nct_id = c.nct_id
            LEFT JOIN ctgov.interventions i ON s.nct_id = i.nct_id
            WHERE f.latitude IS NOT NULL AND f.longitude IS NOT NULL
            AND (
                LOWER(c.name) LIKE '%amyotrophic lateral sclerosis%' OR
                LOWER(c.name) LIKE '%motor neuron disease%'
            )
            AND (3959 * acos(
                LEAST(1.0, GREATEST(-1.0,
                    cos(radians($1)) * cos(radians(f.latitude)) *
                    cos(radians(f.longitude) - radians($2)) +
                    sin(radians($1)) * sin(radians(f.latitude))
                ))
            )) < $3
            {subtype_condition}
            {status_condition}
            ORDER BY s.nct_id, distance_miles
        ) t
        LEFT JOIN LATERAL (
            SELECT STRING_AGG(DISTINCT name, ', ') as interventions
            FROM ctgov.interventions WHERE nct_id = t.nct_id
        ) iv ON true
    """

    params = (lat, lng, float(radius_miles), *subtype_params)

    try:
        results = await execute_query(query, params)

        # Sort by distance and limit
        results.sort(key=lambda r: float(r['distance_miles']))
        results = results[:max_results]

        if not results:
            hint = ""
            if radius_miles < 200:
                hint = f" Try increasing radius_miles (currently {radius_miles})."
            if subtype:
                hint += f" Try removing the '{subtype}' subtype filter for broader results."
            return json.dumps({
                "message": f"No recruiting ALS trials found within {radius_miles} miles of {location_label}.{hint}",
                "total": 0, "trials": []
            })

        trials = []
        for r in results:
            trials.append({
                "nct_id": r['nct_id'],
                "title": r['brief_title'],
                "distance_miles": round(float(r['distance_miles']), 1),
                "facility": r['facility'],
                "location": f"{r['city']}, {r['state'] or ''} {r['zip'] or ''}".strip(),
                "country": r['country'],
                "site_status": r['site_status'],
                "status": r['overall_status'],
                "phase": r['phase'],
                "interventions": r['interventions'],
                "url": f"https://clinicaltrials.gov/study/{r['nct_id']}"
            })

        return json.dumps({
            "message": f"Found {len(trials)} ALS trials within {radius_miles} miles of {location_label}",
            "search_center": location_label,
            "radius_miles": radius_miles,
            "total": len(trials),
            "trials": trials
        }, indent=2)

    except Exception as e:
        logger.error(f"Proximity search failed: {e}")
        return json.dumps({"error": "Search failed", "message": str(e)})


@mcp.tool()
async def check_new_als_trials(
    days_back: int = 30,
    subtype: Optional[str] = None,
    status: str = "RECRUITING",
) -> str:
    """Check for ALS trials posted or updated recently. Use this to monitor for new developments.

    Args:
        days_back: How many days back to check (default: 30, max: 365).
        subtype: ALS subtype filter — one of: SOD1, C9orf72, FUS, TDP-43, bulbar, limb, familial, sporadic.
        status: Trial status filter (default: RECRUITING). Use 'ANY' for all statuses.
    """
    if not (ASYNCPG_AVAILABLE or POSTGRES_AVAILABLE):
        return json.dumps({"error": "Database not available"})

    days_back = min(days_back, 365)
    cutoff_date = (datetime.now() - timedelta(days=days_back)).date()

    logger.info(f"Checking for new ALS trials since {cutoff_date}, subtype={subtype}, status={status}")

    # Build subtype condition
    subtype_condition = ""
    params = [cutoff_date]
    param_count = 2

    if subtype:
        subtype_lower = subtype.lower().strip()
        subtype_map = {
            "sod1": ["sod1", "superoxide dismutase"],
            "c9orf72": ["c9orf72", "c9", "chromosome 9"],
            "fus": ["fus", "fused in sarcoma"],
            "tdp-43": ["tdp-43", "tdp43", "tardbp"],
            "bulbar": ["bulbar"],
            "limb": ["limb-onset", "limb onset", "spinal onset"],
            "familial": ["familial", "fals", "genetic"],
            "sporadic": ["sporadic", "sals"],
        }
        terms = subtype_map.get(subtype_lower, [subtype_lower])
        like_clauses = []
        for term in terms:
            like_clauses.append(f"LOWER(s.brief_title) LIKE ${param_count}")
            params.append(f"%{term}%")
            param_count += 1
            like_clauses.append(f"LOWER(s.official_title) LIKE ${param_count}")
            params.append(f"%{term}%")
            param_count += 1
        subtype_condition = f"AND ({' OR '.join(like_clauses)})"

    status_condition = ""
    if status and status.upper() != "ANY":
        status_condition = f"AND UPPER(s.overall_status) = ${param_count}"
        params.append(status.upper())
        param_count += 1

    query = f"""
        SELECT
            s.nct_id, s.brief_title, s.overall_status, s.phase,
            s.enrollment, s.start_date,
            s.study_first_posted_date as first_posted_date, s.last_update_posted_date,
            STRING_AGG(DISTINCT i.name, ', ') as interventions,
            STRING_AGG(DISTINCT c.name, ', ') as conditions,
            COUNT(DISTINCT f.id) as num_locations
        FROM ctgov.studies s
        JOIN ctgov.conditions c ON s.nct_id = c.nct_id
        LEFT JOIN ctgov.interventions i ON s.nct_id = i.nct_id
        LEFT JOIN ctgov.facilities f ON s.nct_id = f.nct_id
        WHERE (
            LOWER(c.name) LIKE '%amyotrophic lateral sclerosis%' OR
            LOWER(c.name) LIKE '%motor neuron disease%'
        )
        AND (s.study_first_posted_date >= $1 OR s.last_update_posted_date >= $1)
        {subtype_condition}
        {status_condition}
        GROUP BY s.nct_id, s.brief_title, s.overall_status, s.phase,
                 s.enrollment, s.start_date, s.study_first_posted_date, s.last_update_posted_date
        ORDER BY GREATEST(s.study_first_posted_date, s.last_update_posted_date) DESC NULLS LAST

        LIMIT 25
    """

    try:
        results = await execute_query(query, tuple(params))

        if not results:
            return json.dumps({
                "message": f"No new or updated ALS trials in the last {days_back} days.",
                "period": f"Since {cutoff_date}",
                "total": 0, "trials": []
            })

        # Separate newly posted vs updated
        new_trials = []
        updated_trials = []
        for r in results:
            trial = {
                "nct_id": r['nct_id'],
                "title": r['brief_title'],
                "status": r['overall_status'],
                "phase": r['phase'],
                "enrollment": r['enrollment'],
                "interventions": r['interventions'],
                "num_locations": r['num_locations'],
                "first_posted": str(r['first_posted_date']) if r['first_posted_date'] else None,
                "last_updated": str(r['last_update_posted_date']) if r['last_update_posted_date'] else None,
                "url": f"https://clinicaltrials.gov/study/{r['nct_id']}"
            }
            if r['first_posted_date'] and r['first_posted_date'] >= cutoff_date:
                new_trials.append(trial)
            else:
                updated_trials.append(trial)

        return json.dumps({
            "message": f"Found {len(new_trials)} new and {len(updated_trials)} updated ALS trials since {cutoff_date}",
            "period": f"Last {days_back} days (since {cutoff_date})",
            "subtype_filter": subtype,
            "new_trials": new_trials,
            "updated_trials": updated_trials,
            "total_new": len(new_trials),
            "total_updated": len(updated_trials),
        }, indent=2)

    except Exception as e:
        logger.error(f"New trials check failed: {e}")
        return json.dumps({"error": "Search failed", "message": str(e)})


# Cleanup on shutdown
# Note: FastMCP doesn't have a built-in shutdown handler
# The connection pool will be closed when the process ends
# async def cleanup():
#     """Close the connection pool on shutdown"""
#     global _connection_pool
#     if _connection_pool:
#         await _connection_pool.close()
#         logger.info("Connection pool closed")

if __name__ == "__main__":
    mcp.run()