#!/usr/bin/env python3
"""
Test bioRxiv API directly to check if it's responding
"""

import httpx
import asyncio
from datetime import datetime, timedelta

async def test_direct_api():
    """Test bioRxiv API directly"""
    print("=" * 70)
    print("TESTING BIORXIV API DIRECTLY")
    print("=" * 70)

    # Setup dates (last 30 days)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    base_url = "https://api.biorxiv.org/details"

    # Test with a short timeout
    async with httpx.AsyncClient(timeout=10.0) as client:
        url = f"{base_url}/biorxiv/{start_date_str}/{end_date_str}/0"

        print(f"\nTesting URL: {url}")
        print("-" * 40)

        try:
            import time
            start = time.time()
            response = await client.get(url)
            elapsed = time.time() - start

            response.raise_for_status()
            data = response.json()

            collection = data.get("collection", [])

            print(f"✅ SUCCESS!")
            print(f"   Response time: {elapsed:.2f} seconds")
            print(f"   Papers returned: {len(collection)}")
            print(f"   Status code: {response.status_code}")

            if collection:
                print("\n   First 3 papers:")
                for i, paper in enumerate(collection[:3], 1):
                    title = paper.get("title", "No title")[:60]
                    print(f"   {i}. {title}...")

            # Check for cursor info
            messages = data.get("messages", [])
            if messages:
                print(f"\n   Messages: {messages[0] if messages else 'None'}")

        except httpx.TimeoutException:
            elapsed = time.time() - start
            print(f"❌ TIMEOUT after {elapsed:.2f} seconds")
            print("   The bioRxiv API is not responding within 10 seconds")
        except httpx.HTTPError as e:
            print(f"❌ HTTP Error: {e}")
        except Exception as e:
            print(f"❌ Error: {e}")

    print("\n" + "=" * 70)
    print("CONCLUSION")
    print("=" * 70)
    print("""
    If this test:
    - SUCCEEDS: The API is working, issue is in our server code
    - TIMES OUT: The bioRxiv API is genuinely slow/unresponsive
    - ERRORS: Check the error message for API issues
    """)

if __name__ == "__main__":
    asyncio.run(test_direct_api())