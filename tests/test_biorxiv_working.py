#!/usr/bin/env python3
"""
Test if bioRxiv is working with the current setup
"""

import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from custom_mcp_client import MCPClientManager
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_biorxiv():
    """Test bioRxiv server directly using MCPClientManager"""

    print("=" * 70)
    print("TESTING BIORXIV SERVER")
    print("=" * 70)

    # Create manager
    manager = MCPClientManager()

    # Add bioRxiv server
    servers_dir = Path(__file__).parent / "servers"
    biorxiv_path = servers_dir / "biorxiv_server.py"

    print(f"\n1. Starting bioRxiv server from: {biorxiv_path}")

    try:
        await manager.add_server("biorxiv", str(biorxiv_path))
        print("✅ Server started successfully")
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        return

    # List available tools
    print("\n2. Checking available tools...")
    try:
        all_tools = await manager.list_all_tools()
        if "biorxiv" in all_tools:
            print(f"✅ Found {len(all_tools['biorxiv'])} tools:")
            for tool in all_tools['biorxiv']:
                print(f"   - {tool['name']}")
    except Exception as e:
        print(f"❌ Failed to list tools: {e}")

    # Test searches
    test_queries = [
        "ALS gene therapy",
        "ALS TDP-43",
        "ALS biomarkers 2024",
        "amyotrophic lateral sclerosis stem cell"
    ]

    print("\n3. Testing searches...")
    print("-" * 40)

    for query in test_queries:
        print(f"\nSearching: {query}")

        try:
            result = await manager.call_tool(
                "biorxiv",
                "search_preprints",
                {
                    "query": query,
                    "server": "both",
                    "max_results": 3,
                    "days_back": 365
                }
            )

            if result:
                # Count preprints
                import re
                dois = re.findall(r'10\.1101/[\d.]+', result)
                print(f"✅ Found {len(dois)} preprints")

                if len(dois) > 0:
                    print(f"   DOIs: {', '.join(dois[:2])}...")
                    # Show first title
                    title_match = re.search(r'Title: (.+?)(?:\n|$)', result)
                    if title_match:
                        print(f"   First title: {title_match.group(1)[:60]}...")
                else:
                    print("⚠️ No preprints found for this query")
                    # Show response snippet
                    print(f"   Response: {result[:150]}...")
            else:
                print("❌ Empty response")

        except Exception as e:
            print(f"❌ Error: {e}")

    # Close connection
    for client in manager.clients.values():
        await client.close()

    print("\n" + "=" * 70)
    print("ANALYSIS")
    print("=" * 70)
    print("""
    If searches are working and returning results:
    ✅ bioRxiv server is functioning correctly

    If searches return no results:
    - Query might be too specific
    - Papers might be outside the time window (365 days)
    - The preprint servers might not have papers on that topic

    If errors occur:
    - Check server logs for details
    - Verify dependencies are installed
    """)


if __name__ == "__main__":
    asyncio.run(test_biorxiv())