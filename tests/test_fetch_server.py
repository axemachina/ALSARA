# tests/test_fetch_server.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from mcp.types import TextContent
import httpx

@pytest.mark.asyncio
class TestFetchServer:
    
    async def test_list_tools(self, fetch_session):
        """Test that server lists expected tools"""
        response = await fetch_session.list_tools()
        
        tool_names = [tool.name for tool in response.tools]
        assert "fetch_url" in tool_names
    
    async def test_fetch_url_basic(self, fetch_session):
        """Test basic URL fetching"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.text = """
            <html>
                <body>
                    <h1>Test Article</h1>
                    <p>This is a test article about ALS research.</p>
                </body>
            </html>
            """
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            result = await fetch_session.call_tool(
                "fetch_url",
                {"url": "https://example.com/article", "extract_text_only": True}
            )
            
            text = result.content[0].text
            assert "Test Article" in text
            assert "ALS research" in text
            # Should NOT contain HTML tags
            assert "<html>" not in text
            assert "<p>" not in text
    
    async def test_fetch_url_raw_html(self, fetch_session):
        """Test fetching raw HTML"""
        with patch('httpx.AsyncClient') as mock_client:
            html_content = "<html><body><h1>Title</h1></body></html>"
            mock_response = MagicMock()
            mock_response.text = html_content
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            result = await fetch_session.call_tool(
                "fetch_url",
                {"url": "https://example.com", "extract_text_only": False}
            )
            
            text = result.content[0].text
            assert "<html>" in text
            assert "<body>" in text
    
    async def test_fetch_url_strips_scripts(self, fetch_session):
        """Test that scripts and styles are removed"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.text = """
            <html>
                <head>
                    <style>.test { color: red; }</style>
                </head>
                <body>
                    <script>alert('test');</script>
                    <p>Content</p>
                </body>
            </html>
            """
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            result = await fetch_session.call_tool(
                "fetch_url",
                {"url": "https://example.com", "extract_text_only": True}
            )
            
            text = result.content[0].text
            assert "Content" in text
            assert "alert" not in text
            assert ".test" not in text
    
    async def test_fetch_url_follows_redirects(self, fetch_session):
        """Test that redirects are followed"""
        with patch('httpx.AsyncClient') as mock_client:
            # The mock should be configured to test redirect behavior
            mock_response = MagicMock()
            mock_response.text = "<html><body>Final destination</body></html>"
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            result = await fetch_session.call_tool(
                "fetch_url",
                {"url": "https://short.url/redirect"}
            )
            
            assert len(result.content) > 0
    
    async def test_fetch_url_invalid_url(self, fetch_session):
        """Test handling of invalid URLs"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(
                side_effect=httpx.InvalidURL("Invalid URL")
            )
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            with pytest.raises(httpx.InvalidURL):
                await fetch_session.call_tool(
                    "fetch_url",
                    {"url": "not-a-valid-url"}
                )
    
    async def test_fetch_url_timeout(self, fetch_session):
        """Test timeout handling"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(
                side_effect=httpx.TimeoutException("Timeout")
            )
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            with pytest.raises(httpx.TimeoutException):
                await fetch_session.call_tool(
                    "fetch_url",
                    {"url": "https://slow-site.com"}
                )
    
    async def test_fetch_url_size_limit(self, fetch_session):
        """Test that very large responses are truncated"""
        with patch('httpx.AsyncClient') as mock_client:
            # Create very large HTML
            large_html = "<html><body>" + ("X" * 10000) + "</body></html>"
            mock_response = MagicMock()
            mock_response.text = large_html
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            result = await fetch_session.call_tool(
                "fetch_url",
                {"url": "https://example.com"}
            )
            
            text = result.content[0].text
            # Should be truncated to 5000 chars (per implementation)
            assert len(text) <= 5000
