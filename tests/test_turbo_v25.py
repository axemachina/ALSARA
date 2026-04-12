#!/usr/bin/env python3
"""
Test if eleven_turbo_v2.5 is available and faster
"""

import asyncio
import httpx
import os
import time
import json
from dotenv import load_dotenv

load_dotenv()

async def test_turbo_models():
    """Test both turbo models to see which is faster"""

    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("❌ No API key found")
        return

    print("=" * 60)
    print("TESTING TURBO V2.5 MODEL")
    print("=" * 60)

    # Test text (2500 chars for realistic comparison)
    test_text = """
    Recent breakthrough research in ALS has identified TDP-43 pathology in skin biopsies
    as a potential biomarker appearing up to 26 years before symptom onset. This discovery
    could revolutionize early detection and treatment strategies. The study examined multiple
    tissue types including muscle, lymph nodes, and skin, with skin biopsies showing the
    highest diagnostic potential due to accessibility. Researchers found that TDP-43 pathology
    was present in all 17 individuals who later developed ALS, suggesting this could serve as
    a reliable predictive biomarker similar to how alpha-synuclein is used for Parkinson's disease.
    """ * 10
    test_text = test_text[:2500]

    voice_id = "21m00Tcm4TlvDq8ikWAM"  # Rachel voice

    models_to_test = [
        ("eleven_turbo_v2", "Turbo v2 (Current)"),
        ("eleven_turbo_v2.5", "Turbo v2.5 (Newest)"),
        ("eleven_turbo_v2_5", "Turbo v2.5 (Alt naming)"),  # Try alternative naming
    ]

    print(f"\nTesting with {len(test_text)} characters...")
    print("-" * 40)

    for model_id, model_name in models_to_test:
        print(f"\n{model_name}:")

        payload = {
            "text": test_text,
            "model_id": model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5,
                "style": 0.0,
                "use_speaker_boost": True
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
                    print(f"  ✅ SUCCESS in {elapsed:.1f}s - {audio_size:,} bytes")

                    # Save timing for comparison
                    if "v2.5" in model_name:
                        v25_time = elapsed
                    elif model_id == "eleven_turbo_v2":
                        v2_time = elapsed

                elif response.status_code == 400:
                    error_data = response.json()
                    print(f"  ❌ Model not available: {error_data.get('detail', {}).get('message', 'Unknown error')}")
                else:
                    print(f"  ❌ Error {response.status_code}: {response.text[:100]}")

        except Exception as e:
            elapsed = time.time() - start
            print(f"  ❌ Failed after {elapsed:.1f}s: {e}")

    # Test with optimize_streaming_latency option if v2.5 works
    print("\n" + "-" * 40)
    print("Testing v2.5 with streaming optimization:")

    payload = {
        "text": test_text[:1000],  # Shorter for quick test
        "model_id": "eleven_turbo_v2.5",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5,
            "style": 0.0,
            "use_speaker_boost": True
        },
        "optimize_streaming_latency": 4  # Maximum optimization
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
                print(f"  ✅ With streaming optimization: {elapsed:.1f}s")
            else:
                print(f"  ❌ Not available")

    except Exception as e:
        print(f"  ❌ Failed: {e}")

    print("\n" + "=" * 60)
    print("RECOMMENDATION:")
    print("If v2.5 works and is faster, update DEFAULT_MODEL in elevenlabs_server.py")
    print("If not available, stick with eleven_turbo_v2")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_turbo_models())