#!/usr/bin/env python3
"""
Smart Cache System for ALS Research Agent
Features:
- Query normalization to match similar queries
- Cache pre-warming with common queries
- High-frequency question optimization
"""

import json
import hashlib
import re
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import asyncio
import logging

logger = logging.getLogger(__name__)


class SmartCache:
    """Advanced caching system with query normalization and pre-warming"""

    def __init__(self, cache_dir: str = ".cache", ttl_hours: int = 24):
        """
        Initialize smart cache system.

        Args:
            cache_dir: Directory for cache storage
            ttl_hours: Time-to-live for cached entries in hours
        """
        self.cache_dir = cache_dir
        self.ttl = timedelta(hours=ttl_hours)
        self.cache = {}  # In-memory cache
        self.normalized_cache = {}  # Maps normalized queries to original cache keys
        self.high_frequency_queries = {}  # User-specified common queries
        self.query_stats = {}  # Track query frequency

        # Ensure cache directory exists
        import os
        os.makedirs(cache_dir, exist_ok=True)

        # Load persistent cache on init
        self.load_cache()

    def normalize_query(self, query: str) -> str:
        """
        Normalize query for better cache matching.

        Handles variations like:
        - "ALS gene therapy" vs "gene therapy ALS"
        - "What are the latest trials" vs "what are latest trials"
        - Different word orders, case, punctuation
        """
        # Convert to lowercase
        normalized = query.lower().strip()

        # Remove common question words that don't affect meaning
        question_words = [
            'what', 'how', 'when', 'where', 'why', 'who', 'which',
            'are', 'is', 'the', 'a', 'an', 'there', 'can', 'could',
            'would', 'should', 'do', 'does', 'did', 'have', 'has', 'had'
        ]

        # Remove punctuation
        normalized = re.sub(r'[^\w\s]', ' ', normalized)

        # Split into words and remove question words
        words = normalized.split()
        content_words = [w for w in words if w not in question_words]

        # Sort words alphabetically for consistent ordering
        # This makes "ALS gene therapy" match "gene therapy ALS"
        content_words.sort()

        # Join back together
        normalized = ' '.join(content_words)

        # Remove extra whitespace
        normalized = ' '.join(normalized.split())

        return normalized

    def generate_cache_key(self, query: str, include_normalization: bool = True) -> str:
        """
        Generate a cache key for a query.

        Args:
            query: The original query
            include_normalization: Whether to also store normalized version

        Returns:
            Hash-based cache key
        """
        # Generate hash of original query
        original_hash = hashlib.sha256(query.encode()).hexdigest()[:16]

        if include_normalization:
            # Also store mapping from normalized query to this cache key
            normalized = self.normalize_query(query)
            normalized_hash = hashlib.sha256(normalized.encode()).hexdigest()[:16]

            # Store mapping for future lookups
            if normalized_hash not in self.normalized_cache:
                self.normalized_cache[normalized_hash] = []
            if original_hash not in self.normalized_cache[normalized_hash]:
                self.normalized_cache[normalized_hash].append(original_hash)

        return original_hash

    def find_similar_cached(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Find cached results for similar queries.

        Args:
            query: The query to search for

        Returns:
            Cached result if found, None otherwise
        """
        # First try exact match
        exact_key = self.generate_cache_key(query, include_normalization=False)
        if exact_key in self.cache:
            entry = self.cache[exact_key]
            if self._is_valid(entry):
                logger.info(f"Cache hit (exact): {query[:50]}...")
                self._update_stats(query)
                return entry['result']

        # Try normalized match
        normalized = self.normalize_query(query)
        normalized_key = hashlib.sha256(normalized.encode()).hexdigest()[:16]

        if normalized_key in self.normalized_cache:
            # Check all original queries that normalize to this
            for original_key in self.normalized_cache[normalized_key]:
                if original_key in self.cache:
                    entry = self.cache[original_key]
                    if self._is_valid(entry):
                        logger.info(f"Cache hit (normalized): {query[:50]}...")
                        self._update_stats(query)
                        return entry['result']

        logger.info(f"Cache miss: {query[:50]}...")
        return None

    def store(self, query: str, result: Any, metadata: Optional[Dict] = None):
        """
        Store a query result in cache.

        Args:
            query: The original query
            result: The result to cache
            metadata: Optional metadata about the result
        """
        cache_key = self.generate_cache_key(query, include_normalization=True)

        entry = {
            'query': query,
            'result': result,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {},
            'access_count': 0
        }

        self.cache[cache_key] = entry
        self._update_stats(query)

        # Persist to disk asynchronously (non-blocking)
        asyncio.create_task(self._save_cache_async())

        logger.info(f"Cached result for: {query[:50]}...")

    def _is_valid(self, entry: Dict) -> bool:
        """Check if a cache entry is still valid (not expired)"""
        try:
            timestamp = datetime.fromisoformat(entry['timestamp'])
            age = datetime.now() - timestamp
            return age < self.ttl
        except:
            return False

    def _update_stats(self, query: str):
        """Update query frequency statistics"""
        normalized = self.normalize_query(query)
        if normalized not in self.query_stats:
            self.query_stats[normalized] = {'count': 0, 'last_access': None}

        self.query_stats[normalized]['count'] += 1
        self.query_stats[normalized]['last_access'] = datetime.now().isoformat()

    async def pre_warm_cache(self, queries: List[Dict[str, Any]],
                            search_func=None, llm_func=None):
        """
        Pre-warm cache with common queries.

        Args:
            queries: List of dicts with 'query', 'search_terms', 'use_claude' keys
            search_func: Async function to perform searches
            llm_func: Async function to call Claude for high-priority queries
        """
        logger.info(f"Pre-warming cache with {len(queries)} queries...")

        for query_config in queries:
            query = query_config['query']

            # Check if already cached
            if self.find_similar_cached(query):
                logger.info(f"Already cached: {query}")
                continue

            try:
                # Use optimized search terms if provided
                search_terms = query_config.get('search_terms', query)
                use_claude = query_config.get('use_claude', False)

                if search_func:
                    # Perform search with optimized terms
                    logger.info(f"Pre-warming: {query}")

                    if use_claude and llm_func:
                        # Use Claude for high-priority queries
                        result = await llm_func(search_terms)
                    else:
                        # Use standard search
                        result = await search_func(search_terms)

                    # Cache the result
                    self.store(query, result, {
                        'pre_warmed': True,
                        'optimized_terms': search_terms,
                        'used_claude': use_claude
                    })

                    # Small delay to avoid overwhelming APIs
                    await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Failed to pre-warm cache for '{query}': {e}")

    def add_high_frequency_query(self, query: str, config: Dict[str, Any]):
        """
        Add a high-frequency query configuration.

        Args:
            query: The query pattern
            config: Configuration dict with search_terms, use_claude, etc.
        """
        normalized = self.normalize_query(query)
        self.high_frequency_queries[normalized] = {
            'original': query,
            'config': config,
            'added': datetime.now().isoformat()
        }
        logger.info(f"Added high-frequency query: {query}")

    def get_high_frequency_config(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Get configuration for a high-frequency query if it matches.

        Args:
            query: The query to check

        Returns:
            Configuration dict if this is a high-frequency query
        """
        normalized = self.normalize_query(query)
        if normalized in self.high_frequency_queries:
            return self.high_frequency_queries[normalized]['config']
        return None

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        valid_entries = sum(1 for entry in self.cache.values() if self._is_valid(entry))
        total_entries = len(self.cache)

        # Get top queries
        top_queries = sorted(
            self.query_stats.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )[:10]

        return {
            'total_entries': total_entries,
            'valid_entries': valid_entries,
            'expired_entries': total_entries - valid_entries,
            'normalized_groups': len(self.normalized_cache),
            'high_frequency_queries': len(self.high_frequency_queries),
            'top_queries': [
                {'query': q, 'count': stats['count']}
                for q, stats in top_queries
            ]
        }

    def clear_expired(self):
        """Remove expired entries from cache"""
        expired_keys = [
            key for key, entry in self.cache.items()
            if not self._is_valid(entry)
        ]

        for key in expired_keys:
            del self.cache[key]

        if expired_keys:
            logger.info(f"Cleared {len(expired_keys)} expired cache entries")
            self.save_cache()

    def save_cache(self):
        """Persist cache to disk"""
        cache_file = f"{self.cache_dir}/smart_cache.json"
        try:
            with open(cache_file, 'w') as f:
                json.dump({
                    'cache': self.cache,
                    'normalized_cache': self.normalized_cache,
                    'high_frequency_queries': self.high_frequency_queries,
                    'query_stats': self.query_stats
                }, f, indent=2)
            logger.debug(f"Cache saved to {cache_file}")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    async def _save_cache_async(self):
        """Async version of save_cache that doesn't block"""
        try:
            await asyncio.to_thread(self.save_cache)
        except Exception as e:
            logger.error(f"Failed to save cache asynchronously: {e}")

    def load_cache(self):
        """Load cache from disk"""
        cache_file = f"{self.cache_dir}/smart_cache.json"
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
                self.cache = data.get('cache', {})
                self.normalized_cache = data.get('normalized_cache', {})
                self.high_frequency_queries = data.get('high_frequency_queries', {})
                self.query_stats = data.get('query_stats', {})

            # Clear expired entries on load
            self.clear_expired()

            logger.info(f"Loaded cache with {len(self.cache)} entries")
        except FileNotFoundError:
            logger.info("No existing cache file found")
        except Exception as e:
            logger.error(f"Failed to load cache: {e}")


# Configuration for common ALS queries to pre-warm
DEFAULT_PREWARM_QUERIES = [
    {
        'query': 'What are the latest ALS treatments?',
        'search_terms': 'ALS treatment therapy 2024 riluzole edaravone',
        'use_claude': True  # High-frequency, use Claude for best results
    },
    {
        'query': 'Gene therapy for ALS',
        'search_terms': 'ALS gene therapy SOD1 C9orf72 clinical trial',
        'use_claude': True
    },
    {
        'query': 'ALS clinical trials',
        'search_terms': 'ALS clinical trials recruiting phase 2 phase 3',
        'use_claude': False
    },
    {
        'query': 'What causes ALS?',
        'search_terms': 'ALS etiology pathogenesis genetic environmental factors',
        'use_claude': True
    },
    {
        'query': 'ALS symptoms and diagnosis',
        'search_terms': 'ALS symptoms diagnosis EMG criteria El Escorial',
        'use_claude': False
    },
    {
        'query': 'Stem cell therapy for ALS',
        'search_terms': 'ALS stem cell therapy mesenchymal clinical trial',
        'use_claude': False
    },
    {
        'query': 'ALS prognosis and life expectancy',
        'search_terms': 'ALS prognosis survival life expectancy factors',
        'use_claude': True
    },
    {
        'query': 'New ALS drugs',
        'search_terms': 'ALS new drugs FDA approved pipeline 2024',
        'use_claude': False
    },
    {
        'query': 'ALS biomarkers',
        'search_terms': 'ALS biomarkers neurofilament TDP-43 diagnostic prognostic',
        'use_claude': False
    },
    {
        'query': 'Is there a cure for ALS?',
        'search_terms': 'ALS cure breakthrough research treatment advances',
        'use_claude': True
    }
]


def test_smart_cache():
    """Test the smart cache functionality"""
    print("Testing Smart Cache System")
    print("=" * 60)

    cache = SmartCache()

    # Test query normalization
    test_queries = [
        ("What are the latest ALS gene therapy trials?", "ALS gene therapy trials"),
        ("gene therapy ALS", "ALS gene therapy"),
        ("What is ALS?", "ALS"),
        ("HOW does riluzole work for ALS?", "ALS riluzole work"),
    ]

    print("\n1. Query Normalization Tests:")
    for original, expected_words in test_queries:
        normalized = cache.normalize_query(original)
        print(f"  Original: {original}")
        print(f"  Normalized: {normalized}")
        print(f"  Expected words present: {all(w in normalized for w in expected_words.lower().split())}")
        print()

    # Test similar query matching
    print("\n2. Similar Query Matching:")
    cache.store("What are the latest ALS treatments?", {"result": "Treatment data"})

    similar_queries = [
        "latest ALS treatments",
        "ALS latest treatments",
        "What are latest treatments for ALS?",
        "treatments ALS latest"
    ]

    for query in similar_queries:
        result = cache.find_similar_cached(query)
        print(f"  Query: {query}")
        print(f"  Found: {result is not None}")

    # Test cache statistics
    print("\n3. Cache Statistics:")
    stats = cache.get_cache_stats()
    print(f"  Total entries: {stats['total_entries']}")
    print(f"  Valid entries: {stats['valid_entries']}")
    print(f"  Normalized groups: {stats['normalized_groups']}")

    print("\n✅ Smart cache tests completed!")


if __name__ == "__main__":
    test_smart_cache()