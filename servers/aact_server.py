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
            phase_map = {
                'PHASE_1': 'Phase 1',
                'PHASE_2': 'Phase 2',
                'PHASE_3': 'Phase 3',
                'PHASE_4': 'Phase 4',
                'EARLY_PHASE_1': 'Early Phase 1'
            }
            mapped_phase = phase_map.get(phase.upper(), phase)
            conditions.append(f"s.phase = ${param_count}")
            params.append(mapped_phase)
            param_count += 1

        if intervention:
            conditions.append(f"LOWER(i.name) LIKE ${param_count}")
            params.append(f"%{intervention.lower()}%")
            param_count += 1

        if location:
            base_query = base_query.replace("LEFT JOIN facilities f", "INNER JOIN facilities f")
            conditions.append(f"(LOWER(f.country) LIKE ${param_count} OR LOWER(f.state) LIKE ${param_count})")
            params.append(f"%{location.lower()}%")
            param_count += 1

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
            s.first_posted_date,
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
        SELECT outcome_type, measure, time_frame, description
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