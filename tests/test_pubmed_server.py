# tests/test_pubmed_server.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from mcp.types import TextContent
import httpx

@pytest.mark.asyncio
class TestPubMedServer:
    
    async def test_list_tools(self, pubmed_session):
        """Test that server lists expected tools"""
        response = await pubmed_session.list_tools()
        
        tool_names = [tool.name for tool in response.tools]
        assert "search_pubmed" in tool_names
        assert "get_paper_details" in tool_names
        
        # Check search_pubmed schema
        search_tool = next(t for t in response.tools if t.name == "search_pubmed")
        assert "query" in search_tool.inputSchema["properties"]
        assert "max_results" in search_tool.inputSchema["properties"]
        assert search_tool.inputSchema["required"] == ["query"]
    
    async def test_search_pubmed_basic(self, pubmed_session):
        """Test basic PubMed search functionality"""
        result = await pubmed_session.call_tool(
            "search_pubmed",
            {"query": "ALS SOD1", "max_results": 5}
        )
        
        assert len(result.content) > 0
        assert isinstance(result.content[0], TextContent)
        
        text = result.content[0].text
        assert "papers" in text.lower() or "results" in text.lower()
    
    async def test_search_pubmed_with_mocked_api(self, pubmed_session, mock_pubmed_response):
        """Test PubMed search with mocked HTTP responses"""
        with patch('httpx.AsyncClient') as mock_client:
            # Mock search response (returns PMIDs)
            mock_search_response = MagicMock()
            mock_search_response.json.return_value = {
                "esearchresult": {
                    "idlist": ["12345678"]
                }
            }
            
            # Mock fetch response (returns XML)
            mock_fetch_response = MagicMock()
            mock_fetch_response.text = mock_pubmed_response
            
            # Setup async context manager
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(
                side_effect=[mock_search_response, mock_fetch_response]
            )
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            result = await pubmed_session.call_tool(
                "search_pubmed",
                {"query": "ALS SOD1", "max_results": 1}
            )
            
            text = result.content[0].text
            assert "12345678" in text  # PMID should be in result
            assert "SOD1" in text or "therapy" in text.lower()
    
    async def test_search_pubmed_no_results(self, pubmed_session):
        """Test handling of empty search results"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "esearchresult": {
                    "idlist": []
                }
            }
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            result = await pubmed_session.call_tool(
                "search_pubmed",
                {"query": "extremelyunlikelysearchterm12345"}
            )
            
            text = result.content[0].text
            assert "no results" in text.lower()
    
    async def test_search_pubmed_sort_by_date(self, pubmed_session):
        """Test sorting functionality"""
        result = await pubmed_session.call_tool(
            "search_pubmed",
            {"query": "ALS", "max_results": 3, "sort": "date"}
        )
        
        assert len(result.content) > 0
        # Could add more specific assertions about date ordering
    
    async def test_search_pubmed_invalid_params(self, pubmed_session):
        """Test handling of invalid parameters"""
        # Missing required 'query' parameter should raise an error
        with pytest.raises((ValueError, TypeError, KeyError)):
            await pubmed_session.call_tool(
                "search_pubmed",
                {"max_results": 10}  # Missing required 'query'
            )
    
    async def test_get_paper_details(self, pubmed_session):
        """Test fetching specific paper details"""
        # Use a known PMID
        result = await pubmed_session.call_tool(
            "get_paper_details",
            {"pmid": "37123456"}  # Use a real PMID for integration test
        )
        
        assert len(result.content) > 0
    
    async def test_network_error_handling(self, pubmed_session):
        """Test graceful handling of network errors"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(
                side_effect=httpx.TimeoutException("Request timeout")
            )
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            with pytest.raises(httpx.TimeoutException):
                await pubmed_session.call_tool(
                    "search_pubmed",
                    {"query": "ALS"}
                )
    
    async def test_xml_parsing_robustness(self, pubmed_session):
        """Test handling of malformed XML"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_search_response = MagicMock()
            mock_search_response.json.return_value = {
                "esearchresult": {"idlist": ["12345"]}
            }
            
            mock_fetch_response = MagicMock()
            mock_fetch_response.text = "<invalid>xml</invalid>"  # Malformed
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(
                side_effect=[mock_search_response, mock_fetch_response]
            )
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            # Should handle gracefully
            result = await pubmed_session.call_tool(
                "search_pubmed",
                {"query": "test"}
            )
            
            # Should return error message or empty results
            assert len(result.content) > 0
    
    async def test_large_result_set(self, pubmed_session):
        """Test handling of large result sets"""
        result = await pubmed_session.call_tool(
            "search_pubmed",
            {"query": "ALS", "max_results": 50}
        )
        
        text = result.content[0].text
        # Should not crash, should handle pagination
        assert len(text) > 0
    
    async def test_special_characters_in_query(self, pubmed_session):
        """Test queries with special characters"""
        special_queries = [
            "ALS AND (SOD1 OR C9orf72)",
            "amyotrophic lateral sclerosis [MeSH Terms]",
            '"motor neuron disease" AND therapy'
        ]
        
        for query in special_queries:
            result = await pubmed_session.call_tool(
                "search_pubmed",
                {"query": query, "max_results": 5}
            )
            assert len(result.content) > 0
