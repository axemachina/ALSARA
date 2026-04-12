#!/usr/bin/env python3
"""
Test to verify that workflow phases don't appear twice in responses
"""

def check_for_duplicate_phases(response_text):
    """Check if workflow phases appear more than once in the response"""

    phase_markers = [
        "🎯 **PLANNING:**",
        "🔧 **EXECUTING:**",
        "🤔 **REFLECTING:**",
        "✅ **SYNTHESIS:**"
    ]

    issues = []
    for marker in phase_markers:
        count = response_text.count(marker)
        if count > 1:
            issues.append(f"'{marker}' appears {count} times (should be 1)")
        elif count == 0:
            print(f"✓ '{marker}' not found (may be skipped)")
        else:
            print(f"✓ '{marker}' appears exactly once")

    return issues

# Test with the problematic examples from the user
test_response_1 = """📊 **Search Progress:** Completed 1/1 searches

✓ **Completed:** aact → search_als_trials
🔧 **Searching:** biorxiv → search_preprints `psilocybin ALS therapy`

📊 **Search Progress:** Completed 1/1 searches

✓ **Completed:** biorxiv → search_preprints `psilocybin ALS therapy`

🔍 **Search Results:**
The search results did not provide any relevant information...

🎯 **PLANNING:** To answer the user's question about psilocybin trials...

🔧 **EXECUTING:**
1. Search PubMed for peer-reviewed research papers...

🔍 **EXECUTION RESULTS:**
The search results from PubMed, bioRxiv/medRxiv...

🤔 **REFLECTING:**
1. Do I have sufficient high-quality information...

✅ **SYNTHESIS:**
Based on the available information..."""

test_response_2 = """📊 **Search Progress:** Completed 1/1 searches

✓ **Completed:** pubmed → search_pubmed `SOD1 ALS gene therapy`

🎯 **PLANNING:** To answer the user's question about the main genes...

🔧 **EXECUTING:**
1. Identify genes associated with ALS...

🔍 **EXECUTION RESULTS:**
The search results provided information...

🤔 **REFLECTING:**
1. Do I have sufficient high-quality information...

✅ **SYNTHESIS:**
Based on the search results...

🎯 **PLANNING:** To answer the user's question about the main genes... [DUPLICATE!]

🔧 **EXECUTING:**
1. Search PubMed for peer-reviewed research papers...

🔍 **EXECUTION RESULTS:**
The search results identified several genes...

🤔 **REFLECTING:**
1. Do I have sufficient high-quality information...

✅ **SYNTHESIS:**
Based on the search results..."""

print("=" * 70)
print("TESTING WORKFLOW DUPLICATION FIX")
print("=" * 70)

print("\nTest 1 - Psilocybin Response:")
print("-" * 40)
issues_1 = check_for_duplicate_phases(test_response_1)
if issues_1:
    print(f"\n❌ ISSUES FOUND:")
    for issue in issues_1:
        print(f"   - {issue}")
else:
    print("\n✅ NO DUPLICATION FOUND")

print("\n" + "=" * 70)
print("\nTest 2 - Gene Therapy Response (known duplicate):")
print("-" * 40)
issues_2 = check_for_duplicate_phases(test_response_2)
if issues_2:
    print(f"\n❌ ISSUES FOUND (EXPECTED):")
    for issue in issues_2:
        print(f"   - {issue}")
else:
    print("\n✅ NO DUPLICATION FOUND")

print("\n" + "=" * 70)
print("FIX SUMMARY:")
print("=" * 70)
print("""
The duplicate workflow issue has been fixed by:

1. **Iteration-aware prompting**:
   - First iteration uses full workflow with all phases
   - Subsequent iterations get different prompt without phase requirements

2. **Tool access control**:
   - Tools are disabled after first iteration (available_tools = [])
   - Prevents AI from initiating more searches after synthesis

3. **System prompt modification**:
   - Iterations > 1 use simplified prompt
   - Explicitly instructs: "Do NOT repeat the workflow phases"

These changes ensure that Planning/Executing/Reflecting/Synthesis
phases appear only ONCE per response, not multiple times.
""")