#!/usr/bin/env python3
"""
Simple ElevenLabs SDK test
Tests the basic TTS functionality using the official SDK
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    from elevenlabs import ElevenLabs
    print("✅ ElevenLabs SDK imported successfully")
except ImportError:
    print("❌ ElevenLabs SDK not installed!")
    print("Install with: pip install elevenlabs")
    exit(1)

def test_tts():
    """Simple TTS test using ElevenLabs SDK"""

    # Get API key
    api_key = os.getenv("ELEVENLABS_API_KEY")

    if not api_key:
        print("❌ No ELEVENLABS_API_KEY found in .env")
        return False

    print(f"🔑 Using API key: {api_key[:10]}...")

    try:
        # Initialize client
        client = ElevenLabs(api_key=api_key)
        print("✅ Client initialized")

        # Test text
        test_text = "Hello! This is a test of the ElevenLabs text to speech API."
        print(f"📝 Test text: '{test_text}'")

        # Generate speech
        print("🎯 Generating speech...")
        audio = client.text_to_speech.convert(
            text=test_text,
            voice_id="21m00Tcm4TlvDq8ikWAM",  # Rachel voice
            model_id="eleven_monolingual_v1"
        )

        # Save to file
        output_file = "test_output.mp3"
        with open(output_file, "wb") as f:
            for chunk in audio:
                f.write(chunk)

        file_size = os.path.getsize(output_file)
        print(f"✅ Success! Audio saved to {output_file} ({file_size} bytes)")

        # Clean up
        os.remove(output_file)
        print("🧹 Cleaned up test file")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("\n" + "="*50)
    print("ElevenLabs SDK Simple Test")
    print("="*50 + "\n")

    success = test_tts()

    print("\n" + "="*50)
    if success:
        print("✅ TEST PASSED - ElevenLabs TTS is working!")
        print("\nThe voice feature in your app should work now.")
        print("Make sure you're using the fresh instance on port 7890:")
        print("http://localhost:7890")
    else:
        print("❌ TEST FAILED - Check the error above")
    print("="*50)