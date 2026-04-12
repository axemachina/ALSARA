#!/usr/bin/env python3
"""
Test individual components without full app startup
"""

import asyncio
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

async def test_imports():
    """Test that all modules can be imported"""
    print("📦 Testing imports...")
    
    try:
        import anthropic
        print("✅ anthropic imported")
        
        import gradio
        print("✅ gradio imported")
        
        from shared.config import config
        print("✅ shared.config imported")
        
        # Test main app import (but don't run it)
        import als_agent_app
        print("✅ als_agent_app imported")
        
        return True
        
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False

async def test_config():
    """Test configuration loading"""
    print("\n⚙️  Testing configuration...")
    
    try:
        from shared.config import config
        
        print(f"Anthropic model: {config.anthropic_model}")
        print(f"Gradio port: {config.gradio_port}")
        print(f"API key set: {'Yes' if config.anthropic_api_key and config.anthropic_api_key != 'your_anthropic_api_key_here' else 'No'}")
        
        return True
        
    except Exception as e:
        print(f"❌ Config test failed: {e}")
        return False

async def test_mcp_server_files():
    """Test that MCP server files exist and can be imported"""
    print("\n🖥️  Testing MCP server files...")
    
    try:
        servers_dir = Path("servers")
        expected_servers = [
            "pubmed_server.py",
            "biorxiv_server.py", 
            "clinicaltrials_server.py",
            "fetch_server.py"
        ]
        
        for server_file in expected_servers:
            server_path = servers_dir / server_file
            if server_path.exists():
                print(f"✅ {server_file} exists")
            else:
                print(f"❌ {server_file} missing")
                return False
        
        # Test basic import (without running servers)
        import servers.pubmed_server
        print("✅ pubmed_server can be imported")
        
        return True
        
    except Exception as e:
        print(f"❌ MCP server test failed: {e}")
        return False

async def main():
    """Run component tests"""
    print("🧪 Testing Individual Components\n")
    
    tests = [
        test_imports,
        test_config,
        test_mcp_server_files
    ]
    
    results = []
    for test in tests:
        result = await test()
        results.append(result)
    
    print(f"\n📊 Component Test Results:")
    print(f"Passed: {sum(results)}/{len(results)}")
    
    if all(results):
        print("🎉 All component tests passed!")
    else:
        print("⚠️  Some component tests failed.")

if __name__ == "__main__":
    asyncio.run(main())