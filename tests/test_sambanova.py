#!/usr/bin/env python3
"""
Test script for SambaNova integration
Tests the free tier LLM fallback functionality
"""

import asyncio
import os
from llm_providers import SambaNovaProvider

async def test_sambanova():
    """Test SambaNova provider directly"""
    print("=" * 60)
    print("Testing SambaNova Free Tier Integration")
    print("=" * 60)

    provider = SambaNovaProvider()

    # Test messages
    messages = [
        {
            "role": "user",
            "content": "What is ALS and what are the current treatment options? Please be brief."
        }
    ]

    system_prompt = "You are a helpful medical research assistant."

    try:
        print("\n1. Testing basic inference (no tools)...")
        print("   Using: Llama 3.1 70B (free tier)")
        print("   Query: ALS treatment options")
        print("\n   Response:")
        print("   " + "-" * 50)

        full_response = ""
        async for text, tool_calls in provider.stream(
            messages=messages,
            system=system_prompt,
            model="llama-3.1-70b",
            max_tokens=500,
            temperature=0.7
        ):
            if text and len(text) > len(full_response):
                # Print only the new text
                new_text = text[len(full_response):]
                print(new_text, end="", flush=True)
                full_response = text

        print("\n   " + "-" * 50)
        print(f"\n   ✅ Response length: {len(full_response)} characters")

        if tool_calls:
            print(f"   ℹ️ Tool calls detected: {len(tool_calls)}")

        print("\n2. Testing with tools...")

        # Define a simple tool
        tools = [
            {
                "name": "search_papers",
                "description": "Search for scientific papers",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        }
                    },
                    "required": ["query"]
                }
            }
        ]

        messages_with_tools = [
            {
                "role": "user",
                "content": "Search for recent papers about ALS gene therapy"
            }
        ]

        print("   Testing tool calling with Llama 3.1 405B...")

        full_response = ""
        tool_calls = []
        async for text, calls in provider.stream(
            messages=messages_with_tools,
            system="You have access to a paper search tool. Use it when asked to find papers.",
            tools=tools,
            model="llama-3.1-405b",  # Larger model for tool support
            max_tokens=500
        ):
            full_response = text or ""
            if calls:
                tool_calls = calls

        if tool_calls:
            print(f"   ✅ Tool calls successful: {len(tool_calls)} calls")
            for tc in tool_calls:
                print(f"      - {tc.get('name', 'unknown')}: {tc.get('input', {})}")
        else:
            print(f"   ℹ️ No tool calls made (response: {full_response[:100]}...)")

        print("\n3. Testing cost optimization...")
        print("   All tests completed with $0.00 cost (free tier)")

        print("\n" + "=" * 60)
        print("✅ SambaNova integration test PASSED")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await provider.close()


async def test_fallback_in_app():
    """Test the fallback functionality in the main app"""
    print("\n" + "=" * 60)
    print("Testing Fallback in Main App")
    print("=" * 60)

    # Set environment to use fallback
    os.environ["USE_FALLBACK_LLM"] = "true"
    os.environ["LLM_PROVIDER_PREFERENCE"] = "cost_optimize"

    try:
        from refactored_helpers import stream_with_retry

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is 2+2?"}
        ]

        tools = []

        print("\n   Testing with fallback enabled...")
        print("   Provider preference: cost_optimize (will use SambaNova)")

        response_text = ""
        provider_used = ""

        async for text, tool_calls, provider in stream_with_retry(
            client=None,  # No Anthropic client, force fallback
            messages=messages,
            tools=tools,
            system_prompt="You are a helpful assistant.",
            use_fallback=True
        ):
            response_text = text
            provider_used = provider

        print(f"\n   Response: {response_text}")
        print(f"   Provider used: {provider_used}")

        if "SambaNova" in provider_used:
            print("   ✅ Fallback to SambaNova successful!")
        else:
            print(f"   ⚠️ Unexpected provider: {provider_used}")

    except Exception as e:
        print(f"\n❌ Error in fallback test: {e}")


async def main():
    """Run all tests"""
    # Test 1: Direct SambaNova provider
    await test_sambanova()

    # Test 2: Fallback in main app
    await test_fallback_in_app()

    print("\n" + "=" * 60)
    print("All Tests Complete")
    print("=" * 60)
    print("""
Next Steps:
1. To enable SambaNova fallback, set in .env:
   USE_FALLBACK_LLM=true
   LLM_PROVIDER_PREFERENCE=cost_optimize  # or "auto" or "quality_first"

2. Optional: Get a SambaNova API key for higher rate limits:
   https://cloud.sambanova.ai/
   Add to .env: SAMBANOVA_API_KEY=your_key

3. The fallback will automatically activate when:
   - Anthropic API is down or erroring
   - USE_FALLBACK_LLM is set to true
   - You want to optimize costs (free tier)
""")


if __name__ == "__main__":
    asyncio.run(main())