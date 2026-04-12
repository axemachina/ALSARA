# tests/test_performance.py
import pytest
import time
import asyncio

@pytest.mark.asyncio
@pytest.mark.performance
class TestPerformance:
    
    async def test_search_response_time(self, pubmed_session):
        """Test that searches complete in reasonable time"""
        start = time.time()
        
        await pubmed_session.call_tool(
            "search_pubmed",
            {"query": "ALS", "max_results": 10}
        )
        
        elapsed = time.time() - start
        assert elapsed < 5.0  # Should complete within 5 seconds
    
    async def test_concurrent_requests(self, pubmed_session):
        """Test handling of concurrent requests"""
        queries = ["ALS SOD1", "ALS C9orf72", "ALS TDP43", "ALS FUS"]
        
        start = time.time()
        
        tasks = [
            pubmed_session.call_tool(
                "search_pubmed",
                {"query": q, "max_results": 5}
            )
            for q in queries
        ]
        
        results = await asyncio.gather(*tasks)
        
        elapsed = time.time() - start
        
        # Should complete faster than sequential (< 4 * single_request_time)
        assert len(results) == 4
        assert all(len(r.content) > 0 for r in results)
        assert elapsed < 15.0  # Reasonable concurrent time
    
    async def test_memory_usage_large_results(self, pubmed_session):
        """Test memory efficiency with large result sets"""
        import tracemalloc
        
        tracemalloc.start()
        
        await pubmed_session.call_tool(
            "search_pubmed",
            {"query": "ALS", "max_results": 50}
        )
        
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        # Peak memory should be reasonable (< 50 MB for this operation)
        assert peak < 50 * 1024 * 1024
