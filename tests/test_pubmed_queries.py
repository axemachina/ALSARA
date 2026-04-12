#!/usr/bin/env python3
"""
Test various PubMed query patterns to identify which are failing.
"""

import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from custom_mcp_client import MCPClient

async def test_queries():
    """Test different PubMed query patterns"""
    print("=" * 70)
    print("TESTING PUBMED QUERY PATTERNS")
    print("=" * 70)

    # Test queries that should work
    test_queries = [
        # Simple queries
        ("ALS", 10, "Basic term"),
        ("ALS therapy", 10, "Two terms"),
        ("amyotrophic lateral sclerosis", 10, "Full disease name"),

        # Complex queries (the problematic ones from the app)
        ("ALS genetic testing gene therapy eligibility", 10, "Complex multi-term"),
        ("ALS genetic testing SOD1 C9orf72 FUS TARDBP", 10, "Multiple gene names"),
        ("amyotrophic lateral sclerosis gene therapy clinical", 10, "Complex clinical"),

        # Boolean operators (might be the issue)
        ("ALS AND SOD1", 10, "AND operator"),
        ("ALS OR motor neuron disease", 10, "OR operator"),
        ("(ALS OR amyotrophic lateral sclerosis) AND therapy", 10, "Parentheses"),

        # Very long queries
        ("ALS genetic testing gene therapy eligibility SOD1 C9orf72 FUS TARDBP screening diagnosis treatment antisense oligonucleotide", 10, "Very long query"),
    ]

    servers_dir = Path(__file__).parent / "servers"
    pubmed_path = servers_dir / "pubmed_server.py"

    client = MCPClient(str(pubmed_path), "pubmed")
    await client.start()

    results_summary = []

    for query, max_results, description in test_queries:
        print(f"\nTesting: {description}")
        print(f"Query: '{query}'")
        print("-" * 40)

        try:
            result = await asyncio.wait_for(
                client.call_tool("search_pubmed", {
                    "query": query,
                    "max_results": max_results
                }),
                timeout=30
            )

            # Check if we got results
            if "No results found" in result:
                print(f"❌ NO RESULTS")
                results_summary.append((description, "NO RESULTS", query))
            elif "Found" in result:
                import re
                match = re.search(r'Found (\d+) papers', result)
                if match:
                    count = match.group(1)
                    print(f"✅ Found {count} papers")
                    results_summary.append((description, f"{count} papers", query))
                else:
                    print(f"✅ Got results (count unknown)")
                    results_summary.append((description, "RESULTS", query))
            else:
                print(f"⚠️ Unexpected response format")
                results_summary.append((description, "UNKNOWN", query))

        except asyncio.TimeoutError:
            print(f"❌ TIMEOUT after 30s")
            results_summary.append((description, "TIMEOUT", query))
        except Exception as e:
            print(f"❌ ERROR: {e}")
            results_summary.append((description, f"ERROR: {str(e)[:30]}", query))

    await client.close()

    # Print summary
    print("\n" + "=" * 70)
    print("QUERY RESULTS SUMMARY")
    print("=" * 70)
    print(f"{'Description':<30} {'Result':<15} Query")
    print("-" * 70)
    for desc, result, query in results_summary:
        print(f"{desc:<30} {result:<15} {query[:40]}...")

    # Identify patterns
    print("\n" + "=" * 70)
    print("ANALYSIS")
    print("=" * 70)

    no_results = [q for q in results_summary if "NO RESULTS" in q[1]]
    timeouts = [q for q in results_summary if "TIMEOUT" in q[1]]

    if no_results:
        print(f"\n❌ Queries returning NO RESULTS ({len(no_results)}):")
        for desc, _, query in no_results:
            print(f"   - {desc}: '{query[:60]}...'")
        print("\n   ISSUE: Complex multi-term queries may need reformatting")
        print("   SOLUTION: Break into simpler queries or use proper PubMed syntax")

    if timeouts:
        print(f"\n❌ Queries causing TIMEOUT ({len(timeouts)}):")
        for desc, _, query in timeouts:
            print(f"   - {desc}: '{query[:60]}...'")

    if not no_results and not timeouts:
        print("\n✅ All queries returned results successfully!")

if __name__ == "__main__":
    asyncio.run(test_queries())