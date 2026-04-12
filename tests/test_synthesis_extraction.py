#!/usr/bin/env python3
"""
Test extraction of ONLY the synthesis section from a full workflow response
"""

import re

def extract_synthesis_only(text: str) -> str:
    """Extract only the synthesis part, starting after SYNTHESIS marker."""

    # FIRST: Extract ONLY the synthesis section (after ✅ SYNTHESIS:)
    synthesis_match = re.search(r'(?:✅\s*\*{0,2}SYNTHESIS\*{0,2}\s*:?.*?)\n(.*)', text, re.IGNORECASE | re.DOTALL)
    if synthesis_match:
        synthesis_text = synthesis_match.group(1)
        print("✂️ Found synthesis section")
    else:
        # Fallback: if no synthesis marker found, use the whole response
        synthesis_text = text
        print("⚠️ No synthesis marker found, using full response")

    # Precise cutoff patterns - focus on clear section headers
    cutoff_patterns = [
        # Clear section headers with colons - most reliable indicators
        r'\n\s*(?:For (?:more|additional|further) (?:information|details|reading))\s*[:：]',
        r'\n\s*(?:References?|Sources?|Citations?|Bibliography)\s*[:：]',
        r'\n\s*(?:Additional (?:resources?|information|reading|materials?))\s*[:：]',

        # Markdown headers for reference sections (must be on their own line)
        r'\n\s*#{1,6}\s+(?:References?|Sources?|Citations?|Bibliography)\s*$',
        r'\n\s*#{1,6}\s+(?:For (?:more|additional|further) (?:information|details))\s*$',

        # Bold headers for reference sections (with newline after)
        r'\n\s*\*\*(?:References?|Sources?|Citations?)\*\*\s*[:：]?\s*\n',
        r'\n\s*\*\*(?:For (?:more|additional) information)\*\*\s*[:：]?\s*\n',

        # Phrases that clearly introduce reference lists
        r'\n\s*(?:Here are|Below are|The following are)\s+(?:the |some |additional )?(?:references|sources|citations|papers cited|studies referenced)',
        r'\n\s*(?:References used|Sources consulted|Papers cited|Studies referenced)\s*[:：]',

        # Direct ID listings
        r'\n\s*(?:PMID|DOI|NCT)\s*[:：]\s*\d+',

        # Footer sections
        r'\n\s*(?:Note|Notes|Disclaimer|Important notice)\s*[:：]',
    ]

    # THEN: Remove references and footer sections
    for pattern in cutoff_patterns:
        match = re.search(pattern, synthesis_text, re.IGNORECASE | re.MULTILINE)
        if match:
            synthesis_text = synthesis_text[:match.start()]
            print(f"✂️ Cut off at pattern: {pattern[:50]}...")
            break

    return synthesis_text.strip()

# Test with a full workflow response
test_response = """📊 **Search Progress:** Completed 1/1 searches

✓ **Completed:** pubmed → search_pubmed `SOD1 ALS gene therapy`

🎯 **PLANNING:** To answer the user's question about the main genes that should be tested for ALS gene therapy eligibility, I will first identify the genes that are commonly associated with ALS and have been studied in the context of gene therapy.

🔧 **EXECUTING:**
1. Identify genes associated with ALS: SOD1, C9ORF72, TARDBP, FUS, and others.
2. Analyze search results to determine relevance to ALS gene therapy eligibility.

🔍 **EXECUTION RESULTS:**
The search results provided information on various genes associated with ALS, including SOD1, C9ORF72, TARDBP, and FUS. The results also discussed the potential of gene therapy for ALS.

🤔 **REFLECTING:**
1. Do I have sufficient high-quality information to answer comprehensively? Yes, the search results provided comprehensive information.
2. Are there important aspects that need more investigation? No, the search results covered the main genes.

✅ **SYNTHESIS:**
Based on the search results, the main genes that should be tested for ALS gene therapy eligibility are:

1. **SOD1** (Superoxide dismutase 1): Associated with familial ALS, accounts for ~20% of familial cases. Tofersen therapy specifically targets SOD1 mutations.

2. **C9ORF72**: The most common genetic cause of ALS, responsible for ~40% of familial cases. Antisense oligonucleotides are in development.

3. **TARDBP** (encoding TDP-43): Associated with ~4% of familial ALS cases. Gene therapy approaches are being researched.

4. **FUS** (Fused in sarcoma): Accounts for ~5% of familial ALS. ASO therapies are in early development stages.

These four genes represent the primary targets for current and emerging ALS gene therapies. Genetic testing for these mutations is crucial for determining eligibility for gene-specific treatments like Tofersen (for SOD1) and enrollment in clinical trials for other gene-targeted therapies.

References:
1. Miller T, et al. Phase 1-2 Trial of Antisense Oligonucleotide Tofersen for SOD1 ALS. NEJM 2020. PMID: 32640130
2. Benatar M, et al. Design of a phase 3 trial of tofersen. Ann Clin Transl Neurol 2022. PMID: 35234567
3. Clinical trials database: NCT04856982, NCT03626012

Note: Always consult with a genetic counselor and neurologist specializing in ALS for comprehensive genetic testing and treatment eligibility assessment.
"""

print("=" * 70)
print("TESTING SYNTHESIS-ONLY EXTRACTION")
print("=" * 70)

# Extract synthesis
synthesis = extract_synthesis_only(test_response)

print(f"\nOriginal length: {len(test_response)} characters")
print(f"Synthesis length: {len(synthesis)} characters")
print(f"Reduction: {100 - (len(synthesis)/len(test_response)*100):.1f}%")

print("\n" + "=" * 70)
print("EXTRACTED SYNTHESIS TEXT (for voice reading):")
print("=" * 70)
print(synthesis)

print("\n" + "=" * 70)
print("VERIFICATION:")
print("=" * 70)
# Check that planning/executing/reflecting are NOT in the synthesis
unwanted_sections = ["PLANNING:", "EXECUTING:", "REFLECTING:", "EXECUTION RESULTS:", "Search Progress:"]
for section in unwanted_sections:
    if section in synthesis:
        print(f"❌ ERROR: '{section}' found in synthesis!")
    else:
        print(f"✅ OK: '{section}' not in synthesis")

# Check that the main answer IS in the synthesis
if "SOD1" in synthesis and "C9ORF72" in synthesis:
    print("✅ OK: Main gene content is present")
else:
    print("❌ ERROR: Main gene content missing!")

# Check that references are removed
if "PMID:" in synthesis or "NCT" in synthesis:
    print("⚠️ WARNING: Reference IDs still present")
else:
    print("✅ OK: Reference IDs removed")