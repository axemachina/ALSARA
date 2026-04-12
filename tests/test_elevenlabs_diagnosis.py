#!/usr/bin/env python3
"""
Diagnose why ElevenLabs is slow on a paid plan
"""

import asyncio
import httpx
import os
import json
import time
from dotenv import load_dotenv

load_dotenv()

async def test_elevenlabs_direct():
    """Test ElevenLabs API directly to diagnose the issue"""

    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("❌ No API key found")
        return

    print("=" * 60)
    print("ELEVENLABS PAID PLAN DIAGNOSIS")
    print("=" * 60)

    # 1. Check account subscription
    print("\n1. Checking your subscription...")
    async with httpx.AsyncClient(timeout=10) as client:
        headers = {"xi-api-key": api_key}

        # Get subscription info
        response = await client.get(
            "https://api.elevenlabs.io/v1/user/subscription",
            headers=headers
        )

        if response.status_code == 200:
            sub = response.json()
            print(f"   Tier: {sub.get('tier', 'Unknown')}")
            print(f"   Character count: {sub.get('character_count', 0):,} / {sub.get('character_limit', 0):,}")
            print(f"   Can use instant voice cloning: {sub.get('can_use_instant_voice_cloning', False)}")
            print(f"   Can use professional voice cloning: {sub.get('can_use_professional_voice_cloning', False)}")
        else:
            print(f"   ❌ Failed to get subscription: {response.status_code}")

    # 2. Test with different models
    print("\n2. Testing different models...")

    test_text = "This is a test of the ElevenLabs text to speech API performance on a paid plan. " * 25
    test_text = test_text[:500]  # 500 chars for quick test

    models = [
        ("eleven_turbo_v2", "Turbo (Fastest)"),
        ("eleven_monolingual_v1", "Monolingual (Current)"),
        ("eleven_multilingual_v2", "Multilingual (Slowest)")
    ]

    voice_id = "21m00Tcm4TlvDq8ikWAM"  # Rachel voice

    for model_id, model_name in models:
        print(f"\n   Testing {model_name}...")

        payload = {
            "text": test_text,
            "model_id": model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5
            }
        }

        try:
            start = time.time()

            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                    json=payload,
                    headers={"xi-api-key": api_key}
                )

                elapsed = time.time() - start

                if response.status_code == 200:
                    audio_size = len(response.content)
                    print(f"   ✅ Success in {elapsed:.1f}s - {audio_size:,} bytes")
                else:
                    print(f"   ❌ Error {response.status_code} after {elapsed:.1f}s")

        except Exception as e:
            elapsed = time.time() - start
            print(f"   ❌ Failed after {elapsed:.1f}s: {e}")

    # 3. Test with optimized settings
    print("\n3. Testing optimized settings...")

    optimized_settings = [
        ({"stability": 0.3, "similarity_boost": 0.3}, "Low quality, fast"),
        ({"stability": 0.5, "similarity_boost": 0.5}, "Medium quality"),
        ({"stability": 0.75, "similarity_boost": 0.75}, "High quality, slower")
    ]

    model_id = "eleven_turbo_v2"  # Use turbo for this test

    for settings, desc in optimized_settings:
        print(f"\n   Testing {desc}...")

        payload = {
            "text": test_text[:250],  # Shorter for quick test
            "model_id": model_id,
            "voice_settings": settings
        }

        try:
            start = time.time()

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                    json=payload,
                    headers={"xi-api-key": api_key}
                )

                elapsed = time.time() - start

                if response.status_code == 200:
                    print(f"   ✅ {elapsed:.1f}s")
                else:
                    print(f"   ❌ Error {response.status_code}")

        except Exception as e:
            print(f"   ❌ Failed: {e}")

    # 4. Check latency with streaming
    print("\n4. Testing streaming (should start faster)...")

    payload = {
        "text": test_text[:500],
        "model_id": "eleven_turbo_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
        }
    }

    try:
        start = time.time()
        first_chunk_time = None

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream",
                json=payload,
                headers={"xi-api-key": api_key}
            )

            # Note: This doesn't actually stream in this test, just measures response time
            elapsed = time.time() - start

            if response.status_code == 200:
                print(f"   ✅ Stream response in {elapsed:.1f}s")
            else:
                print(f"   ❌ Error {response.status_code}")

    except Exception as e:
        print(f"   ❌ Failed: {e}")

    print("\n" + "=" * 60)
    print("ANALYSIS:")
    print("- If Turbo model is 5+ seconds for 500 chars, there's a problem")
    print("- If all models are slow, could be network/region issue")
    print("- If streaming is much faster, we should use streaming API")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_elevenlabs_direct())