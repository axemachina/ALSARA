#!/usr/bin/env python3
"""
Test script to check if MCP servers are running correctly
"""

import asyncio
import subprocess
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from custom_mcp_client import MCPClientManager

async def test_individual_servers():
    """Test each MCP server individually"""
    servers = [
        ("pubmed", "./venv/bin/python servers/pubmed_server.py"),
        ("biorxiv", "./venv/bin/python servers/biorxiv_server.py"),
        ("clinicaltrials", "./venv/bin/python servers/clinicaltrials_server.py")
    ]

    print("="*60)
    print("Testing Individual MCP Servers")
    print("="*60)

    for name, command in servers:
        print(f"\n### Testing {name} server")
        print(f"Command: {command}")

        try:
            # Try to run the server and see if it starts
            process = subprocess.Popen(
                command.split(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Give it a moment to start
            await asyncio.sleep(0.5)

            # Check if process is still running
            if process.poll() is None:
                print(f"✅ {name} server started successfully")
                # Send a simple test message
                process.stdin.write('{"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1}\n')
                process.stdin.flush()

                # Try to read response
                try:
                    response = await asyncio.wait_for(
                        asyncio.create_task(asyncio.get_event_loop().run_in_executor(None, process.stdout.readline)),
                        timeout=2.0
                    )
                    if response:
                        print(f"✅ {name} server responding to commands")
                    else:
                        print(f"⚠️ {name} server not responding")
                except asyncio.TimeoutError:
                    print(f"⚠️ {name} server timeout on response")

                # Terminate the process
                process.terminate()
                await asyncio.sleep(0.1)
                if process.poll() is None:
                    process.kill()

            else:
                # Process exited immediately
                stderr = process.stderr.read()
                print(f"❌ {name} server failed to start")
                if stderr:
                    print(f"   Error: {stderr[:200]}")

        except Exception as e:
            print(f"❌ Error testing {name} server: {e}")


async def test_mcp_manager():
    """Test the MCP manager with all servers"""
    print("\n" + "="*60)
    print("Testing MCP Manager")
    print("="*60)

    try:
        manager = MCPClientManager()
        print("Initializing MCP servers...")
        await manager.initialize()

        print("\nListing tools from all servers...")
        tools = await manager.list_all_tools()

        print(f"\n✅ Successfully connected to all servers")
        print(f"   Total tools available: {len(tools)}")

        # Group tools by server
        by_server = {}
        for tool in tools:
            server = tool.get('server', 'unknown')
            if server not in by_server:
                by_server[server] = []
            by_server[server].append(tool['name'])

        for server, tool_names in by_server.items():
            print(f"\n   {server} server:")
            for name in tool_names[:3]:  # Show first 3 tools
                print(f"     - {name}")
            if len(tool_names) > 3:
                print(f"     ... and {len(tool_names) - 3} more")

        # Cleanup
        await manager.cleanup()
        print("\n✅ Cleanup completed successfully")

    except Exception as e:
        print(f"\n❌ Error in MCP Manager: {e}")
        import traceback
        traceback.print_exc()


async def test_specific_query():
    """Test with the specific query that caused the error"""
    print("\n" + "="*60)
    print("Testing Specific Query")
    print("="*60)

    try:
        manager = MCPClientManager()
        await manager.initialize()

        # Try to call a tool from each server
        test_calls = [
            {
                "server": "pubmed",
                "tool": "search_papers",
                "args": {"query": "combination therapy ALS", "max_results": 1}
            },
            {
                "server": "biorxiv",
                "tool": "search_preprints",
                "args": {"query": "combination therapy", "max_results": 1}
            },
            {
                "server": "clinicaltrials",
                "tool": "search_trials",
                "args": {"condition": "ALS", "status": "recruiting", "max_results": 1}
            }
        ]

        for test in test_calls:
            print(f"\nTesting {test['server']}.{test['tool']}...")
            try:
                result = await manager.call_tool(
                    test['server'],
                    test['tool'],
                    test['args']
                )
                if result and len(str(result)) > 0:
                    print(f"✅ {test['server']} server working")
                else:
                    print(f"⚠️ {test['server']} server returned empty result")
            except Exception as e:
                print(f"❌ {test['server']} server error: {e}")

        await manager.cleanup()

    except Exception as e:
        print(f"\n❌ Error in specific query test: {e}")


async def main():
    """Run all tests"""
    print("="*60)
    print("MCP Server Diagnostic Tool")
    print("="*60)

    # Test 1: Individual servers
    await test_individual_servers()

    # Test 2: MCP Manager
    await test_mcp_manager()

    # Test 3: Specific query
    await test_specific_query()

    print("\n" + "="*60)
    print("Diagnostic Complete")
    print("="*60)
    print("""
If servers are failing to start:
1. Check that all dependencies are installed: pip install -r requirements.txt
2. Check that the virtual environment is activated
3. Check for any import errors in server files
4. Try running servers individually to see error messages
5. Check that ports are not already in use

If servers start but then close:
1. Check for unhandled exceptions in server code
2. Check memory/resource limits
3. Try increasing timeout values
4. Check for circular imports or dependency issues
    """)


if __name__ == "__main__":
    asyncio.run(main())