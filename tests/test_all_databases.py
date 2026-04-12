#!/usr/bin/env python3
"""
Integration test for all database searches after fixes.
Tests PubMed, bioRxiv, and AACT both individually and in parallel.
"""

import asyncio
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from custom_mcp_client import MCPClientManager

async def test_all_databases():
    """Test all databases after fixes"""
    print("=" * 70)
    print("INTEGRATION TEST: ALL DATABASES")
    print("=" * 70)

    manager = MCPClientManager()
    servers_dir = Path(__file__).parent / "servers"

    # Start all servers
    servers = [
        ("pubmed", "pubmed_server.py"),
        ("biorxiv", "biorxiv_server.py"),
        ("aact", "aact_server.py")
    ]

    print("\n1. Starting all MCP servers...")
    print("-" * 40)
    for server_name, server_file in servers:
        server_path = servers_dir / server_file
        try:
            start = time.time()
            await manager.add_server(server_name, str(server_path))
            elapsed = time.time() - start
            print(f"✅ {server_name}: Started in {elapsed:.1f}s")
        except Exception as e:
            print(f"❌ {server_name}: Failed to start - {e}")

    # Test individual searches
    print("\n2. Testing individual database searches...")
    print("-" * 40)

    test_cases = [
        ("pubmed", "search_pubmed", {"query": "ALS therapy", "max_results": 5}),
        ("pubmed", "search_pubmed", {"query": "ALS SOD1 C9orf72", "max_results": 5}),
        ("biorxiv", "search_preprints", {"query": "ALS", "max_results": 5}),
        ("aact", "search_als_trials", {"condition": "ALS", "max_results": 5})
    ]

    for server, method, params in test_cases:
        print(f"\nTesting {server}.{method}...")
        start = time.time()
        try:
            result = await asyncio.wait_for(
                manager.call_tool(server, method, params),
                timeout=20  # 20 second timeout per search
            )
            elapsed = time.time() - start

            # Check for results
            if "No results" in result or "no results" in result:
                print(f"⚠️ {server}: No results (took {elapsed:.1f}s)")
            elif "Found" in result or "results" in result.lower():
                import re
                # Try to extract count
                count_match = re.search(r'(\d+)\s+(papers?|trials?|preprints?|results?)', result.lower())
                if count_match:
                    print(f"✅ {server}: Found {count_match.group(1)} results in {elapsed:.1f}s")
                else:
                    print(f"✅ {server}: Got results in {elapsed:.1f}s")
            else:
                print(f"? {server}: Unknown response format in {elapsed:.1f}s")

            # Flag slow searches
            if elapsed > 10:
                print(f"   ⚠️ WARNING: Search took {elapsed:.1f}s (>10s)")

        except asyncio.TimeoutError:
            elapsed = time.time() - start
            print(f"❌ {server}: TIMEOUT after {elapsed:.1f}s")
        except Exception as e:
            elapsed = time.time() - start
            print(f"❌ {server}: Error after {elapsed:.1f}s - {e}")

    # Test parallel execution
    print("\n3. Testing parallel searches (3 databases)...")
    print("-" * 40)

    parallel_tasks = [
        manager.call_tool("pubmed", "search_pubmed", {"query": "ALS gene therapy", "max_results": 5}),
        manager.call_tool("biorxiv", "search_preprints", {"query": "ALS TDP-43", "max_results": 5}),
        manager.call_tool("aact", "search_als_trials", {"condition": "ALS", "max_results": 5})
    ]

    print("Starting parallel searches...")
    start = time.time()
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*parallel_tasks, return_exceptions=True),
            timeout=30  # 30 second total timeout for parallel
        )
        elapsed = time.time() - start

        success_count = sum(1 for r in results if not isinstance(r, Exception) and "error" not in str(r).lower())
        print(f"\n✅ Parallel search completed in {elapsed:.1f}s")
        print(f"   {success_count}/3 searches succeeded")

        if elapsed > 20:
            print(f"   ⚠️ WARNING: Took {elapsed:.1f}s (expected <20s)")
        elif elapsed > 10:
            print(f"   ℹ️ Acceptable: {elapsed:.1f}s (10-20s range)")
        else:
            print(f"   🚀 Excellent: {elapsed:.1f}s (<10s)")

    except asyncio.TimeoutError:
        elapsed = time.time() - start
        print(f"❌ Parallel search TIMEOUT after {elapsed:.1f}s")

    # Cleanup
    await manager.close_all()

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print("""
    EXPECTED PERFORMANCE:
    - Individual searches: < 10 seconds each
    - Parallel searches: < 20 seconds total
    - bioRxiv: May be slower due to API pagination

    KEY FIXES APPLIED:
    1. ✅ Reduced PubMed timeout from 30s to 15s
    2. ✅ Fixed HTTP client timeout update bug
    3. ✅ bioRxiv limited to 1 page (100 results) for speed
    4. ✅ LlamaIndex uses lazy initialization (if enabled)

    If any searches are still slow or timing out, check:
    - Network connectivity
    - API rate limits
    - Query complexity (very long queries may fail)
    """)

if __name__ == "__main__":
    asyncio.run(test_all_databases())