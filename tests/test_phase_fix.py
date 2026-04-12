#!/usr/bin/env python3
"""
Test the phase marker formatting fixes
"""

import re

def filter_internal_tags(text):
    """Apply the same filtering logic as the main app"""

    # Remove internal tags
    text = re.sub(r'</?(?:thinking|reflection|search_quality|query_analysis)>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(result|answer)>', '', text)

    # Fix phase formatting - ensure consistent formatting
    phase_patterns = [
        # Fix incorrect formats (missing asterisks) first
        (r'(?<!\*)🎯\s*PLANNING:(?!\*)', r'**🎯 PLANNING:**'),
        (r'(?<!\*)🔧\s*EXECUTING:(?!\*)', r'**🔧 EXECUTING:**'),
        (r'(?<!\*)🤔\s*REFLECTING:(?!\*)', r'**🤔 REFLECTING:**'),
        (r'(?<!\*)✅\s*SYNTHESIS:(?!\*)', r'**✅ SYNTHESIS:**'),
        (r'(?<!\*)✅\s*ANSWER:(?!\*)', r'**✅ ANSWER:**'),

        # Then ensure the markers are on new lines (if not already)
        (r'(?<!\n)(\*\*🎯\s*PLANNING:\*\*)', r'\n\n\1'),
        (r'(?<!\n)(\*\*🔧\s*EXECUTING:\*\*)', r'\n\n\1'),
        (r'(?<!\n)(\*\*🤔\s*REFLECTING:\*\*)', r'\n\n\1'),
        (r'(?<!\n)(\*\*✅\s*SYNTHESIS:\*\*)', r'\n\n\1'),
        (r'(?<!\n)(\*\*✅\s*ANSWER:\*\*)', r'\n\n\1'),

        # Then add spacing after them
        (r'(\*\*🎯\s*PLANNING:\*\*)', r'\1\n'),
        (r'(\*\*🔧\s*EXECUTING:\*\*)', r'\1\n'),
        (r'(\*\*🤔\s*REFLECTING:\*\*)', r'\1\n'),
        (r'(\*\*✅\s*SYNTHESIS:\*\*)', r'\1\n'),
        (r'(\*\*✅\s*ANSWER:\*\*)', r'\1\n'),
    ]

    for pattern, replacement in phase_patterns:
        text = re.sub(pattern, replacement, text)

    # Clean up excessive whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    text = re.sub(r'^\n+', '', text)
    text = re.sub(r'\n+$', '\n', text)

    return text.strip()

# Test with the problematic example from the user
problematic_text = """📊 **Search Progress:** Completed 1/1 searches

✓ **Completed:** pubmed → search_pubmed `Omega-3 and omega-6 fatty acids in ALS treatment`🤔 REFLECTING: Based on the search results, it appears that there are some relevant studies related to the role of Omega-3 and omega-6 fatty acids in ALS treatment. However, the information provided is limited to brief summaries and abstracts of research papers. To answer comprehensively, it would be beneficial to investigate further and gather more detailed information about the specific studies, their methodologies, and findings.

There are important aspects that need more investigation, such as the specific types and amounts of Omega-3 and omega-6 fatty acids that have been studied, the duration of the studies, and the population samples used. Refining search terms or trying different databases may help to uncover more relevant information and provide a more comprehensive understanding of the topic.

Therefore, I will refine my search terms and try different databases to gather more information before proceeding to synthesis.

🎯 PLANNING: To address the role of Omega-3 and omega-6 fatty acids in ALS treatment, I will search PubMed and bioRxiv/medRxiv for peer-reviewed research papers and preprints.

🔧 EXECUTING: I have searched PubMed and bioRxiv/medRxiv using the planned search terms.

🤔 REFLECTING: Upon evaluating the search results, I have found relevant studies.

✅ SYNTHESIS: Based on the available information..."""

print("=" * 70)
print("TESTING PHASE MARKER FORMATTING FIXES")
print("=" * 70)

print("\n### Original problematic text issues:")
print("-" * 40)

# Check for issues in original
issues = []

# Check for missing asterisks
if "🤔 REFLECTING:" in problematic_text and "**🤔 REFLECTING:**" not in problematic_text:
    issues.append("❌ Found 'REFLECTING:' without asterisks")

# Check for inline markers
lines = problematic_text.split('\n')
for line in lines:
    if '🤔 REFLECTING:' in line and not line.strip().startswith('🤔 REFLECTING:'):
        issues.append(f"❌ 'REFLECTING:' not at start of line: {line[:60]}...")
    if '🎯 PLANNING:' in line and not line.strip().startswith('🎯 PLANNING:') and not line.strip().startswith('**🎯 PLANNING:**'):
        issues.append(f"❌ 'PLANNING:' not at start of line: {line[:60]}...")

# Check for duplicate phases
phase_markers = ["PLANNING:", "EXECUTING:", "REFLECTING:", "SYNTHESIS:"]
for marker in phase_markers:
    count = problematic_text.count(marker)
    if count > 1:
        issues.append(f"❌ '{marker}' appears {count} times (should be 1)")

print("Issues found:")
for issue in issues:
    print(f"  {issue}")

print("\n### After applying filters:")
print("-" * 40)

# Apply filtering
filtered = filter_internal_tags(problematic_text)

# Check if issues are fixed
print("\nFiltered text (first 500 chars):")
print(filtered[:500])
print("...")

print("\n### Verification:")
print("-" * 40)

# Verify each phase marker is correctly formatted
correct_markers = [
    "**🎯 PLANNING:**",
    "**🔧 EXECUTING:**",
    "**🤔 REFLECTING:**",
    "**✅ SYNTHESIS:**"
]

for marker in correct_markers:
    count = filtered.count(marker)
    if count == 1:
        print(f"✅ {marker} appears exactly once")
        # Check if on its own line
        marker_pos = filtered.find(marker)
        if marker_pos > 0:
            # Check character before
            char_before = filtered[marker_pos - 1]
            if char_before == '\n':
                print(f"   ✅ On its own line")
            else:
                print(f"   ❌ Not on its own line (preceded by: {repr(char_before)})")
    elif count == 0:
        print(f"⚪ {marker} not found")
    else:
        print(f"❌ {marker} appears {count} times")

# Check for incorrect formats
incorrect_formats = ["🤔 REFLECTING:", "🎯 PLANNING:", "🔧 EXECUTING:", "✅ SYNTHESIS:"]
for wrong in incorrect_formats:
    if wrong in filtered and f"**{wrong}**" not in filtered:
        print(f"❌ Still contains incorrect format: {wrong}")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print("""
The filtering patterns have been enhanced to:
1. Fix missing asterisks (🤔 REFLECTING: → **🤔 REFLECTING:**)
2. Ensure markers appear on new lines (add \\n\\n before)
3. Add spacing after markers
4. Clean up excessive whitespace

The system prompt has also been updated to:
1. Explicitly require asterisks for bold formatting
2. Emphasize markers must be on new lines
3. Clarify each phase should appear EXACTLY ONCE
4. Show examples of correct vs incorrect formats
""")