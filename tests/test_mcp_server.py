#!/usr/bin/env python3
"""Minimal MCP server for testing using FastMCP"""

from mcp.server.fastmcp import FastMCP

# Create server
mcp = FastMCP("test-server")


@mcp.tool()
def test_tool(message: str) -> str:
    """A simple test tool"""
    return f"Received: {message}"


if __name__ == "__main__":
    # Run with stdio transport
    mcp.run(transport="stdio")
