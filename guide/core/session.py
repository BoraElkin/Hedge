"""Session management for tracking work in progress."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SessionState(str, Enum):
    IDLE = "idle"  # No active task
    BRIEFING = "briefing"  # Explaining the task/procedure
    WORKING = "working"  # Actively guiding through steps
    VERIFYING = "verifying"  # Checking completed work
    PAUSED = "paused"  # Temporarily paused
    COMPLETED = "completed"  # Task finished


@dataclass
class Message:
    """A message in the conversation history."""

    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    image_data: bytes | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepProgress:
    """Progress on a procedure step."""

    step_number: int
    status: str  # "pending", "in_progress", "completed", "skipped"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    notes: str = ""
    verification_passed: bool = False


@dataclass
class Session:
    """A work session with a user."""

    id: str
    trade: str
    created_at: datetime = field(default_factory=datetime.now)
    state: SessionState = SessionState.IDLE

    # Current task
    task_description: str = ""
    procedure_id: str | None = None
    current_step: int = 0
    step_progress: list[StepProgress] = field(default_factory=list)

    # Conversation
    messages: list[Message] = field(default_factory=list)

    # Context from vision
    last_visual_context: dict[str, Any] = field(default_factory=dict)
    images_analyzed: int = 0

    # Metadata
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(
        self,
        role: str,
        content: str,
        image_data: bytes | None = None,
        **metadata: Any,
    ) -> Message:
        """Add a message to the conversation."""
        msg = Message(
            role=role,
            content=content,
            image_data=image_data,
            metadata=metadata,
        )
        self.messages.append(msg)
        self.updated_at = datetime.now()
        return msg

    def get_conversation_for_llm(self, max_messages: int = 20) -> list[dict]:
        """Get recent conversation formatted for LLM API."""
        recent = self.messages[-max_messages:]
        formatted = []

        for msg in recent:
            if msg.role == "system":
                continue  # System messages handled separately
            formatted.append({
                "role": msg.role if msg.role != "guide" else "assistant",
                "content": msg.content,
            })

        return formatted

    def start_procedure(self, procedure_id: str, num_steps: int) -> None:
        """Start working on a procedure."""
        self.procedure_id = procedure_id
        self.current_step = 1
        self.state = SessionState.BRIEFING
        self.step_progress = [
            StepProgress(step_number=i, status="pending")
            for i in range(1, num_steps + 1)
        ]

    def advance_step(self) -> int:
        """Move to the next step. Returns new step number."""
        if self.current_step < len(self.step_progress):
            # Mark current as completed
            progress = self.step_progress[self.current_step - 1]
            progress.status = "completed"
            progress.completed_at = datetime.now()

            # Move to next
            self.current_step += 1

            if self.current_step <= len(self.step_progress):
                next_progress = self.step_progress[self.current_step - 1]
                next_progress.status = "in_progress"
                next_progress.started_at = datetime.now()
                self.state = SessionState.WORKING
            else:
                self.state = SessionState.VERIFYING

        return self.current_step

    def complete(self) -> None:
        """Mark session as completed."""
        self.state = SessionState.COMPLETED
        self.updated_at = datetime.now()


class SessionManager:
    """Manages active work sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create_session(self, trade: str = "general") -> Session:
        """Create a new session."""
        session = Session(
            id=str(uuid.uuid4()),
            trade=trade,
            created_at=datetime.now(),
        )
        self._sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def list_sessions(self, active_only: bool = True) -> list[Session]:
        """List all sessions."""
        sessions = list(self._sessions.values())
        if active_only:
            sessions = [
                s for s in sessions
                if s.state not in (SessionState.COMPLETED,)
            ]
        return sessions

    def cleanup_old_sessions(self, max_age_hours: int = 24) -> int:
        """Remove sessions older than max_age_hours. Returns count removed."""
        now = datetime.now()
        to_remove = []

        for session_id, session in self._sessions.items():
            age = (now - session.updated_at).total_seconds() / 3600
            if age > max_age_hours:
                to_remove.append(session_id)

        for session_id in to_remove:
            del self._sessions[session_id]

        return len(to_remove)
