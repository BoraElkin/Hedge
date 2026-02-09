"""AI Guide with tool use — can call MCP tools during guidance.

This extends the base AIGuide to use Claude's tool use capabilities,
allowing it to:
- Control smart devices (turn off power before electrical work)
- Look up parts and specifications
- Send messages to supervisors
- Check inventory
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import anthropic

from guide.config import get_settings
from guide.core.guide import AIGuide, GuideResponse
from guide.core.knowledge import KnowledgeBase, Procedure, Step
from guide.core.mcp import MCPHub, MCPToolResult
from guide.core.session import Session
from guide.core.vision import VisionAnalyzer, VisualAnalysis


@dataclass
class ToolCall:
    """A tool call made by the AI."""

    tool_name: str
    arguments: dict[str, Any]
    result: MCPToolResult | None = None


@dataclass
class ToolGuideResponse(GuideResponse):
    """Response that includes tool calls made."""

    tool_calls: list[ToolCall] = field(default_factory=list)


class ToolUsingGuide(AIGuide):
    """AI Guide that can use MCP tools during guidance.

    This enables powerful capabilities like:
    - "Let me turn off power to that circuit for you"
    - "I found that part - it's a 35/5 MFD capacitor, you have 3 in stock"
    - "I've alerted your supervisor that you need help"
    """

    def __init__(self, mcp_hub: MCPHub | None = None) -> None:
        super().__init__()
        self._mcp = mcp_hub or MCPHub()

    def process_with_tools(
        self,
        session: Session,
        image_data: bytes | None = None,
        user_message: str | None = None,
    ) -> ToolGuideResponse:
        """Process input with tool use capabilities.

        The AI can decide to call tools based on the situation, e.g.:
        - Detect electrical work → offer to turn off power
        - See a part → look up specifications
        - Worker stuck → alert supervisor
        """
        # Build the context
        procedure = None
        current_step = None
        if session.procedure_id:
            procedure = self._knowledge.get_procedure(session.procedure_id)
            if procedure and session.current_step <= len(procedure.steps):
                current_step = procedure.steps[session.current_step - 1]

        # Analyze image if provided
        analysis = None
        if image_data:
            analysis = self._vision.analyze(
                image_data,
                task_context=session.task_description,
                current_step=current_step.instruction if current_step else None,
                trade=session.trade,
            )
            session.last_visual_context = {
                "description": analysis.context.description,
                "objects": analysis.context.objects_detected,
                "hazards": analysis.context.hazards,
            }
            session.images_analyzed += 1

        # Build messages for Claude with tool use
        system = self._build_tool_system_prompt(session, procedure, current_step)
        messages = self._build_messages(session, analysis, user_message)
        tools = self._get_claude_tools()

        # Call Claude with tools
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system,
            messages=messages,
            tools=tools if tools else anthropic.NOT_GIVEN,
        )

        # Process response and handle tool calls
        tool_calls: list[ToolCall] = []
        final_text = ""

        for block in response.content:
            if block.type == "text":
                final_text += block.text
            elif block.type == "tool_use":
                # Execute the tool call
                tool_call = self._execute_tool(block.name, block.input)
                tool_calls.append(tool_call)

        # If there were tool calls, continue the conversation with results
        if tool_calls and response.stop_reason == "tool_use":
            final_text = self._continue_with_tool_results(
                messages, response, tool_calls, system, tools
            )

        # Record in session
        if user_message or image_data:
            session.add_message("user", user_message or "[sent image]", image_data=image_data)
        session.add_message("assistant", final_text)

        return ToolGuideResponse(
            message=final_text,
            action=analysis.suggested_action if analysis else None,
            warnings=analysis.warnings if analysis and analysis.warnings else None,
            current_step=session.current_step if procedure else None,
            total_steps=len(procedure.steps) if procedure else None,
            step_instruction=current_step.instruction if current_step else None,
            visual_analysis=analysis,
            tool_calls=tool_calls,
        )

    def _build_tool_system_prompt(
        self,
        session: Session,
        procedure: Procedure | None,
        current_step: Step | None,
    ) -> str:
        """Build system prompt that includes tool use instructions."""
        base = f"""You are an expert {session.trade} technician providing real-time guidance to a worker.
You can see through their camera and have access to tools that let you take actions.

Current task: {session.task_description or 'No specific task'}
"""
        if procedure:
            base += f"""
Procedure: {procedure.name}
Step {session.current_step}/{len(procedure.steps)}: {current_step.instruction if current_step else 'N/A'}
"""

        base += """
AVAILABLE TOOLS:
You have access to tools that can:
- Control smart devices (turn off power, HVAC, etc.) - USE THESE FOR SAFETY
- Look up parts and specifications
- Check inventory
- Send messages to supervisors
- Log job updates

WHEN TO USE TOOLS:
- ALWAYS offer to turn off power before electrical work
- Look up parts when you see one that needs identification
- Alert supervisor if worker is stuck or in danger
- Check inventory when worker needs a part

Be proactive about safety. If you can make the worker safer by using a tool, DO IT.

Keep your responses concise. Workers need quick, actionable guidance."""

        return base

    def _build_messages(
        self,
        session: Session,
        analysis: VisualAnalysis | None,
        user_message: str | None,
    ) -> list[dict]:
        """Build messages array for Claude."""
        messages = []

        # Include recent conversation context
        for msg in session.messages[-6:]:
            if msg.role in ("user", "assistant"):
                messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        # Add current input
        content = []
        if analysis:
            content.append({
                "type": "text",
                "text": f"[Camera view analysis]\n{analysis.raw_response}",
            })
        if user_message:
            content.append({
                "type": "text",
                "text": f"Worker says: {user_message}",
            })

        if content:
            messages.append({
                "role": "user",
                "content": content if len(content) > 1 else content[0]["text"],
            })

        return messages

    def _get_claude_tools(self) -> list[dict]:
        """Get tools formatted for Claude's API."""
        tools = []

        for tool in self._mcp.list_all_tools():
            tools.append({
                "name": f"{tool.server}__{tool.name}",
                "description": tool.description,
                "input_schema": tool.input_schema,
            })

        # Add built-in guidance tools
        tools.extend([
            {
                "name": "suggest_safety_action",
                "description": "Suggest a safety action the worker should take",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "description": "The safety action"},
                        "urgency": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                    },
                    "required": ["action", "urgency"],
                },
            },
            {
                "name": "identify_part",
                "description": "Identify a part visible in the image",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string", "description": "Part description"},
                        "possible_part_numbers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Possible part numbers",
                        },
                    },
                    "required": ["description"],
                },
            },
        ])

        return tools

    def _execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolCall:
        """Execute a tool call."""
        tool_call = ToolCall(tool_name=tool_name, arguments=arguments)

        # Handle MCP tools (format: server__tool_name)
        if "__" in tool_name:
            server_name, actual_tool = tool_name.split("__", 1)
            result = self._mcp.call_tool(server_name, actual_tool, arguments)
            tool_call.result = result
        else:
            # Built-in tools
            if tool_name == "suggest_safety_action":
                tool_call.result = MCPToolResult(
                    success=True,
                    content=f"Safety suggestion: {arguments.get('action')} (urgency: {arguments.get('urgency')})",
                )
            elif tool_name == "identify_part":
                tool_call.result = MCPToolResult(
                    success=True,
                    content=f"Part identified: {arguments.get('description')}",
                )
            else:
                tool_call.result = MCPToolResult(
                    success=False,
                    content=None,
                    error=f"Unknown tool: {tool_name}",
                )

        return tool_call

    def _continue_with_tool_results(
        self,
        messages: list[dict],
        initial_response,
        tool_calls: list[ToolCall],
        system: str,
        tools: list[dict],
    ) -> str:
        """Continue conversation after tool calls with results."""
        # Add assistant's tool use to messages
        messages.append({
            "role": "assistant",
            "content": initial_response.content,
        })

        # Add tool results
        tool_results = []
        for block in initial_response.content:
            if block.type == "tool_use":
                # Find matching tool call
                for tc in tool_calls:
                    if tc.tool_name == block.name:
                        result_content = (
                            tc.result.content if tc.result and tc.result.success
                            else f"Error: {tc.result.error if tc.result else 'Unknown error'}"
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(result_content),
                        })
                        break

        messages.append({
            "role": "user",
            "content": tool_results,
        })

        # Get final response
        final_response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system,
            messages=messages,
            tools=tools,
        )

        # Extract text from final response
        for block in final_response.content:
            if block.type == "text":
                return block.text

        return "I've completed the requested actions."


class SmartGuide(ToolUsingGuide):
    """Full-featured guide with automatic safety interventions.

    This guide proactively:
    - Offers to turn off power for electrical work
    - Warns about hazards before they're a problem
    - Looks up parts automatically
    - Alerts supervisors when needed
    """

    def __init__(self, mcp_hub: MCPHub | None = None) -> None:
        super().__init__(mcp_hub)
        self._auto_safety = True
        self._auto_parts_lookup = True

    def process_with_tools(
        self,
        session: Session,
        image_data: bytes | None = None,
        user_message: str | None = None,
    ) -> ToolGuideResponse:
        """Process with automatic safety interventions."""

        # Check for automatic safety interventions before processing
        if image_data and self._auto_safety:
            pre_check = self._safety_pre_check(session, image_data)
            if pre_check:
                # Insert safety warning into the flow
                session.add_message(
                    "system",
                    f"[AUTO-SAFETY] {pre_check}",
                )

        # Normal processing with tools
        response = super().process_with_tools(session, image_data, user_message)

        return response

    def _safety_pre_check(self, session: Session, image_data: bytes) -> str | None:
        """Quick safety check before main analysis."""
        # Use a quick vision check for hazards
        hazard_check = self._vision.quick_check(
            image_data,
            "Are there any immediate safety hazards visible? "
            "Look for: exposed wires, water near electricity, unstable structures, "
            "gas leaks, sharp edges, missing safety equipment. "
            "Reply with SAFE if no hazards, or describe the hazard briefly.",
        )

        if "SAFE" not in hazard_check.upper():
            return hazard_check

        return None
