#!/usr/bin/env python3
"""
Test script for ElevenLabs MCP server
Tests voice capabilities for ALS research accessibility
"""

import asyncio
import json
import os
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_elevenlabs_server():
    """Test ElevenLabs MCP server functionality"""

    server_path = Path(__file__).parent / "servers" / "elevenlabs_server.py"

    # Create server parameters
    import sys
    server_params = StdioServerParameters(
        command=sys.executable,  # Use the current Python executable
        args=[str(server_path)]
    )

    # Test with mock API key if not set
    if not os.getenv("ELEVENLABS_API_KEY"):
        print("⚠️ ELEVENLABS_API_KEY not set - tests will show API key errors")
        print("This is expected behavior when API key is not configured\n")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:

            # Initialize the session
            await session.initialize()

            # Get available tools
            tools = await session.list_tools()

            print("=" * 60)
            print("🔊 ElevenLabs MCP Server Test")
            print("=" * 60)
            print(f"\n✅ Server initialized successfully")
            print(f"📦 Found {len(tools.tools)} tools:")
            for tool in tools.tools:
                print(f"  - {tool.name}: {tool.description[:60]}...")

            # Test 1: List available voices
            print("\n" + "=" * 60)
            print("Test 1: List Available Voices")
            print("=" * 60)

            result = await session.call_tool(
                "list_voices",
                arguments={}
            )

            print("Result:")
            try:
                data = json.loads(result.content[0].text)
                if data.get("status") == "error":
                    print(f"  ❌ Error: {data.get('error')}")
                    print(f"     {data.get('message')}")
                else:
                    print(f"  ✅ Found voices")
                    if "recommended_voices" in data:
                        print(f"     Recommended: {len(data['recommended_voices'])} voices")
                    if "other_voices" in data:
                        print(f"     Other: {len(data['other_voices'])} voices")
            except:
                print(f"  Result: {result.content[0].text[:200]}...")

            # Test 2: Text-to-Speech (with sample ALS research text)
            print("\n" + "=" * 60)
            print("Test 2: Text-to-Speech for ALS Research")
            print("=" * 60)

            research_text = """
            Recent findings show that TDP-43 protein aggregation plays a crucial role
            in ALS pathology. The C9orf72 hexanucleotide repeat expansion remains
            the most common genetic cause of familial ALS.
            """

            result = await session.call_tool(
                "text_to_speech",
                arguments={
                    "text": research_text,
                    "speed": 0.9  # Slightly slower for clarity
                }
            )

            print("Result:")
            try:
                data = json.loads(result.content[0].text)
                if data.get("status") == "error":
                    print(f"  ❌ Error: {data.get('error')}")
                    print(f"     {data.get('message')}")
                else:
                    print(f"  ✅ Audio generated successfully")
                    print(f"     Format: {data.get('format')}")
                    print(f"     Duration estimate: ~{data.get('duration_estimate', 0):.1f} seconds")
                    print(f"     Audio data size: {len(data.get('audio_base64', ''))} chars (base64)")
            except:
                print(f"  Result: {result.content[0].text[:200]}...")

            # Test 3: Create Audio Summary
            print("\n" + "=" * 60)
            print("Test 3: Create Audio Summary")
            print("=" * 60)

            complex_content = """
            Amyotrophic lateral sclerosis (ALS) is characterized by progressive
            degeneration of motor neurons. Recent phase 2 trials of tofersen showed
            promising results in SOD1-ALS patients, with reduced neurofilament levels
            indicating decreased neurodegeneration. The drug works through antisense
            oligonucleotide technology, targeting the mutant SOD1 mRNA for degradation.
            """

            result = await session.call_tool(
                "create_audio_summary",
                arguments={
                    "content": complex_content,
                    "summary_type": "patient-friendly",
                    "max_duration": 30
                }
            )

            print("Result:")
            try:
                data = json.loads(result.content[0].text)
                if data.get("status") == "error":
                    print(f"  ❌ Error: {data.get('error')}")
                    print(f"     {data.get('message')}")
                else:
                    print(f"  ✅ Audio summary created")
                    print(f"     Type: {data.get('summary_type')}")
                    print(f"     Word count: {data.get('word_count')}")
                    print(f"     Text summary: {data.get('text_summary', '')[:100]}...")
            except:
                print(f"  Result: {result.content[0].text[:200]}...")

            # Test 4: Medical Pronunciation Guide
            print("\n" + "=" * 60)
            print("Test 4: Medical Pronunciation Guide")
            print("=" * 60)

            medical_terms = [
                "amyotrophic",
                "sclerosis",
                "neurodegeneration",
                "oligonucleotide",
                "C9orf72"
            ]

            result = await session.call_tool(
                "generate_medical_pronunciation",
                arguments={
                    "medical_terms": medical_terms,
                    "include_audio": False  # Just phonetic for testing
                }
            )

            print("Result:")
            try:
                data = json.loads(result.content[0].text)
                if data.get("status") == "error":
                    print(f"  ❌ Error: {data.get('error')}")
                    print(f"     {data.get('message')}")
                else:
                    print(f"  ✅ Pronunciation guide generated")
                    pronunciations = data.get("pronunciations", [])
                    for p in pronunciations[:3]:
                        print(f"     {p['term']}: {p['phonetic']}")
            except:
                print(f"  Result: {result.content[0].text[:200]}...")

            print("\n" + "=" * 60)
            print("✅ All tests completed!")
            print("=" * 60)

            # Summary
            print("\n📊 Test Summary:")
            print("  - Server initialization: ✅")
            print("  - Tool discovery: ✅")
            print("  - Voice listing: Tested")
            print("  - Text-to-speech: Tested")
            print("  - Audio summaries: Tested")
            print("  - Pronunciation guide: Tested")

            if not os.getenv("ELEVENLABS_API_KEY"):
                print("\n⚠️ Note: Set ELEVENLABS_API_KEY to test actual audio generation")

if __name__ == "__main__":
    asyncio.run(test_elevenlabs_server())