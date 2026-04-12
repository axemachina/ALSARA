#!/usr/bin/env python3
"""
Debug test for ElevenLabs text-to-speech issue
"""

import asyncio
import sys
import os
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from custom_mcp_client import MCPClientManager

async def test_elevenlabs():
    """Test ElevenLabs directly"""
    print("=" * 60)
    print("ELEVENLABS DEBUG TEST")
    print("=" * 60)

    # Check API key
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if api_key:
        print(f"✅ API key found: {api_key[:10]}...")
    else:
        print("❌ No API key in environment")

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

    # Test with simple text
    test_text = "Hello, this is a test of the ElevenLabs text to speech system."

    print(f"\n2. Testing text-to-speech with: '{test_text}'")
    print("   Calling tool...")

    try:
        result = await mcp_manager.call_tool(
            "elevenlabs",
            "text_to_speech",
            {
                "text": test_text,
                "speed": 0.95
            }
        )

        print("\n3. Raw result type:", type(result))
        print("   First 500 chars:", str(result)[:500])

        # Try to parse the result
        if isinstance(result, str):
            try:
                result_data = json.loads(result)
                print("\n4. Parsed result structure:")
                print(f"   Status: {result_data.get('status')}")
                print(f"   Error: {result_data.get('error')}")
                print(f"   Message: {result_data.get('message')}")

                if result_data.get('audio_base64'):
                    print(f"   Audio data: {len(result_data.get('audio_base64'))} chars")
                else:
                    print("   No audio data in response")

            except json.JSONDecodeError as e:
                print(f"\n4. JSON decode error: {e}")
        else:
            print(f"\n4. Result is not a string: {result}")

    except Exception as e:
        print(f"\n   ❌ Tool call failed: {e}")
        import traceback
        traceback.print_exc()

    # Test with longer text
    long_text = """
    Recent breakthrough research has identified TDP-43 pathology in skin biopsies
    as a potential biomarker for ALS, appearing up to 26 years before symptom onset.
    This discovery could revolutionize early detection and treatment of the disease.
    """

    print(f"\n5. Testing with longer text...")
    try:
        result = await mcp_manager.call_tool(
            "elevenlabs",
            "text_to_speech",
            {"text": long_text.strip()}
        )

        if isinstance(result, str):
            result_data = json.loads(result)
            print(f"   Status: {result_data.get('status')}")
            if result_data.get('status') == 'error':
                print(f"   Error: {result_data.get('error')} - {result_data.get('message')}")
            else:
                print(f"   Success! Audio length: {len(result_data.get('audio_base64', ''))} chars")
    except Exception as e:
        print(f"   Failed: {e}")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    # Load .env file
    from dotenv import load_dotenv
    load_dotenv()

    asyncio.run(test_elevenlabs())