"""Database models for HVAC Copilot.

These are reference models - actual tables are in Supabase.

SQL for Supabase:

-- Users table (supplements Supabase auth.users)
CREATE TABLE users (
    id UUID PRIMARY KEY REFERENCES auth.users(id),
    email TEXT NOT NULL,
    plan TEXT DEFAULT 'free' CHECK (plan IN ('free', 'pro', 'team')),
    stripe_customer_id TEXT,
    team_id UUID REFERENCES teams(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Teams table for team plans
CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    owner_id UUID REFERENCES users(id),
    stripe_subscription_id TEXT,
    max_members INTEGER DEFAULT 10,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Sessions table
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) NOT NULL,
    task_template TEXT NOT NULL,
    custom_context TEXT,
    room_name TEXT,
    duration_seconds INTEGER,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    feedback TEXT,
    started_at TIMESTAMPTZ DEFAULT now(),
    ended_at TIMESTAMPTZ
);

-- Usage logs for cost tracking
CREATE TABLE usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    session_id UUID REFERENCES sessions(id),
    tokens_used INTEGER,
    cost_usd NUMERIC(10, 6),
    model TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Row Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_logs ENABLE ROW LEVEL SECURITY;

-- Users can only see their own data
CREATE POLICY "Users can view own data" ON users
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can view own sessions" ON sessions
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own sessions" ON sessions
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own sessions" ON sessions
    FOR UPDATE USING (auth.uid() = user_id);

-- Indexes
CREATE INDEX sessions_user_id_idx ON sessions(user_id);
CREATE INDEX sessions_started_at_idx ON sessions(started_at);
CREATE INDEX usage_logs_user_id_idx ON usage_logs(user_id);
CREATE INDEX usage_logs_session_id_idx ON usage_logs(session_id);
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Plan(str, Enum):
    FREE = "free"
    PRO = "pro"
    TEAM = "team"


@dataclass
class User:
    id: str
    email: str
    plan: Plan = Plan.FREE
    stripe_customer_id: str | None = None
    team_id: str | None = None
    created_at: datetime | None = None


@dataclass
class Team:
    id: str
    name: str
    owner_id: str
    stripe_subscription_id: str | None = None
    max_members: int = 10
    created_at: datetime | None = None


@dataclass
class Session:
    id: str
    user_id: str
    task_template: str
    custom_context: str | None = None
    room_name: str | None = None
    duration_seconds: int | None = None
    rating: int | None = None
    feedback: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


@dataclass
class UsageLog:
    id: str
    user_id: str
    session_id: str | None = None
    tokens_used: int | None = None
    cost_usd: float | None = None
    model: str | None = None
    created_at: datetime | None = None
