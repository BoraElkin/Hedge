#!/usr/bin/env python3
"""Test the HVAC agent locally with webcam.

Usage:
    python scripts/test_agent.py

Prerequisites:
    - Set GOOGLE_API_KEY environment variable
    - Set LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
    - Have a webcam connected

This creates a test room and runs the agent against your webcam.
"""

import asyncio
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    from dotenv import load_dotenv

    load_dotenv()

    # Verify environment
    required = ["GOOGLE_API_KEY", "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        print(f"Missing environment variables: {missing}")
        print("Copy backend/.env.example to .env and fill in the values.")
        sys.exit(1)

    print("Environment OK. Starting agent test...")
    print("\nTo test:")
    print("1. The agent will start and wait for a participant")
    print("2. Open https://meet.livekit.io and join the 'hvac-test' room")
    print("3. Use your webcam and speak to test the agent")
    print("\nPress Ctrl+C to stop.\n")

    # Run the agent in dev mode
    from backend.agent.hvac_agent import entrypoint
    from livekit.agents import WorkerOptions, cli

    cli.run_app(
        WorkerOptions(entrypoint_fnc=entrypoint),
    )


if __name__ == "__main__":
    asyncio.run(main())
