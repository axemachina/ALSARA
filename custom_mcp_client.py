"""
Custom MCP client using direct subprocess communication.
This bypasses the buggy stdio_client from mcp.client.stdio.
"""

import asyncio
import json
import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MCPClient:
    """Custom MCP client using direct subprocess communication"""

    def __init__(self, server_script: str, server_name: str):
        self.server_script = server_script
        self.server_name = server_name
        self.process: Optional[subprocess.Popen] = None
        self.message_id = 0
        self._initialized = False
        self.script_path = server_script  # Store for potential restart

    async def start(self):
        """Start the MCP server subprocess"""
        logger.info(f"Starting MCP server: {self.server_name}")

        # HF Spaces does not capture subprocess stderr even when inherited,
        # so we capture via PIPE and relay each line through the parent
        # process's logger (which we've confirmed does reach Space logs).
        self.process = subprocess.Popen(
            [sys.executable, self.server_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line-buffered I/O to prevent 8KB truncation
        )
        self._start_stderr_forwarder()

        # Initialize the session
        await self._initialize()
        logger.info(f"Successfully started MCP server: {self.server_name}")

    def _start_stderr_forwarder(self):
        """Read subprocess stderr in a daemon thread and forward to parent logger.

        Without this, logs from inside MCP server subprocesses never reach HF
        Space logs — HF only captures the parent Gradio process's output.
        """
        proc = self.process
        name = self.server_name

        def _pump():
            try:
                for line in iter(proc.stderr.readline, ""):
                    if not line:
                        break
                    logger.info(f"[{name}] {line.rstrip()}")
            except Exception as e:
                logger.warning(f"[{name}] stderr forwarder stopped: {e}")

        t = threading.Thread(target=_pump, name=f"mcp-stderr-{name}", daemon=True)
        t.start()

    async def _initialize(self):
        """Initialize the MCP session"""
        init_message = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "als-research-agent",
                    "version": "1.0.0"
                }
            }
        }

        response = await self._send_request(init_message)
        if "result" in response:
            self._initialized = True
            logger.info(f"Initialized {self.server_name}: {response['result'].get('serverInfo', {})}")
        else:
            raise Exception(f"Initialization failed: {response}")

    def _next_id(self) -> int:
        """Get next message ID"""
        self.message_id += 1
        return self.message_id

    async def _send_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Send a JSON-RPC request and wait for response"""
        if not self.process:
            raise RuntimeError("Server not started")

        # Check if process is still alive
        if self.process.poll() is not None:
            # Process has terminated
            raise RuntimeError(f"Server {self.server_name} has terminated unexpectedly")

        # Send request
        request_json = json.dumps(message) + "\n"
        self.process.stdin.write(request_json)
        self.process.stdin.flush()

        # Read response with timeout
        try:
            response_line = await asyncio.wait_for(
                asyncio.to_thread(self.process.stdout.readline),
                timeout=60.0  # Extended timeout for LlamaIndex/RAG server initialization
            )

            if not response_line:
                raise Exception("Server closed stdout")

            return json.loads(response_line)
        except asyncio.TimeoutError:
            raise Exception("Request timed out")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools"""
        if not self._initialized:
            raise RuntimeError("Client not initialized")

        message = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
            "params": {}
        }

        response = await self._send_request(message)
        if "result" in response:
            return response["result"].get("tools", [])
        else:
            raise Exception(f"List tools failed: {response}")

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool"""
        if not self._initialized:
            raise RuntimeError("Client not initialized")

        message = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        response = await self._send_request(message)
        if "result" in response:
            # Extract result from response
            result = response["result"]

            # Handle different response formats
            if isinstance(result, dict):
                # New format with 'result' field
                if "result" in result:
                    return result["result"]
                # Content array format
                elif "content" in result:
                    content = result["content"]
                    if isinstance(content, list) and len(content) > 0:
                        return content[0].get("text", str(content))
                    return str(content)
                else:
                    return str(result)
            else:
                return str(result)
        else:
            error = response.get("error", {})
            raise Exception(f"Tool call failed: {error.get('message', response)}")

    async def close(self):
        """Close the MCP client and terminate server"""
        if self.process:
            logger.info(f"Closing MCP server: {self.server_name}")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None
            self._initialized = False


class MCPClientManager:
    """Manage multiple MCP clients"""

    def __init__(self):
        self.clients: Dict[str, MCPClient] = {}

    async def add_server(self, name: str, script_path: str):
        """Add and start an MCP server"""
        client = MCPClient(script_path, name)
        await client.start()
        self.clients[name] = client
        logger.info(f"Added MCP server: {name}")

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool on a specific server"""
        if server_name not in self.clients:
            raise ValueError(f"Server not found: {server_name}")

        return await self.clients[server_name].call_tool(tool_name, arguments)

    async def list_all_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        """List tools from all servers, handling failures gracefully"""
        all_tools = {}
        failed_servers = []

        for name, client in self.clients.items():
            try:
                tools = await client.list_tools()
                for tool in tools:
                    tool['server'] = name  # Add server info to each tool
                all_tools[name] = tools
            except Exception as e:
                logger.error(f"Failed to list tools from server {name}: {e}")
                failed_servers.append(name)
                # Continue with other servers instead of failing entirely
                all_tools[name] = []

        if failed_servers:
            logger.warning(f"Some servers failed to respond: {', '.join(failed_servers)}")
            # Try to restart failed servers
            for server_name in failed_servers:
                try:
                    client = self.clients[server_name]
                    script_path = client.script_path if hasattr(client, 'script_path') else None
                    if script_path:
                        logger.info(f"Attempting to restart {server_name} server...")
                        await client.close()
                        # Re-add the server (which will restart it)
                        await self.add_server(server_name, script_path)
                        # Try listing tools again after restart
                        tools = await self.clients[server_name].list_tools()
                        for tool in tools:
                            tool['server'] = server_name
                        all_tools[server_name] = tools
                        logger.info(f"Successfully restarted {server_name} server")
                except Exception as restart_error:
                    logger.error(f"Failed to restart {server_name}: {restart_error}")
                    # Remove the failed server from clients to prevent further errors
                    if server_name in self.clients:
                        del self.clients[server_name]

        return all_tools

    async def close_all(self):
        """Close all MCP clients"""
        for client in self.clients.values():
            await client.close()
        self.clients.clear()
        logger.info("All MCP servers closed")
