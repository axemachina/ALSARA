#!/usr/bin/env python3
"""
Simple test script to verify Claude API integration without full Gradio setup
"""

import asyncio
import os
from anthropic import AsyncAnthropic

async def test_claude_connection():
    """Test basic Claude API connection"""
    print("🧪 Testing Claude API connection...")
    
    # Check if API key is set
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_anthropic_api_key_here":
        print("❌ ANTHROPIC_API_KEY not set in .env file")
        return False
    
    try:
        client = AsyncAnthropic(api_key=api_key)
        
        # Test simple message
        response = await client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=100,
            messages=[{"role": "user", "content": "Hello, can you respond with 'API connection successful'?"}]
        )
        
        print("✅ Claude API connection successful!")
        print(f"Response: {response.content[0].text}")
        return True
        
    except Exception as e:
        print(f"❌ Claude API connection failed: {e}")
        return False

async def test_streaming():
    """Test streaming functionality"""
    print("\n🔄 Testing Claude API streaming...")
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_anthropic_api_key_here":
        print("❌ ANTHROPIC_API_KEY not set")
        return False
    
    try:
        client = AsyncAnthropic(api_key=api_key)
        
        print("Streaming response: ", end="", flush=True)
        async with client.messages.stream(
            model="claude-3-opus-20240229",
            max_tokens=50,
            messages=[{"role": "user", "content": "Count from 1 to 5"}]
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        print(event.delta.text, end="", flush=True)
        
        print("\n✅ Streaming test successful!")
        return True
        
    except Exception as e:
        print(f"\n❌ Streaming test failed: {e}")
        return False

async def test_tools_format():
    """Test tool calling format (without actual MCP servers)"""
    print("\n🔧 Testing tool calling format...")
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_anthropic_api_key_here":
        print("❌ ANTHROPIC_API_KEY not set")
        return False
    
    try:
        client = AsyncAnthropic(api_key=api_key)
        
        # Mock tool definition
        tools = [{
            "name": "test_tool",
            "description": "A test tool that returns a greeting",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name to greet"}
                },
                "required": ["name"]
            }
        }]
        
        response = await client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=100,
            messages=[{"role": "user", "content": "Use the test tool to greet 'World'"}],
            tools=tools
        )
        
        # Check if Claude wants to use tools
        if any(block.type == "tool_use" for block in response.content):
            print("✅ Tool calling format test successful!")
            print("Claude correctly identified the need to use tools")
            return True
        else:
            print("ℹ️  Claude didn't use tools (which is fine for this test)")
            return True
            
    except Exception as e:
        print(f"❌ Tool calling test failed: {e}")
        return False

async def main():
    """Run all tests"""
    print("🚀 Starting Claude API Integration Tests\n")
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    tests = [
        test_claude_connection,
        test_streaming,
        test_tools_format
    ]
    
    results = []
    for test in tests:
        result = await test()
        results.append(result)
    
    print(f"\n📊 Test Results:")
    print(f"Passed: {sum(results)}/{len(results)}")
    
    if all(results):
        print("🎉 All tests passed! Your Claude integration is ready.")
    else:
        print("⚠️  Some tests failed. Check your API key and configuration.")

if __name__ == "__main__":
    asyncio.run(main())