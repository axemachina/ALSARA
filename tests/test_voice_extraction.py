#!/usr/bin/env python3
"""
Test and debug the voice synthesis text extraction
"""

import re

def extract_synthesis_only(text: str) -> str:
    """Extract only the synthesis part, excluding references and additional info."""

    # Precise cutoff patterns - focus on clear section headers
    cutoff_patterns = [
        # Clear section headers with colons - most reliable indicators
        r'\n\s*(?:For (?:more|additional|further) (?:information|details|reading))\s*[:：]',
        r'\n\s*(?:References?|Sources?|Citations?|Bibliography)\s*[:：]',
        r'\n\s*(?:Additional (?:resources?|information|reading|materials?))\s*[:：]',

        # Markdown headers for reference sections (must be on their own line)
        r'\n\s*#{1,6}\s+(?:References?|Sources?|Citations?|Bibliography)\s*$',
        r'\n\s*#{1,6}\s+(?:For (?:more|additional|further) (?:information|details))\s*$',
        r'\n\s*#{1,6}\s+(?:Additional (?:Resources?|Information|Reading))\s*$',
        r'\n\s*#{1,6}\s+(?:Further Reading|Learn More)\s*$',

        # Bold headers for reference sections (with newline after)
        r'\n\s*\*\*(?:References?|Sources?|Citations?)\*\*\s*[:：]?\s*\n',
        r'\n\s*\*\*(?:For (?:more|additional) information)\*\*\s*[:：]?\s*\n',

        # Phrases that clearly introduce reference lists
        r'\n\s*(?:Here are|Below are|The following are)\s+(?:the |some |additional )?(?:references|sources|citations|papers cited|studies referenced)',
        r'\n\s*(?:References used|Sources consulted|Papers cited|Studies referenced)\s*[:：]',
        r'\n\s*(?:Key|Recent|Selected|Relevant)\s+(?:references?|publications?|citations)\s*[:：]',

        # Clinical trials section headers with clear separators
        r'\n\s*(?:Clinical trials?|Studies|Research papers?)\s+(?:referenced|cited|mentioned|used)\s*[:：]',
        r'\n\s*(?:AACT|ClinicalTrials\.gov)\s+(?:database entries?|trial IDs?|references?)\s*[:：]',

        # Web link sections
        r'\n\s*(?:Links?|URLs?|Websites?|Web resources?)\s*[:：]',
        r'\n\s*(?:Visit|See|Check out)\s+(?:these|the following)\s+(?:links?|websites?|resources?)',
        r'\n\s*(?:Learn more|Read more|Find out more|Get more information)\s+(?:at|here|below)\s*[:：]',

        # Academic citation lists (only when preceded by double newline or clear separator)
        r'\n\n\s*\d+\.\s+[A-Z][a-z]+.*?et al\..*?(?:PMID|DOI|Journal)',
        r'\n\n\s*\[1\]\s+[A-Z][a-z]+.*?(?:et al\.|https?://)',

        # Direct ID listings (clearly separate from main content)
        r'\n\s*(?:PMID|DOI|NCT)\s*[:：]\s*\d+',
        r'\n\s*(?:Trial IDs?|Study IDs?)\s*[:：]',

        # Footer sections
        r'\n\s*(?:Note|Notes|Disclaimer|Important notice)\s*[:：]',
        r'\n\s*(?:Data (?:source|from)|Database|Repository)\s*[:：]',
        r'\n\s*(?:Retrieved from|Accessed via|Source database)\s*[:：]',
    ]

    # Try each pattern and find the earliest match
    synthesis_text = text
    earliest_pos = len(text)
    matched_pattern = None

    for pattern in cutoff_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match and match.start() < earliest_pos:
            earliest_pos = match.start()
            matched_pattern = pattern

    if earliest_pos < len(text):
        synthesis_text = text[:earliest_pos].rstrip()
        print(f"✂️ Cut off at pattern: {matched_pattern}")
        print(f"   Position: {earliest_pos}/{len(text)} chars")
    else:
        print("⚠️ No cutoff pattern matched - using full text")

    return synthesis_text

# Test with a sample response that includes references
test_response = """
Recent breakthrough research in ALS has identified several promising therapeutic approaches:

1. **Gene therapy targeting SOD1 mutations**: Tofersen has shown significant promise in slowing disease progression for patients with SOD1 mutations. The VALOR trial demonstrated a 55% reduction in neurofilament light chain levels, a biomarker of neurodegeneration.

2. **TDP-43 pathology biomarkers**: New research indicates that TDP-43 pathology can be detected in skin biopsies up to 26 years before symptom onset, potentially revolutionizing early detection and treatment strategies.

3. **Combination therapies**: The HEALEY ALS Platform Trial is testing multiple promising therapies simultaneously, including pridopidine and verdiperstat, significantly accelerating the drug development process.

4. **Stem cell approaches**: Recent trials using mesenchymal stem cells have shown potential in modulating the immune response and providing neuroprotection, with some patients showing slowed functional decline.

5. **Antisense oligonucleotides (ASOs)**: Beyond tofersen, new ASOs targeting C9orf72 and FUS mutations are entering clinical trials, offering hope for genetic forms of ALS.

The field is advancing rapidly with over 50 active clinical trials currently recruiting patients worldwide.

For more information:

1. Paganoni S, et al. Trial of Sodium Phenylbutyrate-Taurursodiol for Amyotrophic Lateral Sclerosis. NEJM 2020. PMID: 32877582
2. Miller T, et al. Phase 1-2 Trial of Antisense Oligonucleotide Tofersen for SOD1 ALS. NEJM 2020. PMID: 32640130
3. Berry JD, et al. Design and initial results of HEALEY ALS Platform Trial. Ann Clin Transl Neurol 2020. PMID: 32888362

Clinical trials referenced:
- NCT04856982: HEALEY ALS Platform Trial
- NCT03626012: Tofersen VALOR trial
- NCT04931862: C9orf72 ASO trial

Additional resources:
- ALS Association: www.als.org
- Northeast ALS Consortium: www.neals.org
- ClinicalTrials.gov: Search for "ALS" to find all active trials

Note: Always consult with your healthcare provider before considering participation in clinical trials.
"""

print("=" * 70)
print("TESTING VOICE SYNTHESIS TEXT EXTRACTION")
print("=" * 70)

# Extract synthesis
synthesis = extract_synthesis_only(test_response)

print(f"\nOriginal length: {len(test_response)} characters")
print(f"Synthesis length: {len(synthesis)} characters")
print(f"Reduction: {100 - (len(synthesis)/len(test_response)*100):.1f}%")

print("\n" + "=" * 70)
print("EXTRACTED SYNTHESIS TEXT:")
print("=" * 70)
print(synthesis)

print("\n" + "=" * 70)
print("REMOVED SECTION (first 200 chars):")
print("=" * 70)
if len(synthesis) < len(test_response):
    removed_section = test_response[len(synthesis):]
    print(removed_section[:200] + "..." if len(removed_section) > 200 else removed_section)
else:
    print("(Nothing was removed)")

# Test edge cases
print("\n" + "=" * 70)
print("TESTING EDGE CASES:")
print("=" * 70)

edge_cases = [
    ("Text with no references", "This is just the main content without any references."),
    ("References at start", "References:\n1. Test\n\nMain content here"),
    ("Multiple trigger words", "The research shows promise.\n\nFor additional details:\nExtra info here"),
]

for title, text in edge_cases:
    result = extract_synthesis_only(text)
    print(f"\n{title}:")
    print(f"  Original: {len(text)} chars")
    print(f"  Result: {len(result)} chars")
    print(f"  Extracted: {result[:50]}..." if len(result) > 50 else f"  Extracted: {result}")