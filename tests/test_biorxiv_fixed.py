#!/usr/bin/env python3
"""
Test if bioRxiv timeout is fixed
"""

import asyncio
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from custom_mcp_client import MCPClientManager

async def test_biorxiv_fixed():
    """Test bioRxiv with fixes applied"""

    print("=" * 70)
    print("TESTING BIORXIV WITH FIXES")
    print("=" * 70)
    print("\nChanges made:")
    print("1. Reduced max_iterations from 3 to 1 (only first 100 papers)")
    print("2. HTTP timeout at 15s (was 60s)")
    print("3. MCP client timeout at 30s (was 20s)")
    print("-" * 70)

    # Create manager
    manager = MCPClientManager()

    # Add bioRxiv server
    servers_dir = Path(__file__).parent / "servers"
    biorxiv_path = servers_dir / "biorxiv_server.py"

    print(f"\nStarting bioRxiv server...")
    await manager.add_server("biorxiv", str(biorxiv_path))

    # Test a simple query
    print("\nTesting search for 'ALS therapy'...")
    start = time.time()

    try:
        result = await asyncio.wait_for(
            manager.call_tool(
                "biorxiv",
                "search_preprints",
                {
                    "query": "ALS therapy",
                    "server": "biorxiv",
                    "max_results": 5,
                    "days_back": 90
                }
            ),
            timeout=35  # Give it 35 seconds max
        )
        elapsed = time.time() - start

        # Check results
        if result:
            import re
            count_match = re.search(r'Found (\d+)', result)
            if count_match:
                count = int(count_match.group(1))
                print(f"\n✅ SUCCESS! Found {count} preprints in {elapsed:.1f} seconds")
            else:
                print(f"\n✅ Response received in {elapsed:.1f} seconds")
                print(f"Response preview: {result[:200]}...")
        else:
            print(f"\n⚠️ Empty response after {elapsed:.1f} seconds")

    except asyncio.TimeoutError:
        elapsed = time.time() - start
        print(f"\n❌ TIMEOUT after {elapsed:.1f} seconds - still not fixed")
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n❌ ERROR after {elapsed:.1f} seconds: {e}")

    # Cleanup
    for client in manager.clients.values():
        await client.close()

    print("\n" + "=" * 70)
    if elapsed < 10:
        print("✅ FIXED! bioRxiv now responds quickly")
    elif elapsed < 30:
        print("⚠️ PARTIAL FIX - slower but working")
    else:
        print("❌ STILL BROKEN - needs more investigation")

if __name__ == "__main__":
    asyncio.run(test_biorxiv_fixed())