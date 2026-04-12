#!/usr/bin/env python3
"""Test the custom MCP client"""

import asyncio
import logging
from pathlib import Path
from custom_mcp_client import MCPClientManager

logging.basicConfig(level=logging.INFO)


async def main():
    print("🧪 Testing Custom MCP Client\n")

    manager = MCPClientManager()

    # Add PubMed server
    print("📤 Starting PubMed server...")
    await manager.add_server(
        "pubmed",
        str(Path("servers/pubmed_server.py"))
    )

    # List tools
    print("\n📋 Listing tools...")
    all_tools = await manager.list_all_tools()
    for server, tools in all_tools.items():
        print(f"\n{server} server ({len(tools)} tools):")
        for tool in tools:
            print(f"  - {tool['name']}: {tool.get('description', 'No description')[:80]}...")

    # Test a tool call
    print("\n🔧 Testing tool call: search_pubmed...")
    result = await manager.call_tool(
        "pubmed",
        "search_pubmed",
        {"query": "ALS SOD1", "max_results": 2}
    )
    print(f"Result (first 500 chars):\n{result[:500]}...\n")

    # Close all
    print("🛑 Closing servers...")
    await manager.close_all()

    print("✅ Test complete!")


if __name__ == "__main__":
    asyncio.run(main())
