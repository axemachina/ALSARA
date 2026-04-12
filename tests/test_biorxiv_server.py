# tests/test_biorxiv_server.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from mcp.types import TextContent
import httpx

@pytest.mark.asyncio
class TestBioRxivServer:

    async def test_list_tools(self, biorxiv_session):
        """Test that server lists expected tools"""
        response = await biorxiv_session.list_tools()

        tool_names = [tool.name for tool in response.tools]
        assert "search_preprints" in tool_names
        assert "get_preprint_details" in tool_names

        # Check search_preprints schema
        search_tool = next(t for t in response.tools if t.name == "search_preprints")
        assert "query" in search_tool.inputSchema["properties"]
        assert "server" in search_tool.inputSchema["properties"]
        assert search_tool.inputSchema["required"] == ["query"]

    async def test_search_preprints_basic(self, biorxiv_session, mock_biorxiv_response):
        """Test basic preprint search functionality"""
        with patch('httpx.AsyncClient') as mock_client:
            # Mock API response
            mock_response = MagicMock()
            mock_response.json.return_value = mock_biorxiv_response

            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            result = await biorxiv_session.call_tool(
                "search_preprints",
                {"query": "ALS TDP-43", "max_results": 5}
            )

            assert len(result.content) > 0
            assert isinstance(result.content[0], TextContent)

            text = result.content[0].text
            assert "preprints" in text.lower() or "found" in text.lower()

    async def test_search_preprints_both_servers(self, biorxiv_session):
        """Test searching both bioRxiv and medRxiv"""
        result = await biorxiv_session.call_tool(
            "search_preprints",
            {"query": "ALS", "server": "both", "max_results": 5}
        )

        assert len(result.content) > 0

    async def test_search_preprints_biorxiv_only(self, biorxiv_session):
        """Test searching only bioRxiv"""
        result = await biorxiv_session.call_tool(
            "search_preprints",
            {"query": "ALS", "server": "biorxiv", "max_results": 3}
        )

        assert len(result.content) > 0

    async def test_search_preprints_medrxiv_only(self, biorxiv_session):
        """Test searching only medRxiv"""
        result = await biorxiv_session.call_tool(
            "search_preprints",
            {"query": "ALS", "server": "medrxiv", "max_results": 3}
        )

        assert len(result.content) > 0

    async def test_search_preprints_no_results(self, biorxiv_session):
        """Test handling of empty search results"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"collection": []}

            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            result = await biorxiv_session.call_tool(
                "search_preprints",
                {"query": "extremelyunlikelysearchterm12345"}
            )

            text = result.content[0].text
            assert "no preprints found" in text.lower()

    async def test_search_preprints_date_filtering(self, biorxiv_session):
        """Test date range filtering"""
        result = await biorxiv_session.call_tool(
            "search_preprints",
            {"query": "ALS", "days_back": 30, "max_results": 5}
        )

        assert len(result.content) > 0

    async def test_get_preprint_details(self, biorxiv_session):
        """Test fetching specific preprint details"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "collection": [{
                    "doi": "10.1101/2024.01.01.123456",
                    "title": "Novel ALS therapeutic approach",
                    "abstract": "This study investigates a new treatment for ALS.",
                    "authors": "Smith J; Doe J; Johnson K",
                    "date": "2024-01-01",
                    "category": "Neuroscience",
                    "version": "1",
                    "license": "CC BY 4.0"
                }]
            }

            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            result = await biorxiv_session.call_tool(
                "get_preprint_details",
                {"doi": "10.1101/2024.01.01.123456"}
            )

            text = result.content[0].text
            assert "10.1101/2024.01.01.123456" in text
            assert "preprint" in text.lower()

    async def test_get_preprint_details_not_found(self, biorxiv_session):
        """Test handling of non-existent preprint"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"collection": []}

            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            result = await biorxiv_session.call_tool(
                "get_preprint_details",
                {"doi": "10.1101/9999.99.99.999999"}
            )

            text = result.content[0].text
            assert "no preprint found" in text.lower()

    async def test_network_error_handling(self, biorxiv_session):
        """Test graceful handling of network errors"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(
                side_effect=httpx.TimeoutException("Request timeout")
            )
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            result = await biorxiv_session.call_tool(
                "search_preprints",
                {"query": "ALS"}
            )

            # Should return error message instead of raising
            assert len(result.content) > 0
            text = result.content[0].text
            assert "error" in text.lower() or "timeout" in text.lower()

    async def test_search_preprints_invalid_params(self, biorxiv_session):
        """Test handling of invalid parameters"""
        # Missing required 'query' parameter should raise an error
        with pytest.raises((ValueError, TypeError, KeyError)):
            await biorxiv_session.call_tool(
                "search_preprints",
                {"max_results": 10}  # Missing required 'query'
            )

    async def test_rate_limiting(self, biorxiv_session):
        """Test that rate limiting is respected"""
        import time

        start_time = time.time()

        # Make two consecutive calls
        await biorxiv_session.call_tool(
            "search_preprints",
            {"query": "ALS", "max_results": 1}
        )

        await biorxiv_session.call_tool(
            "search_preprints",
            {"query": "motor neuron", "max_results": 1}
        )

        elapsed = time.time() - start_time

        # Should take at least 1 second due to rate limiting
        assert elapsed >= 1.0
