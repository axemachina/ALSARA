#!/usr/bin/env python3
"""
Direct test of ElevenLabs API key
This will help us verify if your API key is valid
"""

import os
import httpx
import asyncio
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def test_elevenlabs_api_key():
    """Test the ElevenLabs API key directly"""

    api_key = os.getenv("ELEVENLABS_API_KEY")

    print("🔍 Testing ElevenLabs API Key")
    print("=" * 60)

    if not api_key:
        print("❌ ERROR: ELEVENLABS_API_KEY not found in .env file")
        return

    # Check key format
    print(f"📝 API Key Details:")
    print(f"   - Starts with: {api_key[:5]}...")
    print(f"   - Length: {len(api_key)} characters")
    print(f"   - Format check: ", end="")

    # ElevenLabs keys typically have a specific format
    if api_key.startswith("sk_"):
        print("⚠️  Unusual format - ElevenLabs keys typically don't start with 'sk_'")
        print("     This might be an OpenAI/Anthropic style key instead")
    else:
        print("✅ Format looks correct for ElevenLabs")

    print("\n🌐 Testing API Connection...")
    print("-" * 40)

    # Test 1: Check user info endpoint (most basic test)
    try:
        url = "https://api.elevenlabs.io/v1/user"
        headers = {"xi-api-key": api_key}

        print(f"Testing endpoint: {url}")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)

            print(f"Response status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print("✅ SUCCESS! API key is valid!")
                print("\n📊 Account Info:")
                print(f"   - Character limit: {data.get('subscription', {}).get('character_limit', 'N/A')}")
                print(f"   - Characters used: {data.get('subscription', {}).get('character_count', 'N/A')}")
                print(f"   - Tier: {data.get('subscription', {}).get('tier', 'N/A')}")
                return True

            elif response.status_code == 401:
                print("❌ AUTHENTICATION FAILED!")
                print("\n🔧 How to fix:")
                print("1. Go to https://elevenlabs.io")
                print("2. Sign in to your account")
                print("3. Go to Profile Settings → API Keys")
                print("4. Generate a new API key")
                print("5. The key should look different from 'sk_...' format")
                print("6. Update your .env file with the new key")

                # Try to parse error message
                try:
                    error_data = response.json()
                    if "detail" in error_data:
                        print(f"\nError details: {error_data['detail']}")
                except:
                    print(f"\nRaw response: {response.text}")

            else:
                print(f"⚠️ Unexpected response: {response.status_code}")
                print(f"Response: {response.text}")

    except httpx.TimeoutException:
        print("❌ Request timed out - check your internet connection")

    except Exception as e:
        print(f"❌ Error testing API: {e}")

    return False

async def test_voices_list():
    """Test listing available voices"""
    api_key = os.getenv("ELEVENLABS_API_KEY")

    if not api_key:
        return

    print("\n\n🎤 Testing Voice List Endpoint...")
    print("-" * 40)

    try:
        url = "https://api.elevenlabs.io/v1/voices"
        headers = {"xi-api-key": api_key}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                voices = data.get("voices", [])
                print(f"✅ Found {len(voices)} available voices")
                if voices:
                    print("\nFirst 3 voices:")
                    for voice in voices[:3]:
                        print(f"  - {voice['name']} (ID: {voice['voice_id'][:10]}...)")
            else:
                print(f"❌ Failed to list voices: {response.status_code}")

    except Exception as e:
        print(f"❌ Error listing voices: {e}")

async def main():
    """Run all tests"""

    print("\n" + "="*60)
    print("  ElevenLabs API Key Diagnostic Tool")
    print("="*60 + "\n")

    # Test the API key
    key_valid = await test_elevenlabs_api_key()

    # If key is valid, test voice listing
    if key_valid:
        await test_voices_list()

        print("\n" + "="*60)
        print("🎉 Your ElevenLabs API is working correctly!")
        print("The voice feature should now work in your app.")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("⚠️  API Key Issue Detected")
        print("\n📝 Next Steps:")
        print("1. Get your correct API key from https://elevenlabs.io")
        print("2. Look for 'API Key' in your profile settings")
        print("3. The key format should NOT start with 'sk_'")
        print("4. Update the ELEVENLABS_API_KEY in your .env file")
        print("5. Run this test again to verify")
        print("="*60)

if __name__ == "__main__":
    asyncio.run(main())