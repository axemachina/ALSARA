#!/usr/bin/env python3
"""
Test bioRxiv search coverage and consistency
"""

import asyncio
import sys
import os
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import MCP client setup
from custom_mcp_client import setup_mcp_client

async def test_biorxiv_searches():
    """Test various bioRxiv searches to ensure it's working properly"""

    # Initialize MCP clients
    print("=" * 70)
    print("TESTING BIORXIV SEARCH COVERAGE")
    print("=" * 70)

    call_tool, cleanup = await setup_mcp_client(verbose=False)

    test_queries = [
        ("ALS gene therapy", "Should find gene therapy preprints"),
        ("ALS SOD1", "Should find SOD1-related preprints"),
        ("ALS biomarkers", "Should find biomarker studies"),
        ("ALS TDP-43", "Should find TDP-43 research"),
        ("psilocybin ALS", "Specific query - may have limited results"),
        ("ALS stem cell", "Should find stem cell research")
    ]

    results_summary = []

    for query, description in test_queries:
        print(f"\nTesting: {query}")
        print(f"Expected: {description}")
        print("-" * 40)

        try:
            # Test bioRxiv search
            result = await call_tool(
                "biorxiv",
                "search_preprints",
                {
                    "query": query,
                    "server": "both",  # Search both bioRxiv and medRxiv
                    "max_results": 5
                }
            )

            # Parse results
            if result:
                # Count the number of preprints found
                lines = result.split('\n')
                preprint_count = 0
                dois = []

                for line in lines:
                    if 'DOI:' in line or '10.1101/' in line:
                        preprint_count += 1
                        # Extract DOI if present
                        if '10.1101/' in line:
                            import re
                            doi_match = re.search(r'10\.1101/[\d.]+', line)
                            if doi_match:
                                dois.append(doi_match.group())

                print(f"✅ Found {preprint_count} preprints")
                if dois:
                    print(f"   Sample DOIs: {', '.join(dois[:2])}")

                results_summary.append({
                    "query": query,
                    "count": preprint_count,
                    "status": "OK" if preprint_count > 0 else "NO_RESULTS"
                })
            else:
                print("❌ No response from bioRxiv server")
                results_summary.append({
                    "query": query,
                    "count": 0,
                    "status": "ERROR"
                })

        except Exception as e:
            print(f"❌ Error: {e}")
            results_summary.append({
                "query": query,
                "count": 0,
                "status": "ERROR",
                "error": str(e)
            })

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    total_queries = len(results_summary)
    successful = sum(1 for r in results_summary if r["status"] == "OK")
    no_results = sum(1 for r in results_summary if r["status"] == "NO_RESULTS")
    errors = sum(1 for r in results_summary if r["status"] == "ERROR")

    print(f"Total queries tested: {total_queries}")
    print(f"✅ Successful (with results): {successful}")
    print(f"⚠️ No results found: {no_results}")
    print(f"❌ Errors: {errors}")

    print("\nDetailed Results:")
    for result in results_summary:
        status_icon = "✅" if result["status"] == "OK" else "⚠️" if result["status"] == "NO_RESULTS" else "❌"
        print(f"{status_icon} {result['query']}: {result['count']} results")

    # Cleanup
    await cleanup()

    # Analysis
    print("\n" + "=" * 70)
    print("ANALYSIS")
    print("=" * 70)

    if successful < total_queries * 0.5:
        print("⚠️ WARNING: Less than 50% of queries returned results")
        print("Possible issues:")
        print("1. bioRxiv server may be too restrictive in filtering")
        print("2. Time range (365 days) may be too limited")
        print("3. Matching algorithm may need adjustment")
    else:
        print("✅ bioRxiv search coverage appears adequate")

    if no_results > 0:
        print(f"\n{no_results} queries returned no results - this may be expected for very specific topics")

    return results_summary

if __name__ == "__main__":
    results = asyncio.run(test_biorxiv_searches())

    # Check if we need to investigate further
    if any(r["status"] == "ERROR" for r in results):
        print("\n⚠️ Some searches failed - check server logs for details")