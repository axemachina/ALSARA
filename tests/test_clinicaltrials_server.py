# tests/test_clinicaltrials_server.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from mcp.types import TextContent

@pytest.mark.asyncio
class TestClinicalTrialsServer:
    
    async def test_list_tools(self, clinicaltrials_session):
        """Test that server lists expected tools"""
        response = await clinicaltrials_session.list_tools()
        
        tool_names = [tool.name for tool in response.tools]
        assert "search_trials" in tool_names
        assert "get_trial_details" in tool_names
    
    async def test_search_trials_basic(self, clinicaltrials_session):
        """Test basic trial search"""
        result = await clinicaltrials_session.call_tool(
            "search_trials",
            {"condition": "ALS", "status": "recruiting", "max_results": 5}
        )
        
        assert len(result.content) > 0
        text = result.content[0].text
        assert "trial" in text.lower() or "nct" in text.lower()
    
    async def test_search_trials_with_mock(
        self, 
        clinicaltrials_session, 
        mock_clinicaltrials_response
    ):
        """Test trial search with mocked API"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_clinicaltrials_response
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            result = await clinicaltrials_session.call_tool(
                "search_trials",
                {"condition": "ALS", "status": "recruiting"}
            )
            
            text = result.content[0].text
            assert "NCT12345678" in text
            assert "RECRUITING" in text or "recruiting" in text.lower()
    
    async def test_search_trials_with_intervention(self, clinicaltrials_session):
        """Test searching with specific intervention"""
        result = await clinicaltrials_session.call_tool(
            "search_trials",
            {
                "condition": "ALS",
                "intervention": "tofersen",
                "status": "all",
                "max_results": 5
            }
        )
        
        assert len(result.content) > 0
    
    async def test_search_trials_all_statuses(self, clinicaltrials_session):
        """Test searching across all trial statuses"""
        statuses = ["recruiting", "active", "completed", "all"]
        
        for status in statuses:
            result = await clinicaltrials_session.call_tool(
                "search_trials",
                {"condition": "ALS", "status": status, "max_results": 3}
            )
            assert len(result.content) > 0
    
    async def test_search_trials_no_results(self, clinicaltrials_session):
        """Test handling of no results"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"studies": []}
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            result = await clinicaltrials_session.call_tool(
                "search_trials",
                {"condition": "extremelyunlikelycondition12345"}
            )
            
            text = result.content[0].text
            assert "no trials" in text.lower()
    
    async def test_get_trial_details(self, clinicaltrials_session):
        """Test fetching specific trial details"""
        # Use a known NCT ID
        result = await clinicaltrials_session.call_tool(
            "get_trial_details",
            {"nct_id": "NCT05021536"}  # Real tofersen trial
        )
        
        assert len(result.content) > 0
    
    async def test_get_trial_details_invalid_nct(self, clinicaltrials_session):
        """Test handling of invalid NCT ID"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.json.return_value = {"error": "Not found"}
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            # Should handle gracefully
            result = await clinicaltrials_session.call_tool(
                "get_trial_details",
                {"nct_id": "NCT00000000"}
            )
            
            assert len(result.content) > 0
    
    async def test_api_rate_limiting(self, clinicaltrials_session):
        """Test behavior under rate limiting"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 429
            mock_response.text = "Rate limit exceeded"
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            # Should handle rate limiting gracefully
            with pytest.raises(Exception):  # Or specific rate limit exception
                await clinicaltrials_session.call_tool(
                    "search_trials",
                    {"condition": "ALS"}
                )
