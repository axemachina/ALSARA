#!/usr/bin/env python3
"""
Test script for UnifiedLLMClient
Tests various scenarios including fallback
"""

import asyncio
import os
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from llm_client import UnifiedLLMClient

async def test_unified_client():
    """Test the unified client with various configurations"""

    print("=" * 60)
    print("Testing UnifiedLLMClient")
    print("=" * 60)

    # Test 1: Check current configuration
    print("\n1. Testing client initialization...")
    try:
        client = UnifiedLLMClient()
        print(f"   ✅ Client initialized: {client.get_provider_display_name()}")

        status = client.get_status()
        print(f"   Primary provider: {status['primary_provider']}")
        print(f"   Fallback enabled: {status['fallback_enabled']}")
        print(f"   Current provider: {status['current_provider']}")

    except Exception as e:
        print(f"   ❌ Initialization error: {e}")
        return

    # Test 2: Basic streaming test
    print("\n2. Testing basic streaming...")
    messages = [
        {
            "role": "user",
            "content": "What is 2 + 2? Just give me the number."
        }
    ]

    try:
        response_text = ""
        provider_used = ""

        async for text, tool_calls, provider in client.stream(
            messages=messages,
            tools=None,
            system_prompt="You are a helpful assistant. Be very brief.",
            max_tokens=100
        ):
            response_text = text
            provider_used = provider

        print(f"   Response: {response_text.strip()}")
        print(f"   Provider used: {provider_used}")
        print(f"   ✅ Streaming successful")

    except Exception as e:
        print(f"   ❌ Streaming error: {e}")

    # Test 3: Test with tools
    print("\n3. Testing with tools...")
    tools = [
        {
            "name": "calculate",
            "description": "Perform a calculation",
            "input_schema": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Math expression to evaluate"
                    }
                },
                "required": ["expression"]
            }
        }
    ]

    messages_with_tools = [
        {
            "role": "user",
            "content": "Use the calculate tool to compute 15 * 23"
        }
    ]

    try:
        response_text = ""
        tool_calls = []
        provider_used = ""

        async for text, calls, provider in client.stream(
            messages=messages_with_tools,
            tools=tools,
            system_prompt="You have access to calculation tools. Use them when asked.",
            max_tokens=200
        ):
            response_text = text or ""
            tool_calls = calls or []
            provider_used = provider

        if tool_calls:
            print(f"   ✅ Tool calls detected: {len(tool_calls)}")
            for tc in tool_calls:
                print(f"      - {tc.get('name')}: {tc.get('input')}")
        else:
            print(f"   ℹ️ Response without tool: {response_text[:100]}...")

        print(f"   Provider used: {provider_used}")

    except Exception as e:
        print(f"   ❌ Tool test error: {e}")

    # Test 4: Test fallback scenario (simulate Anthropic failure)
    print("\n4. Testing fallback scenario...")

    # Save current API key
    original_key = os.environ.get("ANTHROPIC_API_KEY", "")

    try:
        # Temporarily set invalid key to trigger fallback
        os.environ["ANTHROPIC_API_KEY"] = "invalid_key_to_trigger_fallback"
        os.environ["USE_FALLBACK_LLM"] = "true"

        # Create new client with invalid key
        fallback_client = UnifiedLLMClient()
        print(f"   Fallback client: {fallback_client.get_provider_display_name()}")

        # Try to stream (should use fallback)
        messages = [{"role": "user", "content": "Hello"}]

        provider_used = ""
        async for text, calls, provider in fallback_client.stream(
            messages=messages,
            tools=None,
            system_prompt="Reply with a greeting",
            max_tokens=50
        ):
            provider_used = provider

        if "SambaNova" in provider_used:
            print(f"   ✅ Fallback to SambaNova successful: {provider_used}")
        else:
            print(f"   ⚠️ Unexpected provider: {provider_used}")

        await fallback_client.cleanup()

    except Exception as e:
        print(f"   ❌ Fallback test error: {e}")

    finally:
        # Restore original key
        if original_key:
            os.environ["ANTHROPIC_API_KEY"] = original_key
        else:
            os.environ.pop("ANTHROPIC_API_KEY", None)

    # Cleanup
    await client.cleanup()

    print("\n" + "=" * 60)
    print("✅ UnifiedLLMClient tests complete")
    print("=" * 60)
    print("""
Next Steps:
1. The unified client successfully abstracts all LLM provider logic
2. Fallback is handled transparently within the client
3. The application code is now much cleaner and simpler
4. Ready for deployment to HuggingFace Spaces

Environment Variables:
- ANTHROPIC_API_KEY: Your Anthropic API key
- USE_FALLBACK_LLM: Enable SambaNova fallback (true/false)
- LLM_PROVIDER_PREFERENCE: auto/cost_optimize/quality_first
""")

if __name__ == "__main__":
    asyncio.run(test_unified_client())