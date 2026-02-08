"""MCP (Model Context Protocol) integration for Guide.

Connects Guide to external tools, data sources, and services via MCP servers.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPTool:
    """An MCP tool that can be called."""

    name: str
    description: str
    input_schema: dict[str, Any]
    server: str  # Which MCP server provides this tool


@dataclass
class MCPResource:
    """An MCP resource that can be read."""

    uri: str
    name: str
    description: str
    mime_type: str = "text/plain"


@dataclass
class MCPToolResult:
    """Result from calling an MCP tool."""

    success: bool
    content: Any
    error: str | None = None


class MCPServer(ABC):
    """Base class for MCP server connections."""

    name: str
    description: str

    @abstractmethod
    def list_tools(self) -> list[MCPTool]:
        """List available tools from this server."""

    @abstractmethod
    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> MCPToolResult:
        """Call a tool with the given arguments."""

    @abstractmethod
    def list_resources(self) -> list[MCPResource]:
        """List available resources."""

    @abstractmethod
    def read_resource(self, uri: str) -> str:
        """Read a resource by URI."""


class HomeAssistantMCP(MCPServer):
    """MCP server for Home Assistant smart home control.

    Enables Guide to:
    - Turn off power to equipment before repairs
    - Control HVAC systems
    - Operate smart locks, lights, etc.
    """

    name = "home_assistant"
    description = "Control smart home devices"

    def __init__(self, base_url: str, token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name="turn_off_device",
                description="Turn off a smart device (switch, light, HVAC, etc.)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Home Assistant entity ID"},
                    },
                    "required": ["entity_id"],
                },
                server=self.name,
            ),
            MCPTool(
                name="turn_on_device",
                description="Turn on a smart device",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Home Assistant entity ID"},
                    },
                    "required": ["entity_id"],
                },
                server=self.name,
            ),
            MCPTool(
                name="get_device_state",
                description="Get current state of a device",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Home Assistant entity ID"},
                    },
                    "required": ["entity_id"],
                },
                server=self.name,
            ),
            MCPTool(
                name="set_hvac_mode",
                description="Set HVAC mode (heat, cool, off, auto)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string"},
                        "mode": {"type": "string", "enum": ["heat", "cool", "off", "auto"]},
                    },
                    "required": ["entity_id", "mode"],
                },
                server=self.name,
            ),
        ]

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> MCPToolResult:
        import httpx

        headers = {"Authorization": f"Bearer {self._token}"}

        try:
            if tool_name == "turn_off_device":
                domain = arguments["entity_id"].split(".")[0]
                resp = httpx.post(
                    f"{self._base_url}/api/services/{domain}/turn_off",
                    headers=headers,
                    json={"entity_id": arguments["entity_id"]},
                    timeout=10,
                )
                resp.raise_for_status()
                return MCPToolResult(success=True, content=f"Turned off {arguments['entity_id']}")

            elif tool_name == "turn_on_device":
                domain = arguments["entity_id"].split(".")[0]
                resp = httpx.post(
                    f"{self._base_url}/api/services/{domain}/turn_on",
                    headers=headers,
                    json={"entity_id": arguments["entity_id"]},
                    timeout=10,
                )
                resp.raise_for_status()
                return MCPToolResult(success=True, content=f"Turned on {arguments['entity_id']}")

            elif tool_name == "get_device_state":
                resp = httpx.get(
                    f"{self._base_url}/api/states/{arguments['entity_id']}",
                    headers=headers,
                    timeout=10,
                )
                resp.raise_for_status()
                state = resp.json()
                return MCPToolResult(success=True, content=state)

            elif tool_name == "set_hvac_mode":
                resp = httpx.post(
                    f"{self._base_url}/api/services/climate/set_hvac_mode",
                    headers=headers,
                    json={
                        "entity_id": arguments["entity_id"],
                        "hvac_mode": arguments["mode"],
                    },
                    timeout=10,
                )
                resp.raise_for_status()
                return MCPToolResult(
                    success=True,
                    content=f"Set {arguments['entity_id']} to {arguments['mode']}",
                )

            return MCPToolResult(success=False, content=None, error=f"Unknown tool: {tool_name}")

        except Exception as e:
            return MCPToolResult(success=False, content=None, error=str(e))

    def list_resources(self) -> list[MCPResource]:
        return []

    def read_resource(self, uri: str) -> str:
        return ""


class PartsDatabaseMCP(MCPServer):
    """MCP server for parts lookup and ordering.

    Enables Guide to:
    - Look up part specifications
    - Find compatible replacements
    - Check inventory
    - Create purchase orders
    """

    name = "parts_database"
    description = "Look up parts and specifications"

    def __init__(self) -> None:
        # In production, this would connect to a real parts database
        self._parts: dict[str, dict] = {
            "CAP-35-5": {
                "name": "Run Capacitor 35/5 MFD",
                "type": "capacitor",
                "specs": {"mfd": "35/5", "voltage": "440V", "type": "dual run"},
                "compatible_with": ["CAP-35-5-440", "CAP-35-5-370"],
                "price": 24.99,
            },
            "FILTER-20x25x1": {
                "name": "Air Filter 20x25x1",
                "type": "filter",
                "specs": {"size": "20x25x1", "merv": 8},
                "compatible_with": ["FILTER-20x25x1-MERV8", "FILTER-20x25x1-MERV11"],
                "price": 12.99,
            },
        }

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name="lookup_part",
                description="Look up a part by part number or description",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Part number or search term"},
                    },
                    "required": ["query"],
                },
                server=self.name,
            ),
            MCPTool(
                name="find_compatible_parts",
                description="Find compatible replacement parts",
                input_schema={
                    "type": "object",
                    "properties": {
                        "part_number": {"type": "string"},
                    },
                    "required": ["part_number"],
                },
                server=self.name,
            ),
            MCPTool(
                name="check_inventory",
                description="Check if a part is in stock",
                input_schema={
                    "type": "object",
                    "properties": {
                        "part_number": {"type": "string"},
                        "location": {"type": "string", "description": "Warehouse or truck ID"},
                    },
                    "required": ["part_number"],
                },
                server=self.name,
            ),
        ]

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> MCPToolResult:
        if tool_name == "lookup_part":
            query = arguments["query"].upper()
            for part_num, part in self._parts.items():
                if query in part_num or query.lower() in part["name"].lower():
                    return MCPToolResult(success=True, content={part_num: part})
            return MCPToolResult(success=True, content={}, error="Part not found")

        elif tool_name == "find_compatible_parts":
            part_num = arguments["part_number"].upper()
            if part_num in self._parts:
                compatible = self._parts[part_num].get("compatible_with", [])
                return MCPToolResult(success=True, content=compatible)
            return MCPToolResult(success=False, content=None, error="Part not found")

        elif tool_name == "check_inventory":
            # Simulated inventory check
            return MCPToolResult(
                success=True,
                content={"in_stock": True, "quantity": 5, "location": "Truck #42"},
            )

        return MCPToolResult(success=False, content=None, error=f"Unknown tool: {tool_name}")

    def list_resources(self) -> list[MCPResource]:
        return [
            MCPResource(
                uri="parts://catalog/hvac",
                name="HVAC Parts Catalog",
                description="Full HVAC parts catalog with specs",
            ),
            MCPResource(
                uri="parts://catalog/electrical",
                name="Electrical Parts Catalog",
                description="Electrical components catalog",
            ),
        ]

    def read_resource(self, uri: str) -> str:
        if "hvac" in uri:
            return json.dumps({k: v for k, v in self._parts.items()}, indent=2)
        return ""


class MessagingMCP(MCPServer):
    """MCP server for messaging integrations (OpenClaw-style).

    Enables Guide to:
    - Send updates to worker's preferred messaging app
    - Alert supervisors
    - Request remote assistance
    """

    name = "messaging"
    description = "Send messages via various platforms"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name="send_message",
                description="Send a message to a user",
                input_schema={
                    "type": "object",
                    "properties": {
                        "platform": {
                            "type": "string",
                            "enum": ["sms", "whatsapp", "slack", "teams", "email"],
                        },
                        "recipient": {"type": "string"},
                        "message": {"type": "string"},
                    },
                    "required": ["platform", "recipient", "message"],
                },
                server=self.name,
            ),
            MCPTool(
                name="request_help",
                description="Request help from a supervisor or expert",
                input_schema={
                    "type": "object",
                    "properties": {
                        "urgency": {"type": "string", "enum": ["low", "medium", "high"]},
                        "description": {"type": "string"},
                        "image_url": {"type": "string"},
                    },
                    "required": ["description"],
                },
                server=self.name,
            ),
            MCPTool(
                name="log_job_update",
                description="Log a job status update",
                input_schema={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "status": {"type": "string"},
                        "notes": {"type": "string"},
                    },
                    "required": ["job_id", "status"],
                },
                server=self.name,
            ),
        ]

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> MCPToolResult:
        # In production, these would actually send messages
        if tool_name == "send_message":
            return MCPToolResult(
                success=True,
                content=f"Message sent via {arguments['platform']} to {arguments['recipient']}",
            )
        elif tool_name == "request_help":
            return MCPToolResult(
                success=True,
                content=f"Help request submitted: {arguments['description']}",
            )
        elif tool_name == "log_job_update":
            return MCPToolResult(
                success=True,
                content=f"Job {arguments['job_id']} updated to {arguments['status']}",
            )

        return MCPToolResult(success=False, content=None, error=f"Unknown tool: {tool_name}")

    def list_resources(self) -> list[MCPResource]:
        return []

    def read_resource(self, uri: str) -> str:
        return ""


class MCPHub:
    """Central hub for managing MCP server connections.

    Usage:
        hub = MCPHub()
        hub.register(HomeAssistantMCP(url, token))
        hub.register(PartsDatabaseMCP())

        # List all available tools
        tools = hub.list_all_tools()

        # Call a tool
        result = hub.call_tool("home_assistant", "turn_off_device", {"entity_id": "switch.hvac"})
    """

    def __init__(self) -> None:
        self._servers: dict[str, MCPServer] = {}

    def register(self, server: MCPServer) -> None:
        """Register an MCP server."""
        self._servers[server.name] = server

    def unregister(self, server_name: str) -> None:
        """Unregister an MCP server."""
        self._servers.pop(server_name, None)

    def list_servers(self) -> list[str]:
        """List registered server names."""
        return list(self._servers.keys())

    def list_all_tools(self) -> list[MCPTool]:
        """List all tools from all servers."""
        tools = []
        for server in self._servers.values():
            tools.extend(server.list_tools())
        return tools

    def list_all_resources(self) -> list[MCPResource]:
        """List all resources from all servers."""
        resources = []
        for server in self._servers.values():
            resources.extend(server.list_resources())
        return resources

    def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> MCPToolResult:
        """Call a tool on a specific server."""
        server = self._servers.get(server_name)
        if not server:
            return MCPToolResult(
                success=False,
                content=None,
                error=f"Server not found: {server_name}",
            )
        return server.call_tool(tool_name, arguments)

    def read_resource(self, server_name: str, uri: str) -> str:
        """Read a resource from a specific server."""
        server = self._servers.get(server_name)
        if not server:
            return ""
        return server.read_resource(uri)

    def get_tools_for_llm(self) -> list[dict]:
        """Get all tools formatted for Claude's tool use API."""
        tools = []
        for tool in self.list_all_tools():
            tools.append({
                "name": f"{tool.server}__{tool.name}",
                "description": f"[{tool.server}] {tool.description}",
                "input_schema": tool.input_schema,
            })
        return tools
