"""
MCP (Model Context Protocol) Handler
Allows integration with MCP servers for extended functionality
"""
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class MCPHandler:
    """Handle MCP server connections and tool calls"""
    
    def __init__(self):
        self.mcp_servers: Dict[str, Any] = {}
        self.enabled = False
    
    def add_mcp_server(self, server_name: str, server_config: Dict[str, Any]):
        """
        Add an MCP server configuration
        
        Args:
            server_name: Name identifier for the server
            server_config: Configuration dict with:
                - url: Server URL
                - api_key: Optional API key
                - tools: List of available tools
        """
        self.mcp_servers[server_name] = server_config
        self.enabled = True
        logger.info(f"MCP server '{server_name}' added")
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """
        Get list of all available tools from all MCP servers
        
        Returns:
            List of tool definitions compatible with OpenAI function calling
        """
        tools = []
        
        for server_name, config in self.mcp_servers.items():
            server_tools = config.get("tools", [])
            for tool in server_tools:
                # Format tool for OpenAI-compatible API (Groq supports this)
                tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {})
                    }
                })
        
        return tools
    
    async def call_mcp_tool(
        self, 
        tool_name: str, 
        arguments: Dict[str, Any]
    ) -> Optional[Any]:
        """
        Call a tool from an MCP server
        
        Args:
            tool_name: Name of the tool to call
            arguments: Arguments for the tool
            
        Returns:
            Tool response or None
        """
        import httpx
        
        # Find which server has this tool
        for server_name, config in self.mcp_servers.items():
            server_tools = config.get("tools", [])
            for tool in server_tools:
                if tool.get("name") == tool_name:
                    url = config.get("url")
                    api_key = config.get("api_key")
                    
                    logger.info(f"Calling MCP tool '{tool_name}' from server '{server_name}'")
                    
                    # Make HTTP request to MCP server
                    try:
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            headers = {"Content-Type": "application/json"}
                            if api_key:
                                headers["Authorization"] = f"Bearer {api_key}"
                            
                            # MCP servers typically use POST requests
                            response = await client.post(
                                f"{url}/tools/{tool_name}",
                                json={"arguments": arguments},
                                headers=headers
                            )
                            response.raise_for_status()
                            
                            result = response.json()
                            logger.info(f"MCP tool '{tool_name}' executed successfully")
                            return result
                    
                    except httpx.HTTPError as e:
                        logger.error(f"Error calling MCP tool '{tool_name}': {e}")
                        return {"error": str(e), "tool": tool_name}
        
        logger.warning(f"MCP tool '{tool_name}' not found in any registered server")
        return None

