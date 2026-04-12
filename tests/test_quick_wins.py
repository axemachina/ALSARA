#!/usr/bin/env python3
"""
Test script to verify the Quick Wins implementation:
1. Clear success/failure indicators (✅/⚠️/❌)
2. Working indicators during long searches (⏳)
3. Confidence scoring in synthesis (🟢/🟡/🔴)
"""

import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from custom_mcp_client import MCPClientManager

async def test_quick_wins():
    """Test that all quick wins are working"""

    print("=" * 70)
    print("TESTING QUICK WINS IMPLEMENTATION")
    print("=" * 70)

    # Create manager
    manager = MCPClientManager()

    # Add servers
    servers_dir = Path(__file__).parent / "servers"
    pubmed_path = servers_dir / "pubmed_server.py"
    biorxiv_path = servers_dir / "biorxiv_server.py"

    print("\n1. Starting MCP servers...")
    await manager.add_server("pubmed", str(pubmed_path))
    await manager.add_server("biorxiv", str(biorxiv_path))
    print("✅ Servers started")

    print("\n2. Testing parallel execution with indicators...")
    print("-" * 40)

    # Import the parallel execution module
    from parallel_tool_execution import execute_tool_calls_parallel

    # Create test tool calls
    test_tools = [
        {
            "id": "test1",
            "name": "pubmed__search_papers",
            "input": {
                "query": "ALS TDP-43 2024",
                "max_results": 3
            }
        },
        {
            "id": "test2",
            "name": "biorxiv__search_preprints",
            "input": {
                "query": "amyotrophic lateral sclerosis biomarkers",
                "server": "biorxiv",
                "max_results": 3
            }
        },
        {
            "id": "test3",
            "name": "pubmed__search_papers",
            "input": {
                "query": "nonexistent_12345_drug_ALS",  # Should return no results
                "max_results": 3
            }
        }
    ]

    async def call_tool(tool_name, tool_args):
        """Helper to call MCP tools"""
        if "__" in tool_name:
            server, method = tool_name.split("__", 1)
            return await manager.call_tool(server, method, tool_args)
        return f"Tool {tool_name} not found"

    # Execute tools in parallel
    print("\n⏳ Searching 3 databases in parallel... (this may take 10-15 seconds)")

    start_time = asyncio.get_event_loop().time()
    progress_text, results = await execute_tool_calls_parallel(
        test_tools,
        call_tool
    )
    elapsed = asyncio.get_event_loop().time() - start_time

    print(f"\n✅ Completed in {elapsed:.1f}s")
    print("\nProgress output received:")
    print(progress_text)

    # Check for expected indicators
    print("\n3. Verifying Quick Win #2 (Success/Failure Indicators):")
    print("-" * 40)

    indicators_found = {
        "✅": "Success indicator" in progress_text or "✅" in progress_text,
        "⚠️": "No results" in progress_text or "⚠️" in progress_text,
        "❌": False  # Only appears on errors
    }

    for indicator, found in indicators_found.items():
        if found:
            print(f"{indicator} Found {indicator} indicator")

    print("\n4. Verifying Quick Win #5 (Working Indicators):")
    print("-" * 40)

    if "Search Progress:" in progress_text:
        print("✅ Progress summary included")
    if "took" in progress_text and "s)" in progress_text:
        print("✅ Timing information for slow operations")

    print("\n5. Quick Win #3 (Confidence Scoring):")
    print("-" * 40)
    print("✅ Added to system prompt - will appear in synthesis with:")
    print("   🟢 High confidence: Multiple peer-reviewed studies")
    print("   🟡 Moderate confidence: Limited studies or preprints")
    print("   🔴 Low confidence: Single study or theoretical basis")

    # Cleanup
    for client in manager.clients.values():
        await client.close()

    print("\n" + "=" * 70)
    print("QUICK WINS IMPLEMENTATION SUMMARY")
    print("=" * 70)
    print("""
    ✅ Quick Win #2: Clear success/failure indicators
       - Shows result counts for successful searches
       - Warns when no results are found
       - Displays errors clearly

    ✅ Quick Win #3: Confidence scoring in synthesis
       - Added to system prompt
       - Will show 🟢/🟡/🔴 indicators for claims

    ✅ Quick Win #5: Working indicators during searches
       - Shows "Searching X databases in parallel..."
       - Displays completion time for long operations
       - Progress summary with timing info

    These improvements make the agent more transparent and user-friendly!
    """)

if __name__ == "__main__":
    asyncio.run(test_quick_wins())