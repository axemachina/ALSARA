#!/usr/bin/env python3
"""
Minimal test that doesn't require API keys or external services
"""

import sys
from pathlib import Path

def test_syntax():
    """Test Python syntax of all files"""
    print("📝 Testing Python syntax...")
    
    files_to_check = [
        "als_agent_app.py",
        "shared/config.py",
        "shared/cache.py",
        "shared/utils.py",
        "servers/pubmed_server.py",
        "servers/biorxiv_server.py", 
        "servers/clinicaltrials_server.py",
        "servers/fetch_server.py"
    ]
    
    for file_path in files_to_check:
        try:
            with open(file_path, 'r') as f:
                code = f.read()
            
            compile(code, file_path, 'exec')
            print(f"✅ {file_path} - syntax OK")
            
        except FileNotFoundError:
            print(f"⚠️  {file_path} - file not found")
        except SyntaxError as e:
            print(f"❌ {file_path} - syntax error: {e}")
            return False
        except Exception as e:
            print(f"❌ {file_path} - error: {e}")
            return False
    
    return True

def test_requirements():
    """Check that requirements.txt has correct entries"""
    print("\n📋 Testing requirements.txt...")
    
    try:
        with open("requirements.txt", 'r') as f:
            requirements = f.read()
        
        expected_packages = [
            "anthropic",
            "gradio", 
            "mcp",
            "httpx"
        ]
        
        for package in expected_packages:
            if package in requirements:
                print(f"✅ {package} found in requirements.txt")
            else:
                print(f"❌ {package} missing from requirements.txt")
                return False
        
        # Check that openai is NOT in requirements
        if "openai" in requirements and "anthropic" in requirements:
            print("⚠️  Both openai and anthropic in requirements - might want to remove openai")
        
        return True
        
    except FileNotFoundError:
        print("❌ requirements.txt not found")
        return False

def test_env_example():
    """Check .env.example file"""
    print("\n🔧 Testing .env.example...")
    
    try:
        with open(".env.example", 'r') as f:
            env_content = f.read()
        
        if "ANTHROPIC_API_KEY" in env_content:
            print("✅ ANTHROPIC_API_KEY found in .env.example")
        else:
            print("❌ ANTHROPIC_API_KEY missing from .env.example")
            return False
            
        if "OPENAI_API_KEY" in env_content:
            print("⚠️  OPENAI_API_KEY still in .env.example - should be removed")
        
        return True
        
    except FileNotFoundError:
        print("❌ .env.example not found")
        return False

def main():
    """Run minimal tests that don't require external services"""
    print("🔍 Running Minimal Tests (No API Keys Required)\n")
    
    tests = [
        test_syntax,
        test_requirements, 
        test_env_example
    ]
    
    results = []
    for test in tests:
        result = test()
        results.append(result)
    
    print(f"\n📊 Minimal Test Results:")
    print(f"Passed: {sum(results)}/{len(results)}")
    
    if all(results):
        print("🎉 All minimal tests passed!")
        print("\nNext steps:")
        print("1. Set ANTHROPIC_API_KEY in .env file")
        print("2. Run: python3 test_claude_integration.py")
        print("3. Run: python3 test_components.py")
        print("4. Run: python3 als_agent_app.py (for full app)")
    else:
        print("⚠️  Some minimal tests failed. Fix these issues first.")

if __name__ == "__main__":
    main()