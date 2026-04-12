#!/usr/bin/env python3
"""
Debug script to test SambaNova streaming API
"""

import os
import httpx
import asyncio
import json
from dotenv import load_dotenv

load_dotenv()

async def test_streaming():
    api_key = os.getenv("SAMBANOVA_API_KEY")
    url = "https://api.sambanova.ai/v1/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": "Meta-Llama-3.3-70B-Instruct",
        "messages": [
            {"role": "user", "content": "Count to 5"}
        ],
        "max_tokens": 50,
        "stream": True,
        "stream_options": {"include_usage": True}
    }

    print(f"📡 Testing STREAMING API endpoint: {url}")
    print(f"📦 Model: {payload['model']}")

    async with httpx.AsyncClient() as client:
        try:
            # Use stream() method for SSE
            print("\n📊 Starting stream...")
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                print(f"📊 Response Status: {response.status_code}")

                if response.status_code != 200:
                    body = await response.aread()
                    print(f"❌ Error: {body.decode()}")
                    return

                accumulated = ""
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]  # Remove "data: " prefix

                        if data == "[DONE]":
                            print("\n✅ Stream completed!")
                            break

                        try:
                            chunk = json.loads(data)

                            # Handle usage-only chunks (sent at end of stream)
                            if "usage" in chunk and ("choices" not in chunk or len(chunk.get("choices", [])) == 0):
                                # This is a usage statistics chunk, skip it
                                print(f"\n📊 Usage stats: {chunk.get('usage', {})}")
                                continue

                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                delta = chunk["choices"][0].get("delta", {})
                                if "content" in delta:
                                    content = delta["content"]
                                    accumulated += content
                                    print(content, end="", flush=True)
                        except json.JSONDecodeError:
                            print(f"\n⚠️ Could not parse: {data[:100]}")

                print(f"\n\n📝 Full response: {accumulated}")

        except Exception as e:
            print(f"\n❌ Exception: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_streaming())