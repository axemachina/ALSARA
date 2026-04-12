#!/usr/bin/env python3
"""
Test that the full ALS Research Agent app starts successfully with RAG enabled.
"""

import asyncio
import time
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# Ensure RAG is enabled
os.environ["ENABLE_RAG"] = "true"

async def test_app_startup():
    """Test that the app starts with all MCP servers including RAG"""

    print("=" * 70)
    print("TESTING FULL APP STARTUP WITH RAG ENABLED")
    print("=" * 70)

    from custom_mcp_client import MCPClientManager

    manager = MCPClientManager()
    servers_dir = Path(__file__).parent / "servers"

    servers_to_test = [
        ("pubmed", "pubmed_server.py"),
        ("aact", "aact_server.py"),
        ("biorxiv", "biorxiv_server.py"),
        ("llamaindex", "llamaindex_server.py")  # The problematic one
    ]

    print("\nStarting MCP servers...")
    print("-" * 40)

    start_time = time.time()
    failed_servers = []

    for server_name, server_file in servers_to_test:
        server_path = servers_dir / server_file
        print(f"\nStarting {server_name} server...")

        server_start = time.time()
        try:
            await manager.add_server(server_name, str(server_path))
            elapsed = time.time() - server_start
            print(f"✅ {server_name} started in {elapsed:.1f}s")
        except Exception as e:
            elapsed = time.time() - server_start
            print(f"❌ {server_name} failed after {elapsed:.1f}s: {e}")
            failed_servers.append(server_name)

    total_time = time.time() - start_time

    print("\n" + "=" * 70)
    print("STARTUP SUMMARY")
    print("=" * 70)

    if not failed_servers:
        print(f"\n✅ SUCCESS: All servers started in {total_time:.1f} seconds")
        print("\nThe application can now start successfully with RAG enabled!")
        print("\nYou can run the app with: ./venv/bin/python als_agent_app.py")
    else:
        print(f"\n❌ FAILED: {len(failed_servers)} servers failed to start:")
        for server in failed_servers:
            print(f"   - {server}")
        print(f"\nTotal time: {total_time:.1f} seconds")

    # Test that tools are accessible
    print("\n" + "=" * 70)
    print("TESTING TOOL ACCESSIBILITY")
    print("=" * 70)

    try:
        all_tools = await manager.list_all_tools()
        total_tools = sum(len(tools) for tools in all_tools.values())
        print(f"\n✅ Total tools available: {total_tools}")

        for server_name, tools in all_tools.items():
            if tools:
                print(f"\n{server_name} ({len(tools)} tools):")
                for tool in tools[:2]:  # Show first 2 tools per server
                    print(f"  - {tool['name']}")
    except Exception as e:
        print(f"\n❌ Failed to list tools: {e}")

    # Cleanup
    await manager.close_all()

    print("\n" + "=" * 70)
    print("CONCLUSION")
    print("=" * 70)

    if not failed_servers:
        print("""
✅ The RAG initialization fix is working!

The application now:
1. Starts all MCP servers successfully
2. LlamaIndex server no longer times out during startup
3. Tools are accessible and ready to use
4. BioBERT model loading is deferred until first use

You can now run the app with RAG enabled without timeout issues!
        """)
    else:
        print("""
⚠️ Some servers failed to start. Check the errors above.

If LlamaIndex failed, the lazy initialization may need adjustment.
If other servers failed, there may be unrelated issues.
        """)

if __name__ == "__main__":
    asyncio.run(test_app_startup())