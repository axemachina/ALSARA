#!/usr/bin/env python3
"""
Test if ElevenLabs has a timeout issue when processing longer text
"""

import asyncio
import sys
import os
import json
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from custom_mcp_client import MCPClientManager

async def test_with_timeout():
    """Test ElevenLabs with various text lengths to check for timeout"""
    print("=" * 60)
    print("ELEVENLABS TIMEOUT TEST")
    print("=" * 60)

    # Initialize MCP manager
    mcp_manager = MCPClientManager()
    servers_dir = Path(__file__).parent / "servers"
    elevenlabs_path = servers_dir / "elevenlabs_server.py"

    print(f"\n1. Initializing ElevenLabs server...")
    try:
        await mcp_manager.add_server("elevenlabs", str(elevenlabs_path))
        print("   ✅ Server initialized")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return

    # Test with 5000 character text (same as app)
    long_text = """Recent research has identified significant biomarkers for ALS.
    TDP-43 pathology has been found in skin biopsies up to 26 years before symptom onset.
    This discovery represents a major breakthrough in early detection capabilities.
    The study examined multiple tissue types including muscle, lymph nodes, and skin.
    Skin biopsies showed the highest diagnostic potential due to accessibility.
    """ * 20  # Repeat to get close to 5000 chars

    # Truncate to exactly 5000 chars
    long_text = long_text[:5000]

    print(f"\n2. Testing with {len(long_text)} characters...")
    print("   Starting timer...")

    start_time = time.time()

    try:
        # Set a timeout similar to what might be in the app
        result = await asyncio.wait_for(
            mcp_manager.call_tool(
                "elevenlabs",
                "text_to_speech",
                {"text": long_text, "speed": 0.95}
            ),
            timeout=35.0  # 35 seconds to see if it completes
        )

        elapsed = time.time() - start_time
        print(f"   ✅ Completed in {elapsed:.1f} seconds")

        if isinstance(result, str):
            result_data = json.loads(result)
            if result_data.get('status') == 'success':
                print(f"   Audio generated: {len(result_data.get('audio_base64', ''))} chars")
            else:
                print(f"   Error: {result_data.get('error')} - {result_data.get('message')}")

    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        print(f"   ❌ TIMEOUT after {elapsed:.1f} seconds!")
        print("   This explains the error in the app")

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"   ❌ Error after {elapsed:.1f} seconds: {e}")

    # Test with shorter text
    short_text = "This is a short test message for ElevenLabs text to speech."
    print(f"\n3. Testing with short text ({len(short_text)} chars)...")

    start_time = time.time()
    try:
        result = await asyncio.wait_for(
            mcp_manager.call_tool(
                "elevenlabs",
                "text_to_speech",
                {"text": short_text}
            ),
            timeout=10.0
        )

        elapsed = time.time() - start_time
        print(f"   ✅ Completed in {elapsed:.1f} seconds")

    except asyncio.TimeoutError:
        print(f"   ❌ TIMEOUT!")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    print("\n" + "=" * 60)
    print("ANALYSIS:")
    print("If long text times out but short text works, the issue is:")
    print("1. ElevenLabs API is slow with longer texts")
    print("2. The timeout in the app needs to be increased")
    print("3. Or the text needs to be chunked into smaller pieces")
    print("=" * 60)

if __name__ == "__main__":
    # Load .env file
    from dotenv import load_dotenv
    load_dotenv()

    asyncio.run(test_with_timeout())