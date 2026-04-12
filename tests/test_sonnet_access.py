#!/usr/bin/env python3
"""
Test script to check if your Anthropic API key has access to Claude 3.5 Sonnet
"""

import os
import sys
from dotenv import load_dotenv
from anthropic import Anthropic, APIError

# Load environment variables
load_dotenv()

def print_header():
    """Print test header"""
    print("\n" + "="*60)
    print("🔍 Testing Anthropic API Access for Claude 3.5 Sonnet")
    print("="*60 + "\n")

def test_api_key():
    """Test 1: Check if API key is configured"""
    print("Test 1: API Key Configuration")
    print("-" * 30)

    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        print("❌ No API key found!")
        print("   Please set ANTHROPIC_API_KEY in your .env file or environment")
        return None

    if api_key.startswith("sk-"):
        print("✅ API key found and properly formatted")
    else:
        print("⚠️  API key found but may be incorrectly formatted")
        print("   (Should start with 'sk-')")

    return api_key

def test_claude_opus(client):
    """Test 2: Test with Claude 3 Opus (baseline)"""
    print("\nTest 2: Claude 3 Opus (Baseline)")
    print("-" * 30)

    try:
        response = client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=10,
            messages=[
                {"role": "user", "content": "Say 'hello'"}
            ]
        )
        print("✅ Claude 3 Opus works!")
        print(f"   Response: {response.content[0].text}")
        return True
    except APIError as e:
        if e.status_code == 401:
            print("❌ Authentication failed - Invalid API key")
        elif e.status_code == 404:
            print("❌ Claude 3 Opus not available")
        else:
            print(f"❌ Error: {e.message}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False

def test_claude_sonnet(client):
    """Test 3: Test with Claude 3.5 Sonnet"""
    print("\nTest 3: Claude 3.5 Sonnet")
    print("-" * 30)

    try:
        response = client.messages.create(
            #model="claude-3-5-sonnet-20241022",
            model="claude-sonnet-4-5-20250929",
            max_tokens=10,
            messages=[
                {"role": "user", "content": "Say 'hello'"}
            ]
        )
        print("✅ Claude 3.5 Sonnet works!")
        print(f"   Response: {response.content[0].text}")
        return True
    except APIError as e:
        if e.status_code == 404:
            print("❌ Claude 3.5 Sonnet not accessible")
            print("   This model requires a paid account with billing enabled")
        elif e.status_code == 401:
            print("❌ Authentication failed")
        else:
            print(f"❌ Error: {e.message}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False

def test_available_models(client):
    """Test 4: List available models"""
    print("\nTest 4: Available Models")
    print("-" * 30)

    # Common models to test
    models_to_test = [
        ("claude-3-5-sonnet-20241022", "Claude 3.5 Sonnet (Latest)"),
        ("claude-3-opus-20240229", "Claude 3 Opus"),
        ("claude-sonnet-4-5-20250929", "Claude 4.5 Sonnet"),
        ("claude-3-haiku-20240307", "Claude 3 Haiku"),
    ]

    available = []
    unavailable = []

    for model_id, model_name in models_to_test:
        try:
            # Try a minimal request to check availability
            client.messages.create(
                model=model_id,
                max_tokens=1,
                messages=[{"role": "user", "content": "test"}]
            )
            available.append((model_id, model_name))
        except APIError as e:
            if e.status_code == 404:
                unavailable.append((model_id, model_name))
        except:
            pass

    if available:
        print("\n📋 Available Models:")
        for model_id, model_name in available:
            print(f"   ✅ {model_name}")
            print(f"      ID: {model_id}")

    if unavailable:
        print("\n🚫 Unavailable Models:")
        for model_id, model_name in unavailable:
            print(f"   ❌ {model_name}")
            print(f"      ID: {model_id}")

    return available, unavailable

def print_summary(opus_works, sonnet_works, available_models):
    """Print summary and recommendations"""
    print("\n" + "="*60)
    print("📊 Summary")
    print("="*60)

    if sonnet_works:
        print("\n✅ Great! Your API key has access to Claude 3.5 Sonnet!")
        print("   You can use all Claude models including the latest.")
        print("\n💡 Next steps:")
        print("   1. Update your app configuration to use claude-3-5-sonnet-20241022")
        print("   2. Enjoy 2x longer responses (8192 vs 4096 tokens)")
        print("   3. Benefit from better performance at lower cost")

    elif opus_works:
        print("\n⚠️  Your API key works but doesn't have Claude 3.5 Sonnet access")
        print("\n💡 To get Claude 3.5 Sonnet access:")
        print("   1. Go to https://console.anthropic.com/settings/billing")
        print("   2. Add a payment method (credit card)")
        print("   3. Once billing is active, all models become available")
        print("\n💰 Pricing comparison:")
        print("   • Claude 3.5 Sonnet: $3/$15 per million tokens (input/output)")
        print("   • Claude 3 Opus: $15/$75 per million tokens")
        print("   → Sonnet is 5x cheaper and more capable!")

    else:
        print("\n❌ API key authentication failed")
        print("\n💡 Troubleshooting steps:")
        print("   1. Check your API key at https://console.anthropic.com/api-keys")
        print("   2. Make sure it starts with 'sk-ant-'")
        print("   3. Ensure the key is active and not revoked")
        print("   4. Try generating a new API key")

def main():
    """Main test function"""
    print_header()

    # Test 1: API Key
    api_key = test_api_key()
    if not api_key:
        print("\n⛔ Cannot proceed without API key")
        return 1

    # Initialize client
    try:
        client = Anthropic(api_key=api_key)
    except Exception as e:
        print(f"\n❌ Failed to initialize client: {e}")
        return 1

    # Test 2: Claude 3 Opus (baseline)
    opus_works = test_claude_opus(client)

    # Test 3: Claude 3.5 Sonnet
    sonnet_works = test_claude_sonnet(client)

    # Test 4: Available models
    available, unavailable = test_available_models(client)

    # Summary
    print_summary(opus_works, sonnet_works, available)

    return 0 if sonnet_works else 1

if __name__ == "__main__":
    sys.exit(main())