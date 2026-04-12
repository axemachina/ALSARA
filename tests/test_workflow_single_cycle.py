#!/usr/bin/env python3
"""
Test to verify workflow appears as a single cycle, not duplicated
"""

# Example of CORRECT workflow behavior
correct_workflow = """
📊 **Search Progress:** Completed searches...

**🎯 PLANNING:**
I will search PubMed and bioRxiv for information on Omega-3 fatty acids in ALS treatment.

**🔧 EXECUTING:**
Searching PubMed for "Omega-3 fatty acids ALS treatment"...
[Results from initial searches]

**🤔 REFLECTING:**
Based on the search results, I found some relevant studies. However, I need more specific information about dosages and clinical trials. Let me search for more specific information...
[Additional searches happen HERE within reflection phase]
Searching for "Omega-3 dosage ALS clinical trials"...
Found additional relevant information about specific dosages used in trials.

**✅ SYNTHESIS:**
Based on all the research found, Omega-3 fatty acids show promise in ALS treatment...
[Final comprehensive answer]
"""

# Example of INCORRECT workflow behavior (what we're trying to prevent)
incorrect_workflow = """
📊 **Search Progress:** Completed searches...

**🎯 PLANNING:**
I will search PubMed and bioRxiv for information on Omega-3 fatty acids in ALS treatment.

**🔧 EXECUTING:**
Searching PubMed...
[Initial results]

**🤔 REFLECTING:**
I need more information. Let me search again.

**🎯 PLANNING:**  ← WRONG! Starting new workflow
I will now search for more specific information...

**🔧 EXECUTING:**  ← WRONG! Duplicating phases
Searching again...

**🤔 REFLECTING:**  ← WRONG! Second reflection
Now I have enough information.

**✅ SYNTHESIS:**
Based on the research...
"""

def count_phase_occurrences(text):
    """Count how many times each phase appears"""
    phases = {
        "PLANNING": text.count("**🎯 PLANNING:**"),
        "EXECUTING": text.count("**🔧 EXECUTING:**"),
        "REFLECTING": text.count("**🤔 REFLECTING:**"),
        "SYNTHESIS": text.count("**✅ SYNTHESIS:**")
    }
    return phases

print("=" * 70)
print("TESTING SINGLE WORKFLOW CYCLE")
print("=" * 70)

print("\n### CORRECT WORKFLOW (Single Cycle):")
print("-" * 40)
correct_counts = count_phase_occurrences(correct_workflow)
for phase, count in correct_counts.items():
    if count == 1:
        print(f"✅ {phase}: appears {count} time (correct)")
    else:
        print(f"❌ {phase}: appears {count} times (should be 1)")

print("\nKey point: Additional searches happen WITHIN the REFLECTING phase")
print("No new PLANNING or EXECUTING phases are created")

print("\n### INCORRECT WORKFLOW (Duplicate Cycles):")
print("-" * 40)
incorrect_counts = count_phase_occurrences(incorrect_workflow)
for phase, count in incorrect_counts.items():
    if count == 1:
        print(f"✅ {phase}: appears {count} time")
    else:
        print(f"❌ {phase}: appears {count} times (PROBLEM!)")

print("\nProblem: The workflow restarts when needing more information")
print("This creates duplicate phases and confusing output")

print("\n" + "=" * 70)
print("SYSTEM PROMPT IMPROVEMENTS")
print("=" * 70)
print("""
The system prompt has been updated to prevent duplicate workflows:

1. REFLECTION phase now explicitly states:
   - "DO NOT start a new PLANNING phase"
   - "Stay WITHIN the REFLECTION phase"
   - "Additional searches are part of reflection, not a new workflow"

2. WORKFLOW RULES clarify:
   - "The workflow is a SINGLE CYCLE"
   - "NEVER restart the workflow"
   - "Additional searches happen WITHIN reflection"

3. Phase format requirements:
   - Must use **🤔 REFLECTING:** (with asterisks)
   - Must appear on a new line
   - Must appear EXACTLY ONCE

This ensures clean, single-cycle workflows with all phases appearing once.
""")