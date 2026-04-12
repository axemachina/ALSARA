#!/usr/bin/env python3
"""
Test bioRxiv server directly without MCP client layer
"""

import subprocess
import json
import asyncio

async def test_direct():
    """Test bioRxiv server directly via subprocess"""

    print("Testing bioRxiv server directly...")

    # Start the server as a subprocess
    process = subprocess.Popen(
        ["./venv/bin/python", "servers/biorxiv_server.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    try:
        # Send initialization
        init_msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"capabilities": {}}
        }

        print("1. Sending initialize...")
        process.stdin.write(json.dumps(init_msg) + "\n")
        process.stdin.flush()

        # Read response
        response = process.stdout.readline()
        print(f"   Response: {response[:100]}...")

        # Send search request
        search_msg = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "search_preprints",
                "arguments": {
                    "query": "ALS",
                    "max_results": 5,
                    "days_back": 30
                }
            }
        }

        print("\n2. Sending search for 'ALS'...")
        process.stdin.write(json.dumps(search_msg) + "\n")
        process.stdin.flush()

        # Read response with timeout
        import time
        start = time.time()

        # Try to read response
        import select
        ready = select.select([process.stdout], [], [], 10.0)  # 10 second timeout

        if ready[0]:
            response = process.stdout.readline()
            elapsed = time.time() - start
            print(f"   Response received in {elapsed:.2f}s")

            # Parse response
            data = json.loads(response)
            if "result" in data:
                content = data["result"].get("content", [])
                text = content[0].get("text", "") if isinstance(content, list) else str(content)
                # Count papers
                import re
                count_match = re.search(r'Found (\d+)', text)
                if count_match:
                    print(f"   ✅ Found {count_match.group(1)} preprints")
                else:
                    print(f"   Response preview: {text[:200]}...")
            elif "error" in data:
                print(f"   ❌ Error: {data['error']}")
        else:
            elapsed = time.time() - start
            print(f"   ❌ No response after {elapsed:.2f}s - server may be hanging")

            # Check if process is still alive
            if process.poll() is None:
                print("   Process is still running (not crashed)")
            else:
                print(f"   Process exited with code: {process.poll()}")

            # Try to read stderr
            stderr_output = process.stderr.read()
            if stderr_output:
                print(f"   Stderr: {stderr_output[:500]}")

    finally:
        process.terminate()
        process.wait(timeout=1)

    print("\nConclusion: If this hangs, the issue is in biorxiv_server.py itself")
    print("If it works, the issue is in MCPClientManager communication")

if __name__ == "__main__":
    asyncio.run(test_direct())