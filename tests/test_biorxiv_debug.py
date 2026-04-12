#!/usr/bin/env python3
"""
Test bioRxiv with debug output to diagnose why few articles show up
"""

import asyncio
import sys
import logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from custom_mcp_client import MCPClientManager

# Enable debug logging for all modules
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


async def test_biorxiv_debug():
    """Test bioRxiv server with debug output"""

    print("=" * 70)
    print("TESTING BIORXIV WITH DEBUG OUTPUT")
    print("=" * 70)
    print("\nThis will show detailed debug logs to diagnose search issues.")
    print("-" * 70)

    # Create manager
    manager = MCPClientManager()

    # Add bioRxiv server
    servers_dir = Path(__file__).parent / "servers"
    biorxiv_path = servers_dir / "biorxiv_server.py"

    print(f"\n1. Starting bioRxiv server with DEBUG logging...")
    await manager.add_server("biorxiv", str(biorxiv_path))

    # Test queries that should definitely return results
    test_queries = [
        # Broad ALS queries that should return many results
        ("ALS", "Very broad query - should return many results"),
        ("amyotrophic lateral sclerosis", "Full disease name - should return many results"),

        # Specific ALS research topics
        ("ALS gene therapy", "Common research topic"),
        ("ALS TDP-43", "Major protein in ALS research"),
        ("ALS biomarkers", "Active research area"),

        # Very specific query that may return few/no results
        ("psilocybin ALS", "Very specific - may have limited results"),
    ]

    for query, description in test_queries:
        print("\n" + "=" * 70)
        print(f"QUERY: {query}")
        print(f"Expected: {description}")
        print("-" * 70)

        try:
            result = await manager.call_tool(
                "biorxiv",
                "search_preprints",
                {
                    "query": query,
                    "server": "both",
                    "max_results": 5,
                    "days_back": 365
                }
            )

            # Parse result
            if result:
                lines = result.split('\n')
                first_line = lines[0] if lines else ""

                import re
                count_match = re.search(r'Found (\d+) preprints', first_line)
                if count_match:
                    count = int(count_match.group(1))
                    if count > 0:
                        print(f"\n✅ SUCCESS: Found {count} preprints")
                    else:
                        print(f"\n⚠️ WARNING: No preprints found")
                else:
                    print(f"\n❓ Could not parse result count")
            else:
                print("\n❌ ERROR: Empty response")

        except Exception as e:
            print(f"\n❌ ERROR: {e}")

    # Close connection
    for client in manager.clients.values():
        await client.close()

    print("\n" + "=" * 70)
    print("ANALYSIS OF DEBUG OUTPUT")
    print("=" * 70)
    print("""
    Review the debug logs above to identify issues:

    1. 📝 Search terms: Are synonyms being added correctly?
       - Look for "Search terms: primary=... all=..."

    2. 📦 API fetching: How many papers are fetched from the API?
       - Look for "Fetched X papers from API"

    3. 🔍 Filtering: How many papers pass the filter?
       - Look for "Filtered results: X/Y papers matched"
       - Check rejected papers to see why they were filtered out

    4. 🎯 Final results: What gets returned?
       - Look for "FINAL RESULTS: Returning X preprints"

    Common issues:
    - Too restrictive filtering (papers rejected incorrectly)
    - API returning few papers (date range or server issue)
    - Search terms not matching paper content
    """)


if __name__ == "__main__":
    asyncio.run(test_biorxiv_debug())