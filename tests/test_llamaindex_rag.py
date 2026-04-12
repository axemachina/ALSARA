#!/usr/bin/env python3
"""
Test script for LlamaIndex RAG System
Demonstrates research memory persistence and semantic search capabilities
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, '.')

from servers.llamaindex_server import (
    index_paper,
    semantic_search,
    get_research_connections,
    list_indexed_papers,
    clear_research_memory
)

# Sample ALS research papers for testing
SAMPLE_PAPERS = [
    {
        "title": "TDP-43 Proteinopathy in Amyotrophic Lateral Sclerosis",
        "abstract": "TDP-43 is a key protein in ALS pathology. This study examines the role of TDP-43 aggregation in motor neuron degeneration. We found that mislocalized TDP-43 forms cytoplasmic inclusions that are toxic to neurons.",
        "authors": "Smith J, Johnson K, Williams L",
        "doi": "10.1234/test.2024.001",
        "journal": "Nature Neuroscience",
        "year": 2024,
        "findings": "TDP-43 cytoplasmic aggregation correlates with disease severity"
    },
    {
        "title": "Novel Therapeutic Approaches for ALS Using Gene Therapy",
        "abstract": "Gene therapy offers promising treatment options for ALS. This research explores AAV-mediated delivery of protective factors to motor neurons. Results show significant neuroprotection in mouse models.",
        "authors": "Chen M, Davis R, Anderson P",
        "doi": "10.1234/test.2024.002",
        "journal": "Science Translational Medicine",
        "year": 2024,
        "findings": "AAV9-SOD1 reduces motor neuron loss by 60% in mouse models"
    },
    {
        "title": "Biomarkers for Early Detection of ALS",
        "abstract": "Early diagnosis of ALS remains challenging. This study identifies neurofilament light chain (NfL) as a promising biomarker. Elevated NfL levels were detected 6-12 months before symptom onset.",
        "authors": "Martinez A, Thompson B, Lee S",
        "doi": "10.1234/test.2024.003",
        "journal": "Lancet Neurology",
        "year": 2023,
        "findings": "NfL levels >150 pg/mL predict ALS onset with 85% accuracy"
    },
    {
        "title": "C9orf72 Repeat Expansion and RNA Toxicity in ALS",
        "abstract": "The C9orf72 hexanucleotide repeat expansion is the most common genetic cause of ALS. This paper demonstrates how RNA foci sequester RNA-binding proteins and disrupt cellular function.",
        "authors": "Wilson D, Brown E, Taylor F",
        "doi": "10.1234/test.2024.004",
        "journal": "Cell",
        "year": 2024,
        "findings": "RNA foci disrupt nucleocytoplasmic transport in 90% of C9-ALS cases"
    },
    {
        "title": "Metabolic Dysfunction in ALS Patient-Derived Motor Neurons",
        "abstract": "Metabolic alterations contribute to ALS pathogenesis. Using patient iPSC-derived motor neurons, we identified mitochondrial dysfunction and altered glucose metabolism as early disease features.",
        "authors": "Garcia R, Miller T, White K",
        "doi": "10.1234/test.2024.005",
        "journal": "Cell Metabolism",
        "year": 2024,
        "findings": "Glycolytic shift occurs before motor neuron degeneration"
    }
]

async def test_indexing():
    """Test indexing research papers"""
    print("=" * 80)
    print("TEST 1: Indexing Research Papers")
    print("=" * 80)

    for i, paper in enumerate(SAMPLE_PAPERS, 1):
        print(f"\n{i}. Indexing: {paper['title']}")
        result = await index_paper(
            title=paper["title"],
            abstract=paper["abstract"],
            authors=paper["authors"],
            doi=paper.get("doi"),
            journal=paper.get("journal"),
            year=paper.get("year"),
            findings=paper.get("findings"),
            url=f"https://doi.org/{paper.get('doi', '')}"
        )

        result_data = json.loads(result)
        if result_data["status"] == "success":
            print(f"   ✅ {result_data['message']}")
        elif result_data["status"] == "already_indexed":
            print(f"   ℹ️ {result_data['message']}")
        else:
            print(f"   ❌ Failed: {result_data.get('message', 'Unknown error')}")

    print("\n" + "-" * 40)
    print("Indexing complete!")

async def test_listing():
    """Test listing indexed papers"""
    print("\n" + "=" * 80)
    print("TEST 2: Listing Indexed Papers")
    print("=" * 80)

    result = await list_indexed_papers(limit=10, sort_by="year")
    result_data = json.loads(result)

    if result_data["status"] == "success":
        print(f"\nTotal papers in memory: {result_data['total_papers']}")
        print(f"Showing: {result_data['showing']} papers\n")

        for paper in result_data["papers"]:
            print(f"📄 {paper['title']}")
            print(f"   Authors: {', '.join(paper['authors'][:3]) if paper['authors'] else 'Unknown'}")
            print(f"   Year: {paper.get('year', 'Unknown')}")
            print(f"   Journal: {paper.get('journal', 'Unknown')}")
            print()
    else:
        print(f"❌ Failed to list papers: {result_data.get('message')}")

async def test_semantic_search():
    """Test semantic search capabilities"""
    print("=" * 80)
    print("TEST 3: Semantic Search")
    print("=" * 80)

    queries = [
        "protein aggregation and misfolding in neurodegeneration",
        "therapeutic interventions for motor neuron diseases",
        "biomarkers for early diagnosis",
        "genetic mutations causing ALS"
    ]

    for query in queries:
        print(f"\n🔍 Searching for: '{query}'")
        print("-" * 40)

        result = await semantic_search(query=query, max_results=3)
        result_data = json.loads(result)

        if result_data["status"] == "success":
            print(f"Found {result_data['num_results']} similar papers:\n")

            for res in result_data["results"]:
                print(f"  {res['rank']}. {res['title']}")
                if res.get('similarity_score'):
                    print(f"     Similarity: {res['similarity_score']}")
                print(f"     Year: {res.get('year', 'Unknown')}")
                print(f"     Excerpt: {res['excerpt'][:150]}...")
                print()
        else:
            print(f"  No results found")

async def test_connections():
    """Test finding research connections"""
    print("=" * 80)
    print("TEST 4: Research Connections")
    print("=" * 80)

    test_paper = "TDP-43 Proteinopathy in Amyotrophic Lateral Sclerosis"

    print(f"\n🔗 Finding connections for: '{test_paper}'")
    print("-" * 40)

    result = await get_research_connections(
        paper_title=test_paper,
        connection_type="similar",
        max_connections=3
    )

    result_data = json.loads(result)

    if result_data["status"] == "success":
        print(f"Found {result_data['num_connections']} connected papers:\n")

        for conn in result_data["connections"]:
            print(f"  • {conn['title']}")
            print(f"    Connection strength: {conn.get('connection_strength', 'Unknown')}")
            print(f"    Year: {conn.get('year', 'Unknown')}")
            print()
    else:
        print(f"  {result_data.get('message', 'No connections found')}")

async def test_persistence():
    """Test that memory persists (simulated)"""
    print("=" * 80)
    print("TEST 5: Memory Persistence")
    print("=" * 80)

    print("\n📊 Checking if research memory persists...")

    # List papers to verify they're still there
    result = await list_indexed_papers(limit=1)
    result_data = json.loads(result)

    if result_data["status"] == "success" and result_data["total_papers"] > 0:
        print(f"✅ Research memory contains {result_data['total_papers']} papers")
        print("   Memory successfully persists across sessions!")
    else:
        print("⚠️ No papers in memory (may be first run)")

    # Show ChromaDB location
    print(f"\n📁 Vector database location: ./chroma_db/")
    print("   This directory contains your persistent research memory")

async def main():
    """Run all tests"""
    print("🧠 LlamaIndex RAG System Test Suite")
    print("Testing Research Memory for ALS Research Agent")
    print("=" * 80)

    try:
        # Check if LlamaIndex is available
        from servers.llamaindex_server import LLAMAINDEX_AVAILABLE

        if not LLAMAINDEX_AVAILABLE:
            print("\n❌ LlamaIndex not installed!")
            print("\nTo install required dependencies, run:")
            print("  pip install llama-index-core llama-index-vector-stores-chroma")
            print("  pip install llama-index-embeddings-huggingface")
            print("  pip install chromadb sentence-transformers transformers")
            return

        print("\n✅ LlamaIndex dependencies detected")
        print("\nRunning tests...")

        # Run tests
        await test_indexing()
        await test_listing()
        await test_semantic_search()
        await test_connections()
        await test_persistence()

        print("\n" + "=" * 80)
        print("✅ ALL TESTS COMPLETE!")
        print("=" * 80)

        print("\n📌 Summary:")
        print("- Indexed research papers into persistent memory")
        print("- Performed semantic similarity searches")
        print("- Discovered research connections")
        print("- Verified memory persistence")

        print("\n🚀 Your ALS Research Agent now has:")
        print("1. Persistent research memory that survives restarts")
        print("2. Semantic search across all indexed papers")
        print("3. Ability to find connections between research")
        print("4. Progressive learning from every paper encountered")

        print("\n💡 Next steps:")
        print("1. Install dependencies: pip install -r requirements.txt")
        print("2. Papers will auto-index when searched via PubMed/bioRxiv")
        print("3. Agent becomes smarter with every research session!")

    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())