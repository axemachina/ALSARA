# tests/test_integration.py
"""Integration tests for the full ALS Research Agent workflow"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from mcp.types import TextContent


@pytest.mark.asyncio
@pytest.mark.integration
class TestIntegration:

    async def test_multi_server_search_workflow(
        self,
        pubmed_session,
        biorxiv_session,
        clinicaltrials_session
    ):
        """Test searching across all three data sources"""

        # Search PubMed
        pubmed_result = await pubmed_session.call_tool(
            "search_pubmed",
            {"query": "ALS SOD1", "max_results": 3}
        )
        assert len(pubmed_result.content) > 0

        # Search bioRxiv
        biorxiv_result = await biorxiv_session.call_tool(
            "search_preprints",
            {"query": "ALS", "max_results": 3, "days_back": 90}
        )
        assert len(biorxiv_result.content) > 0

        # Search clinical trials
        trials_result = await clinicaltrials_session.call_tool(
            "search_trials",
            {"condition": "ALS", "status": "recruiting", "max_results": 3}
        )
        assert len(trials_result.content) > 0

        # All results should be valid
        assert all([pubmed_result, biorxiv_result, trials_result])

    async def test_fetch_and_detail_workflow(
        self,
        pubmed_session,
        clinicaltrials_session
    ):
        """Test fetching a result then getting its details"""

        # First search for papers
        search_result = await pubmed_session.call_tool(
            "search_pubmed",
            {"query": "ALS", "max_results": 1}
        )

        # Extract PMID from result (simplified - in real test would parse)
        text = search_result.content[0].text

        # Verify we got results
        assert "PMID" in text or "papers" in text.lower()

        # Similarly for clinical trials
        trials_search = await clinicaltrials_session.call_tool(
            "search_trials",
            {"condition": "ALS", "max_results": 1}
        )

        trials_text = trials_search.content[0].text
        assert "NCT" in trials_text or "trial" in trials_text.lower()

    async def test_error_recovery_across_servers(self, pubmed_session):
        """Test that errors in one server don't crash the system"""

        # Test with invalid query that should return gracefully
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "esearchresult": {"idlist": []}
            }

            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            result = await pubmed_session.call_tool(
                "search_pubmed",
                {"query": "nonexistentquery12345xyz"}
            )

            # Should return error message, not crash
            assert len(result.content) > 0
            assert "no results" in result.content[0].text.lower()

    async def test_concurrent_server_calls(
        self,
        pubmed_session,
        biorxiv_session,
        clinicaltrials_session
    ):
        """Test that multiple servers can be queried concurrently"""
        import asyncio

        # Create concurrent tasks
        tasks = [
            pubmed_session.call_tool(
                "search_pubmed",
                {"query": "ALS", "max_results": 2}
            ),
            biorxiv_session.call_tool(
                "search_preprints",
                {"query": "ALS", "max_results": 2}
            ),
            clinicaltrials_session.call_tool(
                "search_trials",
                {"condition": "ALS", "max_results": 2}
            )
        ]

        # Execute concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should succeed
        assert len(results) == 3

        # None should be exceptions
        for result in results:
            assert not isinstance(result, Exception)
            assert len(result.content) > 0

    async def test_server_initialization(
        self,
        pubmed_session,
        biorxiv_session,
        clinicaltrials_session,
        fetch_session
    ):
        """Test that all servers initialize and list tools correctly"""

        # List tools from each server
        pubmed_tools = await pubmed_session.list_tools()
        biorxiv_tools = await biorxiv_session.list_tools()
        trials_tools = await clinicaltrials_session.list_tools()
        fetch_tools = await fetch_session.list_tools()

        # Verify each server has expected tools
        assert len(pubmed_tools.tools) == 2  # search_pubmed, get_paper_details
        assert len(biorxiv_tools.tools) == 2  # search_preprints, get_preprint_details
        assert len(trials_tools.tools) == 2  # search_trials, get_trial_details
        assert len(fetch_tools.tools) == 1   # fetch_url

        # Verify tool names
        pubmed_tool_names = [t.name for t in pubmed_tools.tools]
        assert "search_pubmed" in pubmed_tool_names
        assert "get_paper_details" in pubmed_tool_names
