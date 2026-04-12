#!/usr/bin/env python3
"""
Test that LlamaIndex/RAG server initializes without timeout using lazy initialization.
"""

import asyncio
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from custom_mcp_client import MCPClient

async def test_lazy_init():
    """Test lazy initialization of LlamaIndex server"""

    print("=" * 70)
    print("TESTING LLAMAINDEX LAZY INITIALIZATION")
    print("=" * 70)

    # Test 1: Server startup should be fast (no model loading)
    print("\n1. Testing server startup speed...")
    print("-" * 40)

    servers_dir = Path(__file__).parent / "servers"
    llamaindex_path = servers_dir / "llamaindex_server.py"

    client = MCPClient(str(llamaindex_path), "llamaindex")

    start_time = time.time()
    try:
        await client.start()
        elapsed = time.time() - start_time
        print(f"✅ Server started in {elapsed:.1f} seconds")

        if elapsed < 5:
            print("   SUCCESS: Server started quickly (no model loading)")
        else:
            print(f"   WARNING: Server took {elapsed:.1f}s to start (expected <5s)")

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ Server startup failed after {elapsed:.1f}s: {e}")
        return

    # Test 2: List tools should work without initialization
    print("\n2. Testing tool listing (no initialization needed)...")
    print("-" * 40)

    start_time = time.time()
    try:
        tools = await client.list_tools()
        elapsed = time.time() - start_time
        print(f"✅ Listed {len(tools)} tools in {elapsed:.1f}s")
        for tool in tools[:3]:  # Show first 3 tools
            print(f"   - {tool['name']}: {tool.get('description', '')[:60]}...")
    except Exception as e:
        print(f"❌ Failed to list tools: {e}")

    # Test 3: First tool use should trigger initialization
    print("\n3. Testing first tool use (triggers lazy initialization)...")
    print("-" * 40)
    print("   This will load BioBERT model (20-30 seconds expected)...")

    start_time = time.time()
    try:
        # Try semantic search (will trigger initialization)
        result = await asyncio.wait_for(
            client.call_tool("semantic_search", {
                "query": "ALS TDP-43 aggregation",
                "max_results": 3
            }),
            timeout=65  # 65 second timeout (60s MCP + 5s buffer)
        )
        elapsed = time.time() - start_time

        # Parse result
        import json
        result_data = json.loads(result)

        if result_data.get("status") == "error" and "No research memory" in result_data.get("message", ""):
            print(f"✅ Tool executed in {elapsed:.1f}s (no papers indexed yet - expected)")
        elif result_data.get("status") == "no_results":
            print(f"✅ Tool executed in {elapsed:.1f}s (no results - expected)")
        else:
            print(f"✅ Tool executed successfully in {elapsed:.1f}s")

        if elapsed < 40:
            print("   SUCCESS: First use initialized in reasonable time")
        else:
            print(f"   WARNING: Initialization took {elapsed:.1f}s (expected <40s)")

    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        print(f"❌ Tool call timed out after {elapsed:.1f}s")
        print("   The lazy initialization may not be working correctly")
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ Tool call failed after {elapsed:.1f}s: {e}")

    # Test 4: Second tool use should be fast (already initialized)
    print("\n4. Testing second tool use (should be fast)...")
    print("-" * 40)

    start_time = time.time()
    try:
        result = await client.call_tool("list_indexed_papers", {
            "limit": 10
        })
        elapsed = time.time() - start_time
        print(f"✅ Second tool executed in {elapsed:.1f}s")

        if elapsed < 2:
            print("   SUCCESS: Second use was fast (already initialized)")
        else:
            print(f"   WARNING: Second use took {elapsed:.1f}s (expected <2s)")

    except Exception as e:
        print(f"❌ Second tool call failed: {e}")

    # Cleanup
    await client.close()

    print("\n" + "=" * 70)
    print("LAZY INITIALIZATION TEST SUMMARY")
    print("=" * 70)
    print("""
    Expected behavior:
    1. Server startup: <5 seconds (no model loading)
    2. Tool listing: <1 second (no initialization needed)
    3. First tool use: 20-40 seconds (triggers BioBERT loading)
    4. Second tool use: <2 seconds (already initialized)

    If all tests passed with expected times, the lazy initialization is working!
    """)

if __name__ == "__main__":
    asyncio.run(test_lazy_init())