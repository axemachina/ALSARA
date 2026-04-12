#!/usr/bin/env python3
"""
Final test for ElevenLabs with fixed timeout
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

async def test_elevenlabs():
    """Test ElevenLabs with the fixed timeout"""
    print("=" * 60)
    print("ELEVENLABS FINAL TEST WITH TIMEOUT FIX")
    print("=" * 60)

    # Initialize MCP manager
    mcp_manager = MCPClientManager()
    servers_dir = Path(__file__).parent / "servers"
    elevenlabs_path = servers_dir / "elevenlabs_server.py"

    print(f"\n1. Initializing ElevenLabs server...")
    await mcp_manager.add_server("elevenlabs", str(elevenlabs_path))
    print("   ✅ Server initialized")

    # Test with 5000 character text (typical long response)
    long_text = """Recent research has identified significant biomarkers for ALS.
    TDP-43 pathology has been found in skin biopsies up to 26 years before symptom onset.
    This discovery represents a major breakthrough in early detection capabilities.
    The study examined multiple tissue types including muscle, lymph nodes, and skin.
    Skin biopsies showed the highest diagnostic potential due to accessibility.
    """ * 20  # Repeat to get close to 5000 chars

    long_text = long_text[:5000]

    print(f"\n2. Testing with {len(long_text)} characters...")
    print("   (This will take 30-70 seconds, please wait...)")

    start_time = time.time()

    try:
        # Use a longer timeout to match what the server now supports
        result = await asyncio.wait_for(
            mcp_manager.call_tool(
                "elevenlabs",
                "text_to_speech",
                {"text": long_text, "speed": 0.95}
            ),
            timeout=90.0  # 90 seconds should be enough with the new timeout
        )

        elapsed = time.time() - start_time
        print(f"   ✅ SUCCESS! Completed in {elapsed:.1f} seconds")

        if isinstance(result, str):
            result_data = json.loads(result)
            if result_data.get('status') == 'success':
                audio_size = len(result_data.get('audio_base64', ''))
                print(f"   Audio generated: {audio_size} bytes")
                print("   The 'Read last response' button should now work!")
            else:
                print(f"   Error: {result_data.get('error')} - {result_data.get('message')}")

    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        print(f"   ❌ TIMEOUT after {elapsed:.1f} seconds")
        print("   The timeout needs to be increased further")

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"   ❌ Error after {elapsed:.1f} seconds: {e}")

    print("\n" + "=" * 60)
    print("SUMMARY:")
    print("If this test succeeds, the 'Read last response' button")
    print("in the app should now work properly with long responses.")
    print("=" * 60)

if __name__ == "__main__":
    # Load .env file
    from dotenv import load_dotenv
    load_dotenv()

    asyncio.run(test_elevenlabs())