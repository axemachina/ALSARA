#!/usr/bin/env python3
"""
Test that phase markers are properly formatted on new lines
"""

import re

def filter_internal_tags(text):
    """Apply the same filtering logic as the main app"""

    # Remove internal tags
    text = re.sub(r'</?(?:thinking|reflection|search_quality|query_analysis)>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(result|answer)>', '', text)

    # Fix phase formatting - ensure consistent formatting
    # First normalize any existing phase markers to be on their own line
    phase_patterns = [
        # First, ensure the markers are on new lines (if not already)
        (r'(?<!\n)(\*\*🎯\s*PLANNING:\*\*)', r'\n\1'),
        (r'(?<!\n)(\*\*🔧\s*EXECUTING:\*\*)', r'\n\1'),
        (r'(?<!\n)(\*\*🤔\s*REFLECTING:\*\*)', r'\n\1'),
        (r'(?<!\n)(\*\*✅\s*SYNTHESIS:\*\*)', r'\n\1'),
        (r'(?<!\n)(\*\*✅\s*ANSWER:\*\*)', r'\n\1'),
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

def check_phase_on_newline(text, phase_marker):
    """Check if a phase marker appears on its own line"""
    # Look for the marker and check what comes before it
    import re

    # Check if marker exists
    if phase_marker not in text:
        return None, "Marker not found"

    # Find all occurrences
    pattern = re.compile(re.escape(phase_marker))
    matches = list(pattern.finditer(text))

    issues = []
    for match in matches:
        start_pos = match.start()

        # Check what comes before the marker
        if start_pos > 0:
            prev_char = text[start_pos - 1]
            if prev_char != '\n':
                # Find context (10 chars before and after)
                context_start = max(0, start_pos - 10)
                context_end = min(len(text), match.end() + 10)
                context = text[context_start:context_end]
                issues.append(f"Not on new line. Context: ...{repr(context)}...")

    if issues:
        return False, issues
    return True, "OK - on new line"

# Test cases
test_cases = [
    # Case 1: Inline markers (problematic)
    ("Some text **🎯 PLANNING:** here is the plan", "Inline marker - should be fixed"),

    # Case 2: Already on new line (good)
    ("Some text\n**🎯 PLANNING:** here is the plan", "Already on new line"),

    # Case 3: Multiple markers inline
    ("Text before **🎯 PLANNING:** plan text **🔧 EXECUTING:** execute text", "Multiple inline markers"),

    # Case 4: Real example from user's problematic output
    ("🔍 **Search Results:** The search results did not provide... **🎯 PLANNING:** To answer the user's question", "Real problematic case"),
]

print("=" * 70)
print("TESTING PHASE MARKER FORMATTING")
print("=" * 70)

phase_markers = [
    "**🎯 PLANNING:**",
    "**🔧 EXECUTING:**",
    "**🤔 REFLECTING:**",
    "**✅ SYNTHESIS:**"
]

for i, (test_text, description) in enumerate(test_cases, 1):
    print(f"\nTest Case {i}: {description}")
    print("-" * 50)

    # Apply filtering
    filtered = filter_internal_tags(test_text)

    print(f"Original text ({len(test_text)} chars):")
    print(f"  {repr(test_text[:100])}...")
    print(f"\nFiltered text ({len(filtered)} chars):")
    print(f"  {repr(filtered[:100])}...")

    # Check each phase marker
    print("\nPhase marker checks:")
    for marker in phase_markers:
        if marker in filtered:
            is_ok, info = check_phase_on_newline(filtered, marker)
            if is_ok:
                print(f"  ✅ {marker[:20]}... - {info}")
            else:
                print(f"  ❌ {marker[:20]}... - Issues: {info}")
        else:
            print(f"  ⚪ {marker[:20]}... - Not present")

print("\n" + "=" * 70)
print("FORMATTING VERIFICATION")
print("=" * 70)

# Test the actual problematic response
problematic = """🔍 **Search Results:** The search results did not provide any relevant information on psilocybin trials and use in therapy for ALS. **🎯 PLANNING:** To answer the user's question about psilocybin trials and use in therapy for ALS, I will first search the PubMed database. **🔧 EXECUTING:** 1. Search PubMed for peer-reviewed research papers. **🤔 REFLECTING:** 1. Do I have sufficient high-quality information? **✅ SYNTHESIS:** Based on the available information, there is limited research."""

print("Testing problematic response:")
filtered = filter_internal_tags(problematic)
print("\nFiltered output:")
print(filtered)

# Verify each marker is on a new line
print("\n" + "=" * 70)
lines = filtered.split('\n')
for i, line in enumerate(lines, 1):
    for marker in phase_markers:
        if marker in line:
            # Check if marker is at the start of the line
            if line.strip().startswith(marker):
                print(f"✅ Line {i}: {marker} is properly at line start")
            else:
                print(f"❌ Line {i}: {marker} is NOT at line start")
                print(f"   Full line: {repr(line[:60])}...")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print("""
The formatting patterns have been updated to:
1. Check if phase markers are NOT preceded by a newline (?<!\\n)
2. Add a newline before them if needed
3. Ensure a newline after them as well
4. Clean up any excessive whitespace

This ensures all phase markers appear on their own lines.
""")