#!/usr/bin/env python3
"""
Query Classification Module for ALS Research Agent
Determines whether a query requires full research workflow or simple response
"""

import re
from typing import Dict, Tuple, List
import logging

logger = logging.getLogger(__name__)


class QueryClassifier:
    """Classify queries as research-required or simple questions"""

    # Keywords that indicate ALS research is needed
    RESEARCH_KEYWORDS = [
        # Disease-specific terms
        'als', 'amyotrophic lateral sclerosis', 'motor neuron disease',
        'mnd', 'lou gehrig', 'ftd', 'frontotemporal dementia',

        # Medical research terms
        'clinical trial', 'treatment', 'therapy', 'drug', 'medication',
        'gene therapy', 'stem cell', 'biomarker', 'diagnosis',
        'prognosis', 'survival', 'progression', 'symptom',
        'cure', 'breakthrough', 'research', 'study', 'paper',
        'latest', 'recent', 'new findings', 'advances',

        # Specific ALS-related
        'riluzole', 'edaravone', 'radicava', 'relyvrio', 'qalsody',
        'tofersen', 'sod1', 'c9orf72', 'tdp-43', 'fus',

        # Research actions
        'find studies', 'search papers', 'what research',
        'clinical evidence', 'scientific literature'
    ]

    # Keywords that indicate simple/general questions
    SIMPLE_KEYWORDS = [
        'hello', 'hi', 'hey', 'thanks', 'thank you',
        'how are you', "what's your name", 'who are you',
        'what can you do', 'help', 'test', 'testing',
        'explain', 'define', 'what is', 'what are',
        'how does', 'why', 'when', 'where', 'who'
    ]

    # Exclusion patterns for non-research queries
    NON_RESEARCH_PATTERNS = [
        r'^(hi|hello|hey|thanks|thank you)',
        r'^test\s',
        r'^how (are you|do you)',
        r'^what (is|are) (the|a|an)\s+\w+$',  # Simple definitions
        r'^(explain|define)\s+\w+$',  # Simple explanations
        r'^\w{1,3}$',  # Very short queries
    ]

    @classmethod
    def classify_query(cls, query: str) -> Dict[str, any]:
        """
        Classify a query and determine processing strategy.

        Returns:
            Dict with:
                - requires_research: bool - Whether to use full research workflow
                - confidence: float - Confidence in classification (0-1)
                - reason: str - Explanation of classification
                - suggested_mode: str - 'research' or 'simple'
        """
        query_lower = query.lower().strip()

        # Check for very short or empty queries
        if len(query_lower) < 5:
            return {
                'requires_research': False,
                'confidence': 0.9,
                'reason': 'Query too short for research',
                'suggested_mode': 'simple'
            }

        # Check exclusion patterns first
        for pattern in cls.NON_RESEARCH_PATTERNS:
            if re.match(pattern, query_lower):
                return {
                    'requires_research': False,
                    'confidence': 0.85,
                    'reason': 'Matches non-research pattern',
                    'suggested_mode': 'simple'
                }

        # Count research keywords
        research_score = sum(
            1 for keyword in cls.RESEARCH_KEYWORDS
            if keyword in query_lower
        )

        # Count simple keywords
        simple_score = sum(
            1 for keyword in cls.SIMPLE_KEYWORDS
            if keyword in query_lower
        )

        # Check for question complexity
        has_multiple_questions = query.count('?') > 1
        has_complex_structure = len(query.split()) > 15
        mentions_comparison = any(word in query_lower for word in
                                ['compare', 'versus', 'vs', 'difference between'])

        # Decision logic - Conservative approach for ALS research agent

        # FIRST: Check if this is truly just a greeting/thanks (only these skip research)
        greeting_only = query_lower in ['hi', 'hello', 'hey', 'thanks', 'thank you', 'bye', 'goodbye', 'test']
        if greeting_only and research_score == 0:
            return {
                'requires_research': False,
                'confidence': 0.95,
                'reason': 'Pure greeting or acknowledgment',
                'suggested_mode': 'simple'
            }

        # SECOND: If ANY research keyword is present, use research mode
        # This includes "ALS", "treatment", "therapy", etc.
        if research_score >= 1:
            return {
                'requires_research': True,
                'confidence': min(0.95, 0.7 + research_score * 0.1),
                'reason': f'Contains research-related terms ({research_score} keywords)',
                'suggested_mode': 'research'
            }

        # THIRD: Check for questions about the agent itself
        about_agent = any(phrase in query_lower for phrase in [
            'who are you', 'what can you do', 'how do you work',
            'what are you', 'your capabilities'
        ])
        if about_agent:
            return {
                'requires_research': False,
                'confidence': 0.85,
                'reason': 'Question about the agent itself',
                'suggested_mode': 'simple'
            }

        # DEFAULT: For an ALS research agent, when in doubt, use research mode
        # This is safer than potentially missing important medical queries
        return {
            'requires_research': True,
            'confidence': 0.6,
            'reason': 'Default to research mode for potential medical queries',
            'suggested_mode': 'research'
        }

    @classmethod
    def should_use_tools(cls, query: str) -> bool:
        """Quick check if query needs research tools"""
        classification = cls.classify_query(query)
        return classification['requires_research'] and classification['confidence'] > 0.65

    @classmethod
    def get_processing_hint(cls, classification: Dict) -> str:
        """Get a hint for how to process the query"""
        if classification['requires_research']:
            return "🔬 Using full research workflow ..."
        else:
            return "💬 Providing direct response without research tools"


def test_classifier():
    """Test the classifier with example queries"""
    test_queries = [
        # Should require research
        "What are the latest gene therapy trials for ALS?",
        "Compare riluzole and edaravone effectiveness",
        "Find recent studies on SOD1 mutations",
        "What breakthroughs in ALS treatment happened in 2024?",
        "Are there any promising stem cell therapies for motor neuron disease?",

        # Should NOT require research
        "Hello, how are you?",
        "What is your name?",
        "Test",
        "Thanks for your help",
        "Explain what a database is",
        "What time is it?",
        "How do I use this app?",
    ]

    print("Query Classification Test Results")
    print("=" * 60)

    for query in test_queries:
        result = QueryClassifier.classify_query(query)
        print(f"\nQuery: {query[:50]}...")
        print(f"Requires Research: {result['requires_research']}")
        print(f"Confidence: {result['confidence']:.2f}")
        print(f"Reason: {result['reason']}")
        print(f"Mode: {result['suggested_mode']}")
        print("-" * 40)


if __name__ == "__main__":
    test_classifier()