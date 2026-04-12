#!/usr/bin/env python3
"""
Test the full LLM integration with SambaNova
"""

import asyncio
import os
from dotenv import load_dotenv
from llm_providers import LLMRouter

load_dotenv()

async def test_unified_client():
    """Test the LLMRouter with SambaNova streaming"""

    print("🧪 Testing LLMRouter with SambaNova...")
    print("=" * 50)

    # Initialize client (will use SambaNova as primary)
    client = LLMRouter()

    messages = [
        {"role": "user", "content": "Count from 1 to 5 in a single line"}
    ]

    print("📤 Sending message: Count from 1 to 5 in a single line")
    print("📡 Streaming response...")
    print("-" * 50)

    try:
        accumulated = ""
        provider = None
        async for text, tool_calls, provider_used in client.stream_with_fallback(
            messages=messages,
            tools=[],  # No tools for this test
            system_prompt="You are a helpful assistant.",
            provider_preference="cost_optimize"  # Use SambaNova first
        ):
            # Show only new content
            new_content = text[len(accumulated):]
            if new_content:
                print(new_content, end="", flush=True)
                accumulated = text
            provider = provider_used

        print("\n" + "-" * 50)
        print(f"✅ Test passed! Full response: {accumulated}")
        print(f"🎯 Provider used: {provider}")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_unified_client())