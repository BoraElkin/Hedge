"""LiveKit Agent for real-time HVAC guidance using Gemini Live API.

This is the core of the product:
- Receives video frames (1-2 FPS) + audio from technician's phone
- Sends to Gemini 2.5 Flash Live API
- Streams voice responses back to technician

Run with: python -m backend.agent.hvac_agent dev
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from livekit import rtc
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
)
from livekit.agents.voice import Agent as VoiceAgent
from livekit.plugins import google, silero

from .prompts import get_system_prompt, TASK_TEMPLATES

logger = logging.getLogger("hvac-agent")
logger.setLevel(logging.INFO)


async def entrypoint(ctx: JobContext) -> None:
    """Main entry point for the HVAC guidance agent.

    This function is called when a technician joins a LiveKit room.
    It sets up the Gemini Live connection and starts streaming.
    """
    logger.info(f"Agent connecting to room: {ctx.room.name}")

    # Connect to the room and subscribe to audio/video
    await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_ALL)

    # Wait for a participant (the technician) to join
    participant = await ctx.wait_for_participant()
    logger.info(f"Participant joined: {participant.identity}")

    # Get task context from room metadata (set by the mobile app)
    task_template = "general"
    custom_context = None

    if ctx.room.metadata:
        import json
        try:
            metadata = json.loads(ctx.room.metadata)
            task_template = metadata.get("task_template", "general")
            custom_context = metadata.get("custom_context")
            logger.info(f"Task template: {task_template}, Custom context: {custom_context}")
        except json.JSONDecodeError:
            logger.warning("Could not parse room metadata")

    # Build the system prompt for this task
    system_prompt = get_system_prompt(task_template, custom_context)

    # Create the Gemini multimodal model
    # Using Gemini 2.0 Flash for real-time video + voice
    model = google.beta.realtime.RealtimeModel(
        model="gemini-2.0-flash-exp",
        voice="Puck",  # Clear, professional voice
        temperature=0.7,
        instructions=system_prompt,
    )

    # Create voice activity detection
    vad = silero.VAD.load()

    # Create the voice agent
    # This handles the full loop: video/audio in -> Gemini -> voice out
    agent = VoiceAgent(
        instructions=system_prompt,
        vad=vad,
        llm=model,
    )

    # Start the agent session - it now sees video + hears audio
    # and responds with voice automatically
    session = agent.start(ctx.room, participant)

    logger.info("Agent started - now providing real-time guidance")

    # Keep the agent running until the session ends
    await session.wait()

    logger.info("Session ended")


def prewarm(proc: JobProcess) -> None:
    """Prewarm function to load models before first request.

    This reduces cold-start latency.
    """
    logger.info("Prewarming agent...")
    # Load VAD model
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("Prewarm complete")


if __name__ == "__main__":
    # Run the agent
    # In development: python -m backend.agent.hvac_agent dev
    # In production: python -m backend.agent.hvac_agent start
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )
