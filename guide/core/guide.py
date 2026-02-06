"""AI Guide - the main orchestrator that sees, reasons, and guides."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import anthropic

from guide.config import get_settings
from guide.core.knowledge import KnowledgeBase, Procedure, Step
from guide.core.session import Session, SessionState
from guide.core.vision import VisionAnalyzer, VisualAnalysis


@dataclass
class GuideResponse:
    """Response from the AI Guide."""

    message: str  # What to say to the worker
    action: str | None = None  # Suggested next action
    warnings: list[str] | None = None  # Safety warnings
    current_step: int | None = None  # Current step number
    total_steps: int | None = None  # Total steps in procedure
    step_instruction: str | None = None  # Current step instruction
    visual_analysis: VisualAnalysis | None = None
    confidence: float = 0.9


class AIGuide:
    """The AI Guide that orchestrates vision, knowledge, and conversation.

    This is the core "brain" - it sees through the worker's camera,
    understands context, retrieves relevant knowledge, and provides
    real-time guidance.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.default_model
        self._vision = VisionAnalyzer()
        self._knowledge = KnowledgeBase()

    def start_task(
        self,
        session: Session,
        task_description: str,
        image_data: bytes | None = None,
    ) -> GuideResponse:
        """Start a new task. Can include an image of the work area.

        Args:
            session: The current work session
            task_description: What the worker wants to accomplish
            image_data: Optional image of the current situation
        """
        session.task_description = task_description
        session.state = SessionState.BRIEFING

        # Search for matching procedures
        procedures = self._knowledge.search_procedures(
            task_description,
            trade=session.trade,
            limit=3,
        )

        # Get safety rules
        safety_rules = self._knowledge.get_critical_safety_rules(session.trade)

        # If we have an image, analyze it
        visual_context = ""
        analysis = None
        if image_data:
            analysis = self._vision.analyze(
                image_data,
                task_context=task_description,
                trade=session.trade,
            )
            visual_context = f"\nI can see: {analysis.context.description}"
            session.last_visual_context = {
                "description": analysis.context.description,
                "objects": analysis.context.objects_detected,
                "hazards": analysis.context.hazards,
            }
            session.images_analyzed += 1

        # Build response
        response = self._generate_task_start_response(
            task_description=task_description,
            procedures=procedures,
            safety_rules=safety_rules,
            visual_context=visual_context,
            session=session,
        )

        # If we found a matching procedure, set it up
        if procedures:
            best_match = procedures[0]
            session.start_procedure(best_match.id, len(best_match.steps))
            return GuideResponse(
                message=response,
                warnings=[r.rule for r in safety_rules],
                current_step=1,
                total_steps=len(best_match.steps),
                step_instruction=best_match.steps[0].instruction,
                visual_analysis=analysis,
            )

        return GuideResponse(
            message=response,
            warnings=[r.rule for r in safety_rules],
            visual_analysis=analysis,
        )

    def process_image(
        self,
        session: Session,
        image_data: bytes,
        user_message: str | None = None,
    ) -> GuideResponse:
        """Process a new image from the worker's camera.

        This is the main interaction loop - the worker shows what they're
        looking at, and the guide responds with what to do next.
        """
        # Get current procedure and step if any
        procedure = None
        current_step = None
        if session.procedure_id:
            procedure = self._knowledge.get_procedure(session.procedure_id)
            if procedure and session.current_step <= len(procedure.steps):
                current_step = procedure.steps[session.current_step - 1]

        # Analyze the image
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

        # Check for safety hazards first
        if analysis.warnings:
            session.add_message("assistant", f"⚠️ SAFETY: {', '.join(analysis.warnings)}")

        # Generate contextual guidance
        response = self._generate_guidance_response(
            session=session,
            analysis=analysis,
            procedure=procedure,
            current_step=current_step,
            user_message=user_message,
        )

        session.add_message("user", user_message or "[sent image]", image_data=image_data)
        session.add_message("assistant", response)

        return GuideResponse(
            message=response,
            action=analysis.suggested_action,
            warnings=analysis.warnings if analysis.warnings else None,
            current_step=session.current_step if procedure else None,
            total_steps=len(procedure.steps) if procedure else None,
            step_instruction=current_step.instruction if current_step else None,
            visual_analysis=analysis,
        )

    def process_message(
        self,
        session: Session,
        message: str,
    ) -> GuideResponse:
        """Process a text/voice message from the worker."""
        session.add_message("user", message)

        # Check for special commands
        lower_msg = message.lower().strip()

        if lower_msg in ("next", "done", "next step", "step complete"):
            return self._handle_step_complete(session)

        if lower_msg in ("repeat", "say again", "what?"):
            return self._repeat_current_instruction(session)

        if lower_msg in ("help", "i'm stuck", "stuck"):
            return self._provide_help(session)

        if any(w in lower_msg for w in ["skip", "skip step"]):
            return self._skip_step(session)

        # General conversation - use LLM
        response = self._generate_conversation_response(session, message)
        session.add_message("assistant", response)

        return GuideResponse(
            message=response,
            current_step=session.current_step if session.procedure_id else None,
            total_steps=len(session.step_progress) if session.step_progress else None,
        )

    def _generate_task_start_response(
        self,
        task_description: str,
        procedures: list[Procedure],
        safety_rules: list,
        visual_context: str,
        session: Session,
    ) -> str:
        """Generate the initial response when starting a task."""
        system = f"""You are an expert {session.trade} technician guiding a worker through a task.
Be concise, clear, and safety-focused. Speak naturally as if talking to a colleague.
Don't be verbose - workers need quick, actionable guidance."""

        procedure_info = ""
        if procedures:
            p = procedures[0]
            procedure_info = f"""
I found a matching procedure: "{p.name}"
Steps: {len(p.steps)}
Tools needed: {', '.join(p.tools_required) if p.tools_required else 'Basic tools'}
"""

        safety_info = ""
        if safety_rules:
            safety_info = "\nCritical safety rules:\n" + "\n".join(f"- {r.rule}" for r in safety_rules)

        prompt = f"""The worker wants to: {task_description}
{visual_context}
{procedure_info}
{safety_info}

Give a brief, friendly response that:
1. Acknowledges what they want to do
2. Mentions any critical safety steps FIRST
3. Gives them the first actionable instruction

Keep it under 3-4 sentences. Be direct."""

        response = self._client.messages.create(
            model=self._model,
            max_tokens=300,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text

    def _generate_guidance_response(
        self,
        session: Session,
        analysis: VisualAnalysis,
        procedure: Procedure | None,
        current_step: Step | None,
        user_message: str | None,
    ) -> str:
        """Generate guidance based on what we see."""
        system = f"""You are an expert {session.trade} technician providing real-time guidance.
You can see what the worker sees through their camera.
Be concise and actionable. If something looks wrong, say so directly.
If they're doing well, confirm and move them forward."""

        step_context = ""
        if current_step:
            step_context = f"""
Current step ({session.current_step}/{len(procedure.steps)}): {current_step.instruction}
Details: {current_step.details}
What to verify: {current_step.verification}"""

        prompt = f"""Task: {session.task_description}
{step_context}

What I see in their camera:
{analysis.raw_response}

{f'Worker says: "{user_message}"' if user_message else ''}

Based on what I see, give brief guidance. Either:
- Confirm they did it right and give next action
- Point out what needs adjustment
- Answer their question if they asked one

Keep response under 2-3 sentences. Be specific about what you see."""

        response = self._client.messages.create(
            model=self._model,
            max_tokens=250,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text

    def _generate_conversation_response(
        self,
        session: Session,
        message: str,
    ) -> str:
        """Handle general conversation/questions."""
        system = f"""You are an expert {session.trade} technician helping a worker.
Current task: {session.task_description or 'No specific task'}
Answer questions concisely. If you don't know something, say so."""

        # Include recent conversation context
        messages = session.get_conversation_for_llm(max_messages=10)
        messages.append({"role": "user", "content": message})

        response = self._client.messages.create(
            model=self._model,
            max_tokens=300,
            system=system,
            messages=messages,
        )

        return response.content[0].text

    def _handle_step_complete(self, session: Session) -> GuideResponse:
        """Handle when worker says they completed a step."""
        if not session.procedure_id:
            return GuideResponse(
                message="No active procedure. What would you like to do?",
            )

        procedure = self._knowledge.get_procedure(session.procedure_id)
        if not procedure:
            return GuideResponse(message="Procedure not found.")

        old_step = session.current_step
        session.advance_step()

        if session.current_step > len(procedure.steps):
            session.complete()
            return GuideResponse(
                message="Great work! That completes the procedure. Everything look good?",
                current_step=old_step,
                total_steps=len(procedure.steps),
            )

        next_step = procedure.steps[session.current_step - 1]
        msg = f"Step {session.current_step}: {next_step.instruction}"
        if next_step.details:
            msg += f"\n\n{next_step.details}"
        if next_step.warnings:
            msg = f"⚠️ {', '.join(next_step.warnings)}\n\n" + msg

        return GuideResponse(
            message=msg,
            current_step=session.current_step,
            total_steps=len(procedure.steps),
            step_instruction=next_step.instruction,
            warnings=next_step.warnings if next_step.warnings else None,
        )

    def _repeat_current_instruction(self, session: Session) -> GuideResponse:
        """Repeat the current step instruction."""
        if not session.procedure_id:
            return GuideResponse(
                message=f"You're working on: {session.task_description}",
            )

        procedure = self._knowledge.get_procedure(session.procedure_id)
        if not procedure or session.current_step > len(procedure.steps):
            return GuideResponse(message="No current step to repeat.")

        step = procedure.steps[session.current_step - 1]
        msg = f"Step {session.current_step}: {step.instruction}"
        if step.details:
            msg += f"\n\n{step.details}"

        return GuideResponse(
            message=msg,
            current_step=session.current_step,
            total_steps=len(procedure.steps),
            step_instruction=step.instruction,
        )

    def _provide_help(self, session: Session) -> GuideResponse:
        """Provide additional help for the current situation."""
        if not session.procedure_id:
            return GuideResponse(
                message="Tell me what you're trying to do, or show me what you're looking at.",
            )

        procedure = self._knowledge.get_procedure(session.procedure_id)
        if not procedure or session.current_step > len(procedure.steps):
            return GuideResponse(message="Show me what you're looking at and I'll help.")

        step = procedure.steps[session.current_step - 1]

        help_msg = f"Let me help with step {session.current_step}: {step.instruction}\n\n"

        if step.details:
            help_msg += f"Details: {step.details}\n\n"

        if step.tools_needed:
            help_msg += f"Tools needed: {', '.join(step.tools_needed)}\n\n"

        if step.image_hints:
            help_msg += f"Look for: {', '.join(step.image_hints)}\n\n"

        help_msg += "Show me what you're seeing and I can give more specific guidance."

        return GuideResponse(
            message=help_msg,
            current_step=session.current_step,
            total_steps=len(procedure.steps),
            step_instruction=step.instruction,
        )

    def _skip_step(self, session: Session) -> GuideResponse:
        """Skip the current step."""
        if not session.procedure_id:
            return GuideResponse(message="No active procedure.")

        procedure = self._knowledge.get_procedure(session.procedure_id)
        if not procedure:
            return GuideResponse(message="Procedure not found.")

        # Mark as skipped and advance
        if session.current_step <= len(session.step_progress):
            session.step_progress[session.current_step - 1].status = "skipped"

        session.advance_step()

        if session.current_step > len(procedure.steps):
            return GuideResponse(
                message="That was the last step. Procedure complete.",
                current_step=session.current_step - 1,
                total_steps=len(procedure.steps),
            )

        next_step = procedure.steps[session.current_step - 1]
        return GuideResponse(
            message=f"Skipped. Step {session.current_step}: {next_step.instruction}",
            current_step=session.current_step,
            total_steps=len(procedure.steps),
            step_instruction=next_step.instruction,
        )
