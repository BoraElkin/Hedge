# HVAC Copilot

**Real-time AI guidance for HVAC technicians.**

An AI copilot that sees through your phone camera and talks you through the job — like having a senior tech in your ear on every call.

## The Vision

HVAC repair requires skills that take years to develop. But AI can now:

1. **See** through a phone camera in real-time
2. **Understand** what it's looking at (equipment, wiring, components)
3. **Guide** technicians step-by-step with voice instructions

A new tech can become effective on day one, with AI coaching them through: "That's the capacitor — before you touch it, let's discharge it. Got your screwdriver?"

## How It Works

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Technician's  │────▶│  LiveKit Cloud  │────▶│   AI Agent      │
│   Phone Camera  │     │  (WebRTC)       │     │  (Gemini Live)  │
│                 │◀────│                 │◀────│                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
     Video + Voice           Streaming              Voice Response
```

1. Tech opens app, selects task ("Thermostat Install", "AC Not Cooling")
2. Points phone at the equipment
3. AI sees the video stream in real-time (1-2 FPS)
4. AI speaks guidance through earbuds
5. Tech works hands-free with expert guidance

## Tech Stack

| Layer | Technology |
|-------|------------|
| **AI Model** | Gemini 2.0 Flash Live API — native video+voice, ~$0.02-0.05/session |
| **Real-time** | LiveKit Cloud + Agents SDK — handles WebRTC, Python-native |
| **Backend** | FastAPI — REST for auth, sessions, billing |
| **Frontend** | React Native + Expo — iOS + Android from one codebase |
| **Database** | Supabase — Postgres + Auth + Storage |
| **Payments** | Stripe — Free/Pro/Team tiers |

## Project Structure

```
hvac-copilot/
├── backend/
│   ├── agent/
│   │   ├── hvac_agent.py      # LiveKit Agent — core AI loop
│   │   └── prompts.py         # System prompts & task templates
│   ├── api/
│   │   ├── main.py            # FastAPI app
│   │   └── routes/            # Auth, sessions, tasks, usage
│   ├── db/
│   │   └── models.py          # Database schemas
│   ├── requirements.txt
│   └── Dockerfile
├── mobile/                     # React Native app (coming soon)
├── scripts/
│   ├── test_agent.py          # Test agent with webcam
│   └── seed_tasks.py          # Verify task templates
└── docs/
```

## Quick Start

### 1. Set up environment

```bash
cd backend
cp .env.example .env
# Fill in your API keys:
# - GOOGLE_API_KEY (get from Google AI Studio)
# - LIVEKIT_* (get from cloud.livekit.io)
# - SUPABASE_* (get from your Supabase project)
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the API server

```bash
uvicorn api.main:app --reload
```

### 4. Run the AI agent

```bash
python -m agent.hvac_agent dev
```

### 5. Test with webcam

```bash
python ../scripts/test_agent.py
```

## Task Templates

Pre-built guidance for common HVAC jobs:

| Task | Description |
|------|-------------|
| `thermostat_install` | Install or replace a thermostat |
| `ac_not_cooling` | Diagnose AC cooling issues |
| `furnace_no_heat` | Diagnose furnace heating issues |
| `capacitor_replacement` | Replace run/start capacitor |
| `filter_replacement` | Replace air filter |
| `refrigerant_check` | Check refrigerant pressures |
| `contactor_replacement` | Replace contactor |
| `blower_motor` | Service or replace blower motor |

## API Endpoints

### Authentication
- `POST /auth/signup` — Create account
- `POST /auth/login` — Sign in, get JWT
- `GET /auth/me` — Get current user

### Sessions
- `POST /sessions/start` — Start guidance session (returns LiveKit token)
- `POST /sessions/{id}/end` — End session, save rating
- `GET /sessions/history` — List past sessions

### Tasks
- `GET /tasks` — List task templates
- `GET /tasks/{id}` — Get task details

### Usage
- `GET /usage/status` — Check free tier limits
- `GET /usage/history` — Usage statistics

## Pricing Tiers

| Tier | Price | Sessions | Session Length |
|------|-------|----------|----------------|
| **Free** | $0 | 3/week | 10 min max |
| **Pro** | $49/mo | Unlimited | Unlimited |
| **Team** | $149-499/mo | Unlimited | + Admin dashboard |

## Safety

The AI is trained to:
- Say "STOP" immediately if it sees a safety hazard
- Always verify power is OFF before electrical guidance
- Remind about EPA certification for refrigerant work
- Never guess on critical work — asks for clarification

## Development Roadmap

### Phase 1: MVP (Weeks 1-4) ✓
- [x] LiveKit Agent with Gemini Live
- [x] FastAPI backend with Supabase
- [x] Task templates for common HVAC jobs
- [ ] React Native mobile app
- [ ] Free tier with usage limits

### Phase 2: Beta (Weeks 5-8)
- [ ] User testing with real HVAC techs
- [ ] Demo video content
- [ ] Landing page + waitlist
- [ ] Stripe payments

### Phase 3: Launch (Weeks 9-12)
- [ ] App Store submission
- [ ] RAG with manufacturer manuals
- [ ] Team plans
- [ ] Admin dashboard

## License

MIT

---

Built for [Y Combinator RFS: AI for Physical Work](https://www.ycombinator.com/rfs#ai-physical-work)
