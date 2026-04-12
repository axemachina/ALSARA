#!/usr/bin/env python3
"""
Test PubMed server to diagnose timeout/performance issues.
"""

import asyncio
import time
import sys
import httpx
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from custom_mcp_client import MCPClient

async def test_pubmed_direct():
    """Test PubMed API directly"""
    print("=" * 70)
    print("TESTING PUBMED API DIRECTLY")
    print("=" * 70)

    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    # Test 1: Simple search
    print("\n1. Testing simple search (should be fast)...")
    client = httpx.AsyncClient(timeout=10.0)

    start = time.time()
    try:
        # Search for PMIDs
        search_params = {
            "db": "pubmed",
            "term": "ALS therapy",
            "retmax": 5,
            "retmode": "json",
            "sort": "relevance"
        }

        response = await client.get(f"{base_url}/esearch.fcgi", params=search_params)
        response.raise_for_status()
        data = response.json()

        pmids = data.get("esearchresult", {}).get("idlist", [])
        elapsed = time.time() - start

        print(f"✅ Search completed in {elapsed:.2f}s, found {len(pmids)} PMIDs")

    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ Direct API failed after {elapsed:.2f}s: {e}")

    await client.aclose()

    # Test 2: Fetch details (the slow part?)
    print("\n2. Testing fetch details...")

    if pmids:
        client = httpx.AsyncClient(timeout=30.0)
        start = time.time()

        try:
            fetch_params = {
                "db": "pubmed",
                "id": ",".join(pmids[:3]),  # Only fetch 3
                "retmode": "xml"
            }

            response = await client.get(f"{base_url}/efetch.fcgi", params=fetch_params)
            response.raise_for_status()
            elapsed = time.time() - start

            print(f"✅ Fetch completed in {elapsed:.2f}s, response size: {len(response.text)} bytes")

        except Exception as e:
            elapsed = time.time() - start
            print(f"❌ Fetch failed after {elapsed:.2f}s: {e}")

        await client.aclose()


async def test_pubmed_via_mcp():
    """Test PubMed through MCP client"""
    print("\n" + "=" * 70)
    print("TESTING PUBMED VIA MCP CLIENT")
    print("=" * 70)

    servers_dir = Path(__file__).parent / "servers"
    pubmed_path = servers_dir / "pubmed_server.py"

    client = MCPClient(str(pubmed_path), "pubmed")

    # Start server
    print("\n1. Starting PubMed MCP server...")
    start = time.time()

    try:
        await client.start()
        elapsed = time.time() - start
        print(f"✅ Server started in {elapsed:.2f}s")
    except Exception as e:
        print(f"❌ Server failed to start: {e}")
        return

    # Test small search
    print("\n2. Testing small search (5 results)...")
    start = time.time()

    try:
        result = await asyncio.wait_for(
            client.call_tool("search_pubmed", {
                "query": "ALS therapy",
                "max_results": 5
            }),
            timeout=60
        )
        elapsed = time.time() - start

        # Count results
        import re
        papers = re.findall(r'\d+\.\s\*\*', result)
        print(f"✅ Search completed in {elapsed:.2f}s, found {len(papers)} papers")

        if elapsed > 30:
            print(f"⚠️ WARNING: Search took {elapsed:.2f}s (>30s timeout)")

    except asyncio.TimeoutError:
        elapsed = time.time() - start
        print(f"❌ Search timed out after {elapsed:.2f}s")
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ Search failed after {elapsed:.2f}s: {e}")

    # Test larger search
    print("\n3. Testing larger search (10 results)...")
    start = time.time()

    try:
        result = await asyncio.wait_for(
            client.call_tool("search_pubmed", {
                "query": "ALS genetic testing SOD1 C9orf72",
                "max_results": 10
            }),
            timeout=60
        )
        elapsed = time.time() - start

        papers = re.findall(r'\d+\.\s\*\*', result)
        print(f"✅ Search completed in {elapsed:.2f}s, found {len(papers)} papers")

        if elapsed > 30:
            print(f"⚠️ WARNING: Search took {elapsed:.2f}s (>30s timeout)")

    except asyncio.TimeoutError:
        elapsed = time.time() - start
        print(f"❌ Search timed out after {elapsed:.2f}s")
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ Search failed after {elapsed:.2f}s: {e}")

    await client.close()


async def test_pubmed_parallel():
    """Test multiple parallel PubMed searches"""
    print("\n" + "=" * 70)
    print("TESTING PARALLEL PUBMED SEARCHES")
    print("=" * 70)

    from custom_mcp_client import MCPClientManager

    manager = MCPClientManager()
    servers_dir = Path(__file__).parent / "servers"
    pubmed_path = servers_dir / "pubmed_server.py"

    # Start server
    await manager.add_server("pubmed", str(pubmed_path))

    print("\nRunning 3 parallel searches...")
    start = time.time()

    tasks = [
        manager.call_tool("pubmed", "search_pubmed", {
            "query": "ALS therapy", "max_results": 5
        }),
        manager.call_tool("pubmed", "search_pubmed", {
            "query": "ALS SOD1", "max_results": 5
        }),
        manager.call_tool("pubmed", "search_pubmed", {
            "query": "ALS C9orf72", "max_results": 5
        })
    ]

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=90
        )
        elapsed = time.time() - start

        success_count = sum(1 for r in results if not isinstance(r, Exception))
        print(f"\n✅ Completed in {elapsed:.2f}s")
        print(f"   {success_count}/3 searches succeeded")

        if elapsed > 60:
            print(f"⚠️ WARNING: Parallel searches took {elapsed:.2f}s")

    except asyncio.TimeoutError:
        elapsed = time.time() - start
        print(f"❌ Parallel searches timed out after {elapsed:.2f}s")

    await manager.close_all()


async def main():
    """Run all tests"""
    # Test direct API first
    await test_pubmed_direct()

    # Test via MCP
    await test_pubmed_via_mcp()

    # Test parallel
    await test_pubmed_parallel()

    print("\n" + "=" * 70)
    print("DIAGNOSIS SUMMARY")
    print("=" * 70)
    print("""
    Expected behavior:
    - Direct API: < 2 seconds for small searches
    - MCP single search: < 5 seconds for 5 results
    - MCP parallel: < 10 seconds for 3 parallel searches

    If times are much longer, check:
    1. Network connectivity to PubMed
    2. HTTP client timeout settings
    3. XML parsing performance
    4. Rate limiting delays
    """)

if __name__ == "__main__":
    asyncio.run(main())