"""Guide as an MCP Server — allows OpenClaw and other MCP clients to connect.

This exposes Guide's capabilities as MCP tools that can be called from
any MCP-compatible client (OpenClaw, Claude Desktop, etc.)
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

# MCP Server implementation using JSON-RPC 2.0 over stdio
# This follows the MCP specification: https://modelcontextprotocol.io/specification


class GuideMCPServer:
    """Guide exposed as an MCP server.

    Tools exposed:
    - start_session: Create a new guidance session
    - analyze_image: Send an image for analysis and guidance
    - send_message: Send a text message and get guidance
    - get_procedures: List available procedures
    - get_session_status: Get current session state

    Resources exposed:
    - guide://procedures - List of all procedures
    - guide://safety-rules - Safety rules by trade
    """

    def __init__(self) -> None:
        from guide.core.guide import AIGuide
        from guide.core.session import SessionManager
        from guide.core.knowledge import KnowledgeBase

        self._guide = AIGuide()
        self._sessions = SessionManager()
        self._knowledge = KnowledgeBase()
        self._active_session_id: str | None = None

    def get_server_info(self) -> dict:
        """Return MCP server capabilities."""
        return {
            "name": "guide",
            "version": "0.1.0",
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "resources": {},
                "prompts": {},
            },
        }

    def list_tools(self) -> list[dict]:
        """List all available MCP tools."""
        return [
            {
                "name": "start_session",
                "description": "Start a new guidance session for a physical task",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "trade": {
                            "type": "string",
                            "description": "Trade type: general, hvac, plumbing, electrical, automotive",
                            "enum": ["general", "hvac", "plumbing", "electrical", "automotive"],
                        },
                        "task": {
                            "type": "string",
                            "description": "What the worker wants to accomplish",
                        },
                    },
                    "required": ["task"],
                },
            },
            {
                "name": "analyze_image",
                "description": "Send an image of what you're looking at for AI guidance",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "image_base64": {
                            "type": "string",
                            "description": "Base64-encoded image data",
                        },
                        "message": {
                            "type": "string",
                            "description": "Optional question or context",
                        },
                    },
                    "required": ["image_base64"],
                },
            },
            {
                "name": "send_message",
                "description": "Send a text message to get guidance or ask a question",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Your message or question",
                        },
                    },
                    "required": ["message"],
                },
            },
            {
                "name": "next_step",
                "description": "Mark current step as complete and get the next instruction",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "get_help",
                "description": "Get additional help with the current step",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "get_session_status",
                "description": "Get current session state and progress",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "list_procedures",
                "description": "List available step-by-step procedures",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "trade": {
                            "type": "string",
                            "description": "Filter by trade",
                        },
                        "query": {
                            "type": "string",
                            "description": "Search query",
                        },
                    },
                },
            },
        ]

    def list_resources(self) -> list[dict]:
        """List available MCP resources."""
        return [
            {
                "uri": "guide://procedures",
                "name": "Available Procedures",
                "description": "List of all step-by-step procedures",
                "mimeType": "application/json",
            },
            {
                "uri": "guide://safety-rules",
                "name": "Safety Rules",
                "description": "Critical safety rules by trade",
                "mimeType": "application/json",
            },
        ]

    def list_prompts(self) -> list[dict]:
        """List available MCP prompts."""
        return [
            {
                "name": "hvac_diagnosis",
                "description": "Help diagnose an HVAC problem",
                "arguments": [
                    {"name": "symptoms", "description": "What's wrong?", "required": True},
                ],
            },
            {
                "name": "safety_check",
                "description": "Get safety checklist for a task",
                "arguments": [
                    {"name": "trade", "description": "Trade type", "required": True},
                    {"name": "task", "description": "What you're doing", "required": True},
                ],
            },
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict:
        """Execute an MCP tool call."""
        import base64

        if name == "start_session":
            trade = arguments.get("trade", "general")
            task = arguments.get("task", "")

            session = self._sessions.create_session(trade=trade)
            self._active_session_id = session.id

            response = self._guide.start_task(
                session=session,
                task_description=task,
            )

            return {
                "content": [
                    {
                        "type": "text",
                        "text": response.message,
                    }
                ],
                "metadata": {
                    "session_id": session.id,
                    "current_step": response.current_step,
                    "total_steps": response.total_steps,
                    "warnings": response.warnings,
                },
            }

        elif name == "analyze_image":
            session = self._get_active_session()
            if not session:
                return self._error("No active session. Call start_session first.")

            image_data = base64.b64decode(arguments["image_base64"])
            message = arguments.get("message")

            response = self._guide.process_image(
                session=session,
                image_data=image_data,
                user_message=message,
            )

            result = {
                "content": [{"type": "text", "text": response.message}],
                "metadata": {
                    "current_step": response.current_step,
                    "total_steps": response.total_steps,
                    "action": response.action,
                },
            }

            if response.warnings:
                result["metadata"]["warnings"] = response.warnings

            return result

        elif name == "send_message":
            session = self._get_active_session()
            if not session:
                return self._error("No active session. Call start_session first.")

            response = self._guide.process_message(
                session=session,
                message=arguments["message"],
            )

            return {
                "content": [{"type": "text", "text": response.message}],
                "metadata": {
                    "current_step": response.current_step,
                    "total_steps": response.total_steps,
                },
            }

        elif name == "next_step":
            session = self._get_active_session()
            if not session:
                return self._error("No active session.")

            response = self._guide.process_message(session=session, message="next")

            return {
                "content": [{"type": "text", "text": response.message}],
                "metadata": {
                    "current_step": response.current_step,
                    "total_steps": response.total_steps,
                },
            }

        elif name == "get_help":
            session = self._get_active_session()
            if not session:
                return self._error("No active session.")

            response = self._guide.process_message(session=session, message="help")

            return {
                "content": [{"type": "text", "text": response.message}],
            }

        elif name == "get_session_status":
            session = self._get_active_session()
            if not session:
                return {
                    "content": [{"type": "text", "text": "No active session."}],
                }

            status = {
                "session_id": session.id,
                "trade": session.trade,
                "state": session.state.value,
                "task": session.task_description,
                "current_step": session.current_step,
                "total_steps": len(session.step_progress) if session.step_progress else 0,
                "images_analyzed": session.images_analyzed,
            }

            return {
                "content": [{"type": "text", "text": json.dumps(status, indent=2)}],
            }

        elif name == "list_procedures":
            trade = arguments.get("trade")
            query = arguments.get("query")

            if query:
                procedures = self._knowledge.search_procedures(query, trade=trade)
            else:
                procedures = list(self._knowledge._procedures.values())
                if trade:
                    procedures = [p for p in procedures if p.trade == trade]

            result = [
                {
                    "id": p.id,
                    "name": p.name,
                    "trade": p.trade,
                    "description": p.description,
                    "steps": len(p.steps),
                }
                for p in procedures
            ]

            return {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
            }

        return self._error(f"Unknown tool: {name}")

    def read_resource(self, uri: str) -> dict:
        """Read an MCP resource."""
        if uri == "guide://procedures":
            procedures = [
                {
                    "id": p.id,
                    "name": p.name,
                    "trade": p.trade,
                    "description": p.description,
                    "difficulty": p.difficulty,
                    "steps": len(p.steps),
                }
                for p in self._knowledge._procedures.values()
            ]
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(procedures, indent=2),
                    }
                ]
            }

        elif uri == "guide://safety-rules":
            rules_by_trade: dict[str, list] = {}
            for rule in self._knowledge._safety_rules:
                if rule.trade not in rules_by_trade:
                    rules_by_trade[rule.trade] = []
                rules_by_trade[rule.trade].append({
                    "id": rule.id,
                    "rule": rule.rule,
                    "severity": rule.severity,
                    "category": rule.category,
                })
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(rules_by_trade, indent=2),
                    }
                ]
            }

        return {"contents": [], "error": f"Resource not found: {uri}"}

    def get_prompt(self, name: str, arguments: dict[str, str]) -> dict:
        """Get an MCP prompt."""
        if name == "hvac_diagnosis":
            symptoms = arguments.get("symptoms", "")
            return {
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": f"""I'm having an HVAC issue. Here are the symptoms:

{symptoms}

Please help me diagnose the problem and tell me what to check.
Start with the simplest/most common causes first.
Include any safety warnings.""",
                        },
                    }
                ],
            }

        elif name == "safety_check":
            trade = arguments.get("trade", "general")
            task = arguments.get("task", "")

            rules = self._knowledge.get_critical_safety_rules(trade)
            rules_text = "\n".join(f"- {r.rule}" for r in rules)

            return {
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": f"""I'm about to do this task: {task}

Trade: {trade}

Critical safety rules for this trade:
{rules_text}

Please give me a pre-task safety checklist specific to what I'm doing.""",
                        },
                    }
                ],
            }

        return {"messages": [], "error": f"Prompt not found: {name}"}

    def _get_active_session(self):
        """Get the current active session."""
        if self._active_session_id:
            return self._sessions.get_session(self._active_session_id)
        return None

    def _error(self, message: str) -> dict:
        """Return an error response."""
        return {
            "content": [{"type": "text", "text": f"Error: {message}"}],
            "isError": True,
        }


async def run_mcp_server():
    """Run Guide as an MCP server over stdio.

    This implements the JSON-RPC 2.0 protocol used by MCP.
    """
    server = GuideMCPServer()

    async def handle_request(request: dict) -> dict:
        """Handle a single JSON-RPC request."""
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")

        result = None
        error = None

        try:
            if method == "initialize":
                result = server.get_server_info()

            elif method == "tools/list":
                result = {"tools": server.list_tools()}

            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                result = server.call_tool(tool_name, arguments)

            elif method == "resources/list":
                result = {"resources": server.list_resources()}

            elif method == "resources/read":
                uri = params.get("uri", "")
                result = server.read_resource(uri)

            elif method == "prompts/list":
                result = {"prompts": server.list_prompts()}

            elif method == "prompts/get":
                name = params.get("name", "")
                arguments = params.get("arguments", {})
                result = server.get_prompt(name, arguments)

            elif method == "notifications/initialized":
                # Client notification, no response needed
                return None

            else:
                error = {"code": -32601, "message": f"Method not found: {method}"}

        except Exception as e:
            error = {"code": -32603, "message": str(e)}

        if request_id is None:
            return None  # Notification, no response

        response = {"jsonrpc": "2.0", "id": request_id}
        if error:
            response["error"] = error
        else:
            response["result"] = result

        return response

    # Read from stdin, write to stdout
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, asyncio.get_event_loop())

    while True:
        try:
            line = await reader.readline()
            if not line:
                break

            request = json.loads(line.decode())
            response = await handle_request(request)

            if response:
                writer.write((json.dumps(response) + "\n").encode())
                await writer.drain()

        except json.JSONDecodeError:
            continue
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"},
            }
            writer.write((json.dumps(error_response) + "\n").encode())
            await writer.drain()


def main():
    """Entry point for running Guide as MCP server."""
    asyncio.run(run_mcp_server())


if __name__ == "__main__":
    main()
