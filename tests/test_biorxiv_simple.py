#!/usr/bin/env python3
"""
Simple test to check if bioRxiv is returning results
"""

import asyncio
import subprocess
import json
import sys

async def test_biorxiv():
    """Test bioRxiv server directly"""

    print("=" * 70)
    print("TESTING BIORXIV SEARCH")
    print("=" * 70)

    # Start the bioRxiv server
    process = subprocess.Popen(
        ["./venv/bin/python", "servers/biorxiv_server.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    try:
        # Initialize
        init_msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"capabilities": {}}
        }

        process.stdin.write(json.dumps(init_msg) + "\n")
        process.stdin.flush()

        # Read initialization response
        response = process.stdout.readline()
        print(f"Init response: {response[:100]}...")

        # Test searches
        test_queries = [
            "ALS gene therapy",
            "ALS SOD1",
            "ALS biomarkers",
            "psilocybin ALS"
        ]

        for i, query in enumerate(test_queries, start=2):
            print(f"\n{'='*50}")
            print(f"Testing: {query}")
            print('-'*50)

            # Call search_preprints
            search_msg = {
                "jsonrpc": "2.0",
                "id": i,
                "method": "tools/call",
                "params": {
                    "name": "search_preprints",
                    "arguments": {
                        "query": query,
                        "server": "both",
                        "max_results": 3,
                        "days_back": 365
                    }
                }
            }

            process.stdin.write(json.dumps(search_msg) + "\n")
            process.stdin.flush()

            # Read response
            response = process.stdout.readline()
            if response:
                try:
                    result = json.loads(response)
                    if "result" in result:
                        content = result["result"].get("content", [])
                        if content and isinstance(content, list):
                            text = content[0].get("text", "") if content else ""
                            # Count results
                            import re
                            dois = re.findall(r'10\.1101/[\d.]+', text)
                            print(f"✅ Found {len(dois)} preprints")
                            if dois:
                                print(f"   Sample DOIs: {', '.join(dois[:2])}")
                            if len(dois) == 0:
                                print(f"⚠️ No results for '{query}'")
                                # Show part of response for debugging
                                print(f"   Response snippet: {text[:200]}...")
                    elif "error" in result:
                        print(f"❌ Error: {result['error']}")
                except json.JSONDecodeError:
                    print(f"❌ Invalid JSON response: {response[:100]}...")
            else:
                print("❌ No response received")

    finally:
        # Cleanup
        process.terminate()
        process.wait(timeout=1)

    print("\n" + "=" * 70)
    print("ANALYSIS")
    print("=" * 70)
    print("""
    If queries are returning 0 results, possible issues:
    1. Search terms are too specific
    2. Time range is too restrictive
    3. bioRxiv/medRxiv may not have preprints for niche topics
    4. Filtering logic may be too strict

    The bioRxiv server seems to be working, but may need tuning for better coverage.
    """)

if __name__ == "__main__":
    asyncio.run(test_biorxiv())