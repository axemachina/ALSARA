#!/usr/bin/env python3
"""
Test script to verify AACT database and PubMed API configurations from .env file
"""

import os
import sys
import asyncio
from dotenv import load_dotenv
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def test_pubmed_config():
    """Test PubMed configuration"""
    print("\n🔬 Testing PubMed Configuration")
    print("=" * 80)

    pubmed_email = os.getenv("PUBMED_EMAIL")

    if pubmed_email:
        print(f"✅ PubMed email configured: {pubmed_email}")
        print("   This increases rate limits from 3 to 10 requests/second")
    else:
        print("⚠️  No PubMed email configured")
        print("   Rate limit is 3 requests/second (default)")

    # Test actual PubMed API
    try:
        import httpx
        import xml.etree.ElementTree as ET

        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": "ALS",
            "retmax": "1",
            "retmode": "xml"
        }

        if pubmed_email:
            params["email"] = pubmed_email
            params["tool"] = "ALS-Research-Agent"

        with httpx.Client() as client:
            response = client.get(base_url, params=params, timeout=10)

            if response.status_code == 200:
                root = ET.fromstring(response.text)
                count = root.find(".//Count")
                if count is not None:
                    print(f"✅ PubMed API test successful! Found {count.text} ALS articles")
                else:
                    print("⚠️  PubMed API returned unexpected format")
            else:
                print(f"❌ PubMed API returned status {response.status_code}")

    except Exception as e:
        print(f"❌ PubMed API test failed: {e}")

    return pubmed_email is not None


def test_aact_config():
    """Test AACT database configuration"""
    print("\n🗄️ Testing AACT Database Configuration")
    print("=" * 80)

    # Get AACT credentials from environment
    aact_host = os.getenv("AACT_HOST", "aact-db.ctti-clinicaltrials.org")
    aact_port = os.getenv("AACT_PORT", "5432")
    aact_database = os.getenv("AACT_DATABASE", "aact")
    aact_user = os.getenv("AACT_USER", "aact")
    aact_password = os.getenv("AACT_PASSWORD", "aact")

    print(f"Configuration:")
    print(f"  Host: {aact_host}")
    print(f"  Port: {aact_port}")
    print(f"  Database: {aact_database}")
    print(f"  User: {aact_user}")
    print(f"  Password: {'*' * len(aact_password) if aact_password else 'Not set'}")

    # Try to connect to AACT database
    try:
        import psycopg2

        print("\n🔌 Attempting to connect to AACT database...")

        conn = psycopg2.connect(
            host=aact_host,
            port=int(aact_port),
            database=aact_database,
            user=aact_user,
            password=aact_password,
            connect_timeout=10
        )

        print("✅ Successfully connected to AACT database!")

        # Test a simple query
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM studies WHERE nct_id LIKE 'NCT%'")
        count = cursor.fetchone()[0]
        print(f"✅ Database test query successful! Total studies: {count:,}")

        # Search for psilocybin trials
        cursor.execute("""
            SELECT COUNT(DISTINCT s.nct_id)
            FROM studies s
            JOIN interventions i ON s.nct_id = i.nct_id
            WHERE i.name ILIKE '%psilocybin%'
        """)
        psilocybin_count = cursor.fetchone()[0]
        print(f"✅ Found {psilocybin_count} psilocybin trials in database")

        # Check for specific ALS psilocybin trials
        cursor.execute("""
            SELECT DISTINCT s.nct_id, s.brief_title
            FROM studies s
            JOIN conditions c ON s.nct_id = c.nct_id
            JOIN interventions i ON s.nct_id = i.nct_id
            WHERE (c.name ILIKE '%ALS%' OR c.name ILIKE '%amyotrophic lateral sclerosis%')
            AND i.name ILIKE '%psilocybin%'
            LIMIT 5
        """)
        als_psilocybin_trials = cursor.fetchall()

        if als_psilocybin_trials:
            print(f"\n✅ Found {len(als_psilocybin_trials)} ALS + psilocybin trials:")
            for nct_id, title in als_psilocybin_trials:
                print(f"   - {nct_id}: {title[:60]}...")
        else:
            print("\n⚠️  No ALS + psilocybin trials found in current database snapshot")

        cursor.close()
        conn.close()

        return True

    except ImportError:
        print("❌ psycopg2 not installed. Run: pip install psycopg2-binary")
        return False

    except Exception as e:
        print(f"❌ Failed to connect to AACT database: {e}")

        # Check if it's an authentication issue
        if "role" in str(e) and "not permitted" in str(e):
            print("\n⚠️  Authentication issue detected. The public credentials may have changed.")
            print("   Please check https://aact.ctti-clinicaltrials.org/ for current access info.")
        elif "could not translate host name" in str(e):
            print("\n⚠️  Cannot resolve host. Check your internet connection.")
        elif "timeout" in str(e).lower():
            print("\n⚠️  Connection timeout. The server may be temporarily unavailable.")

        return False


async def test_mcp_servers():
    """Test that MCP servers can be initialized with current config"""
    print("\n🔧 Testing MCP Server Initialization")
    print("=" * 80)

    servers_to_test = ["pubmed", "clinicaltrials", "fetch", "aact"]
    results = {}

    for server in servers_to_test:
        try:
            print(f"\nTesting {server} server...")

            # Try to import and initialize the server
            if server == "pubmed":
                from servers.pubmed_server import mcp as pubmed_mcp
                print(f"  ✅ {server} server imported successfully")
                results[server] = True
            elif server == "clinicaltrials":
                from servers.clinicaltrials_server import mcp as ct_mcp
                print(f"  ✅ {server} server imported successfully")
                results[server] = True
            elif server == "fetch":
                from servers.fetch_server import mcp as fetch_mcp
                print(f"  ✅ {server} server imported successfully")
                results[server] = True
            elif server == "aact":
                from servers.aact_server import app as aact_app
                print(f"  ✅ {server} server imported successfully")
                # Check if PostgreSQL is available
                from servers.aact_server import POSTGRES_AVAILABLE
                if POSTGRES_AVAILABLE:
                    print(f"  ✅ PostgreSQL driver available for {server}")
                else:
                    print(f"  ❌ PostgreSQL driver not available for {server}")
                results[server] = POSTGRES_AVAILABLE

        except Exception as e:
            print(f"  ❌ {server} server failed: {e}")
            results[server] = False

    # Summary
    print("\n📊 MCP Server Status:")
    for server, status in results.items():
        status_emoji = "✅" if status else "❌"
        print(f"  {status_emoji} {server}")

    return all(results.values())


def main():
    """Run all tests"""
    print("\n🚀 Testing ALS Research Agent Configuration")
    print("=" * 80)

    # Load .env file
    env_path = ".env"
    if os.path.exists(env_path):
        print(f"✅ Found .env file at {env_path}")
        load_dotenv(env_path)
    else:
        print("⚠️  No .env file found, using defaults")

    # Run tests
    results = {
        "PubMed": test_pubmed_config(),
        "AACT Database": test_aact_config(),
    }

    # Test MCP servers
    mcp_ok = asyncio.run(test_mcp_servers())
    results["MCP Servers"] = mcp_ok

    # Final summary
    print("\n" + "=" * 80)
    print("📊 FINAL TEST SUMMARY")
    print("=" * 80)

    for component, status in results.items():
        status_emoji = "✅" if status else "❌"
        print(f"{status_emoji} {component}: {'PASSED' if status else 'FAILED'}")

    all_passed = all(results.values())

    if all_passed:
        print("\n🎉 All tests passed! Your configuration is working correctly.")
    else:
        print("\n⚠️  Some tests failed. Please check the output above for details.")

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())