#!/usr/bin/env python3
"""
Direct test of ElevenLabs API using the official Python SDK
This will verify if your API key works with the ElevenLabs client
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Check if elevenlabs package is installed
try:
    from elevenlabs import ElevenLabs, play, save
except ImportError:
    print("❌ ElevenLabs SDK not installed!")
    print("Install it with: pip install elevenlabs")
    sys.exit(1)

def test_elevenlabs_sdk():
    """Test ElevenLabs API using the official SDK"""

    # Get API key from environment
    api_key = os.getenv("ELEVENLABS_API_KEY")

    print("🎤 Testing ElevenLabs SDK")
    print("=" * 60)

    if not api_key:
        print("❌ ERROR: ELEVENLABS_API_KEY not found in .env file")
        return False

    print(f"📝 Using API Key: {api_key[:10]}...")
    print(f"   Key length: {len(api_key)} characters")

    try:
        # Initialize the client
        print("\n🔌 Initializing ElevenLabs client...")
        client = ElevenLabs(api_key=api_key)

        # Test 1: Get user info (validates API key)
        print("\n📊 Testing API connection (getting user info)...")
        try:
            # The SDK doesn't have a direct user info method, so we'll test with voices
            voices = client.voices.get_all()
            print(f"✅ API key is valid! Found {len(voices.voices)} voices")

            # Show first 3 voices
            print("\n🎙️ Available voices:")
            for i, voice in enumerate(voices.voices[:3]):
                print(f"  {i+1}. {voice.name} (ID: {voice.voice_id[:15]}...)")

        except Exception as api_error:
            print(f"❌ API Error: {api_error}")
            if "401" in str(api_error) or "authentication" in str(api_error).lower():
                print("\n⚠️ Authentication failed! Your API key is invalid.")
                print("\n🔧 How to fix:")
                print("1. Go to https://elevenlabs.io")
                print("2. Sign in and go to your profile")
                print("3. Click on 'API Keys'")
                print("4. Generate a new API key")
                print("5. Update the ELEVENLABS_API_KEY in your .env file")
            return False

        # Test 2: Generate speech (if API key is valid)
        print("\n🎯 Testing text-to-speech conversion...")
        test_text = "Hello! This is a test of the ElevenLabs text to speech system."

        # Use a default voice ID (Rachel - clear and calm)
        voice_id = "21m00Tcm4TlvDq8ikWAM"

        print(f"   Text: '{test_text}'")
        print(f"   Voice ID: {voice_id}")

        # Generate audio
        audio = client.text_to_speech.convert(
            text=test_text,
            voice_id=voice_id,
            model_id="eleven_monolingual_v1",
            output_format="mp3_44100_128",
        )

        # Save the audio to a file
        output_file = "test_elevenlabs_output.mp3"
        print(f"\n💾 Saving audio to: {output_file}")

        with open(output_file, "wb") as f:
            for chunk in audio:
                f.write(chunk)

        print(f"✅ Audio saved successfully! File size: {os.path.getsize(output_file)} bytes")

        # Option to play the audio (requires audio output)
        print("\n🔊 Audio file created. You can play it with any audio player.")
        print(f"   File: {output_file}")

        # Uncomment this line if you want to play the audio automatically
        # play(audio)

        return True

    except ImportError as e:
        print(f"❌ Import Error: {e}")
        print("Make sure you have installed: pip install elevenlabs")
        return False

    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run the test"""
    print("\n" + "="*60)
    print("  ElevenLabs SDK Test")
    print("="*60 + "\n")

    success = test_elevenlabs_sdk()

    print("\n" + "="*60)
    if success:
        print("🎉 SUCCESS! Your ElevenLabs API is working!")
        print("The voice feature in your app should now work.")
    else:
        print("❌ FAILED! Please check your API key.")
        print("\nYour current key appears to be invalid or incorrectly formatted.")
        print("ElevenLabs API keys do NOT start with 'sk_' - that's an OpenAI format.")
    print("="*60)

if __name__ == "__main__":
    main()