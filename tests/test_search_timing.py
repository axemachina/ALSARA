#!/usr/bin/env python3
"""
Quick test to measure actual search times for different databases
"""

import asyncio
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from custom_mcp_client import MCPClientManager

async def test_search_timing():
    """Measure actual search times"""

    print("=" * 70)
    print("MEASURING ACTUAL SEARCH TIMES")
    print("=" * 70)

    # Create manager
    manager = MCPClientManager()

    # Test each server individually
    servers = [
        ("pubmed", "pubmed_server.py", "search_papers", {"query": "ALS therapy", "max_results": 5}),
        ("biorxiv", "biorxiv_server.py", "search_preprints", {"query": "ALS therapy", "max_results": 5, "days_back": 180}),
        ("aact", "aact_server.py", "search_aact_trials", {"condition": "ALS", "max_results": 5})
    ]

    results = {}

    for server_name, server_file, method, params in servers:
        print(f"\nTesting {server_name}...")
        servers_dir = Path(__file__).parent / "servers"
        server_path = servers_dir / server_file

        try:
            # Start server
            await manager.add_server(server_name, str(server_path))

            # Time the search
            start = time.time()
            try:
                result = await asyncio.wait_for(
                    manager.call_tool(server_name, method, params),
                    timeout=45  # 45 second timeout
                )
                elapsed = time.time() - start
                results[server_name] = elapsed
                print(f"✅ {server_name}: {elapsed:.1f} seconds")
            except asyncio.TimeoutError:
                elapsed = time.time() - start
                results[server_name] = "timeout"
                print(f"❌ {server_name}: TIMEOUT after {elapsed:.1f} seconds")

        except Exception as e:
            print(f"❌ {server_name}: Error - {e}")
            results[server_name] = "error"

    # Test parallel execution
    print("\n" + "=" * 70)
    print("TESTING PARALLEL EXECUTION (3 databases)")
    print("-" * 70)

    # Clean up previous servers
    for client in manager.clients.values():
        await client.close()
    manager.clients.clear()

    # Start all servers
    for server_name, server_file, _, _ in servers:
        servers_dir = Path(__file__).parent / "servers"
        server_path = servers_dir / server_file
        await manager.add_server(server_name, str(server_path))

    # Run searches in parallel
    start = time.time()
    tasks = []
    for server_name, _, method, params in servers:
        tasks.append(manager.call_tool(server_name, method, params))

    try:
        results_parallel = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=60
        )
        elapsed = time.time() - start
        print(f"✅ Parallel search completed in {elapsed:.1f} seconds")
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        print(f"❌ Parallel search TIMEOUT after {elapsed:.1f} seconds")

    # Cleanup
    for client in manager.clients.values():
        await client.close()

    print("\n" + "=" * 70)
    print("TIMING SUMMARY")
    print("=" * 70)
    print("\nIndividual server times:")
    for server, timing in results.items():
        if isinstance(timing, float):
            print(f"  {server}: {timing:.1f}s")
        else:
            print(f"  {server}: {timing}")

    print("\nRecommended timing estimates for UI:")
    print("  1 database: 15-20 seconds")
    print("  2 databases: 20-30 seconds")
    print("  3+ databases: 30-45 seconds")
    print("\nNote: bioRxiv tends to be slowest due to API pagination")

if __name__ == "__main__":
    asyncio.run(test_search_timing())