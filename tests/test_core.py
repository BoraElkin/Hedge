"""Tests for core components."""

import pytest

from guide.core.knowledge import KnowledgeBase, Procedure, Step, SafetyRule
from guide.core.session import Session, SessionManager, SessionState, StepProgress


class TestKnowledgeBase:
    def test_default_procedures_loaded(self):
        kb = KnowledgeBase()
        assert len(kb._procedures) > 0

    def test_get_procedure(self):
        kb = KnowledgeBase()
        proc = kb.get_procedure("hvac-filter-replace")
        assert proc is not None
        assert proc.name == "Replace Air Filter"
        assert len(proc.steps) > 0

    def test_search_procedures(self):
        kb = KnowledgeBase()
        results = kb.search_procedures("filter")
        assert len(results) > 0
        assert any("filter" in p.name.lower() for p in results)

    def test_search_procedures_by_trade(self):
        kb = KnowledgeBase()
        results = kb.search_procedures("replace", trade="hvac")
        assert all(p.trade == "hvac" for p in results)

    def test_get_safety_rules(self):
        kb = KnowledgeBase()
        rules = kb.get_safety_rules(trade="electrical")
        assert len(rules) > 0
        assert any(r.severity == "critical" for r in rules)

    def test_critical_safety_rules_first(self):
        kb = KnowledgeBase()
        rules = kb.get_safety_rules(trade="electrical")
        # Should be sorted by severity
        if len(rules) > 1:
            first_critical = next(
                (i for i, r in enumerate(rules) if r.severity == "critical"),
                len(rules)
            )
            first_warning = next(
                (i for i, r in enumerate(rules) if r.severity == "warning"),
                len(rules)
            )
            # Critical should come before warning
            if first_critical < len(rules) and first_warning < len(rules):
                assert first_critical <= first_warning

    def test_add_custom_procedure(self):
        kb = KnowledgeBase()
        custom = Procedure(
            id="custom-test",
            name="Custom Test Procedure",
            trade="general",
            description="A test procedure",
            steps=[
                Step(number=1, instruction="Do the first thing"),
                Step(number=2, instruction="Do the second thing"),
            ],
        )
        kb.add_procedure(custom)
        assert kb.get_procedure("custom-test") is not None


class TestSession:
    def test_create_session(self):
        session = Session(
            id="test-123",
            trade="hvac",
        )
        assert session.id == "test-123"
        assert session.state == SessionState.IDLE

    def test_add_message(self):
        session = Session(id="test", trade="general")
        msg = session.add_message("user", "Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert len(session.messages) == 1

    def test_start_procedure(self):
        session = Session(id="test", trade="hvac")
        session.start_procedure("hvac-filter-replace", num_steps=6)

        assert session.procedure_id == "hvac-filter-replace"
        assert session.current_step == 1
        assert session.state == SessionState.BRIEFING
        assert len(session.step_progress) == 6

    def test_advance_step(self):
        session = Session(id="test", trade="hvac")
        session.start_procedure("test-proc", num_steps=3)

        assert session.current_step == 1
        session.advance_step()
        assert session.current_step == 2
        assert session.step_progress[0].status == "completed"

    def test_advance_past_last_step(self):
        session = Session(id="test", trade="hvac")
        session.start_procedure("test-proc", num_steps=2)

        session.advance_step()  # 1 -> 2
        session.advance_step()  # 2 -> complete

        assert session.current_step == 3
        assert session.state == SessionState.VERIFYING

    def test_conversation_for_llm(self):
        session = Session(id="test", trade="general")
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi there!")
        session.add_message("user", "Help me")

        messages = session.get_conversation_for_llm()
        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"


class TestSessionManager:
    def test_create_and_get_session(self):
        manager = SessionManager()
        session = manager.create_session(trade="plumbing")

        retrieved = manager.get_session(session.id)
        assert retrieved is not None
        assert retrieved.trade == "plumbing"

    def test_delete_session(self):
        manager = SessionManager()
        session = manager.create_session()

        assert manager.delete_session(session.id) is True
        assert manager.get_session(session.id) is None

    def test_delete_nonexistent_session(self):
        manager = SessionManager()
        assert manager.delete_session("fake-id") is False

    def test_list_sessions(self):
        manager = SessionManager()
        s1 = manager.create_session()
        s2 = manager.create_session()

        sessions = manager.list_sessions()
        assert len(sessions) == 2

    def test_list_active_sessions_only(self):
        manager = SessionManager()
        s1 = manager.create_session()
        s2 = manager.create_session()
        s2.complete()

        active = manager.list_sessions(active_only=True)
        assert len(active) == 1
        assert active[0].id == s1.id


class TestStep:
    def test_step_creation(self):
        step = Step(
            number=1,
            instruction="Turn off the power",
            details="Flip the breaker switch to OFF",
            warnings=["Verify power is off with tester"],
            tools_needed=["Voltage tester"],
        )
        assert step.number == 1
        assert "power" in step.instruction.lower()
        assert len(step.warnings) == 1

    def test_step_with_verification(self):
        step = Step(
            number=2,
            instruction="Remove the cover plate",
            verification="Cover plate is off and wires are visible",
        )
        assert step.verification != ""


class TestProcedure:
    def test_procedure_creation(self):
        proc = Procedure(
            id="test-proc",
            name="Test Procedure",
            trade="general",
            description="A test",
            steps=[
                Step(number=1, instruction="Step one"),
                Step(number=2, instruction="Step two"),
            ],
            safety_warnings=["Be careful"],
            tools_required=["Screwdriver"],
        )
        assert proc.id == "test-proc"
        assert len(proc.steps) == 2
        assert proc.difficulty == "intermediate"  # default
