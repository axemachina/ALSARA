#!/usr/bin/env python3
"""Minimal test to isolate MCP server connection issue"""

import asyncio
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_connection():
    """Test basic MCP server connection"""
    print("🧪 Testing MCP server connection...")

    # Test with converted PubMed server
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path("servers/pubmed_server.py"))],
        env=None  # Inherit environment
    )

    print(f"Command: {server_params.command}")
    print(f"Args: {server_params.args}")

    # First, let's test if the server can even import properly
    print("\n📋 Testing server imports...")
    import subprocess
    result = subprocess.run(
        [sys.executable, "-c", "import sys; sys.path.insert(0, '.'); from servers import pubmed_server; print('✅ Server imports successfully')"],
        capture_output=True,
        text=True
    )
    print(f"Import test stdout: {result.stdout}")
    if result.stderr:
        print(f"Import test stderr: {result.stderr}")
    if result.returncode != 0:
        print(f"❌ Server import failed with code {result.returncode}")
        return
    print("Attempting to connect...")

    # Add more detailed logging
    import logging
    logging.basicConfig(level=logging.DEBUG)

    try:
        # Try with timeout
        async with asyncio.timeout(10):
            print("Creating stdio_client...")
            async with stdio_client(server_params) as (read, write):
                print("✅ Context manager entered successfully!")
                print(f"Read stream: {read}")
                print(f"Write stream: {write}")

                session = ClientSession(read, write)
                print("Initializing session...")

                # Try to initialize with more debugging
                init_result = await session.initialize()
                print(f"✅ Session initialized! Result: {init_result}")

                # List tools
                print("Listing tools...")
                tools = await session.list_tools()
                print(f"✅ Found {len(tools.tools)} tools")
                for tool in tools.tools:
                    print(f"  - {tool.name}")

    except asyncio.TimeoutError:
        print("❌ Connection timed out after 5 seconds")
        print("This suggests the server is not responding to the handshake")
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_connection())
