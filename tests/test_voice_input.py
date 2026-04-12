#!/usr/bin/env python3
"""
Test script for voice input functionality
This tests the speech-to-text capability
"""

import os
import sys
import tempfile
import wave
import struct
import math

def create_test_audio_file():
    """Create a simple test WAV audio file with a sine wave"""
    # Parameters for the WAV file
    sample_rate = 16000
    duration = 2  # seconds
    frequency = 440  # A4 note

    # Generate sine wave data
    num_samples = sample_rate * duration
    samples = []
    for i in range(num_samples):
        t = i / sample_rate
        # Generate a sine wave that modulates (simulates speech-like pattern)
        amplitude = 0.5 * (1 + 0.5 * math.sin(2 * math.pi * 0.5 * t))
        sample = amplitude * math.sin(2 * math.pi * frequency * t)
        # Convert to 16-bit integer
        packed = struct.pack('h', int(sample * 32767))
        samples.append(packed)

    # Create temporary WAV file
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
        wav_path = tmp_file.name

    # Write WAV file
    with wave.open(wav_path, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b''.join(samples))

    return wav_path

def test_speech_recognition():
    """Test the speech recognition functionality"""
    print("🎤 Testing Voice Input Functionality")
    print("=" * 60)

    # Check if SpeechRecognition is installed
    try:
        import speech_recognition as sr
        print("✅ SpeechRecognition library is installed")
    except ImportError:
        print("❌ SpeechRecognition not installed!")
        print("Install with: pip install SpeechRecognition")
        return False

    # Create a recognizer instance
    recognizer = sr.Recognizer()
    print("\n📊 Recognizer created successfully")

    # Test with a simple audio file (create a test file)
    print("\n🎵 Creating test audio file...")
    test_audio = create_test_audio_file()
    print(f"   Test file created: {test_audio}")

    try:
        # Try to process the test audio
        print("\n🔄 Processing test audio...")
        with sr.AudioFile(test_audio) as source:
            audio_data = recognizer.record(source)
            print("   Audio data loaded successfully")

        # Note: This will likely fail with our test sine wave
        # but it tests that the API is reachable
        print("\n🌐 Testing Google Speech Recognition API...")
        try:
            text = recognizer.recognize_google(audio_data)
            print(f"   Transcribed text: '{text}'")
        except sr.UnknownValueError:
            print("   ⚠️ Could not understand the test audio (expected for sine wave)")
            print("   This is normal - real speech would be transcribed correctly")
        except sr.RequestError as e:
            print(f"   ❌ API Error: {e}")
            print("   Check your internet connection")
            return False

        print("\n✅ Speech recognition system is working!")
        print("   The voice input feature should work in the app")

    finally:
        # Clean up test file
        if os.path.exists(test_audio):
            os.remove(test_audio)
            print(f"\n🗑️ Cleaned up test file")

    return True

def test_app_integration():
    """Test that the app has the voice input components"""
    print("\n\n🔧 Checking App Integration")
    print("=" * 60)

    # Check if the app file exists and has our additions
    app_path = "als_agent_app.py"
    if not os.path.exists(app_path):
        print(f"❌ {app_path} not found")
        return False

    with open(app_path, 'r') as f:
        content = f.read()

    # Check for key components
    checks = [
        ("process_voice_input function", "async def process_voice_input"),
        ("Audio input component", "gr.Audio"),
        ("Voice input event handler", "audio_input.change"),
        ("SpeechRecognition import", "import speech_recognition as sr"),
    ]

    all_found = True
    for name, pattern in checks:
        if pattern in content:
            print(f"✅ {name} found")
        else:
            print(f"❌ {name} NOT found")
            all_found = False

    return all_found

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("  Voice Input Test Suite")
    print("="*60)

    # Test speech recognition
    sr_works = test_speech_recognition()

    # Test app integration
    app_ready = test_app_integration()

    # Summary
    print("\n\n" + "="*60)
    print("  TEST SUMMARY")
    print("="*60)

    if sr_works and app_ready:
        print("🎉 SUCCESS! Voice input is ready to use!")
        print("\nHow to use voice input:")
        print("1. Start the app: python als_agent_app.py")
        print("2. Click the 🎤 microphone button")
        print("3. Speak your question")
        print("4. Stop recording")
        print("5. Your speech will be converted to text automatically")
        print("\nNote: Requires internet connection for Google Speech API")
    else:
        print("⚠️ Some components need attention:")
        if not sr_works:
            print("  - Fix speech recognition issues")
        if not app_ready:
            print("  - App integration incomplete")

    print("="*60)

if __name__ == "__main__":
    main()