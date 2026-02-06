# Guide

**Real-time AI guidance for physical work.**

> "I know Kung Fu." — Neo, The Matrix

What if any worker could gain expert-level skills instantly? Not through years of training, but through an AI that sees what they see and talks them through the job in real-time.

Guide is the foundation for building that future.

## The Vision

Physical work — HVAC repair, plumbing, electrical, healthcare, manufacturing — requires skills that traditionally take months or years to develop. But AI can now:

1. **See** through a phone camera or smart glasses
2. **Reason** about real-world situations
3. **Guide** humans through complex tasks step-by-step

This means a new worker can become effective on day one, with AI coaching them through every step: "turn off that valve", "use the ⅜ inch wrench", "that part looks worn, replace it".

## How It Works

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Worker's      │────▶│    Guide AI     │────▶│   Voice/Text    │
│   Camera        │     │   (sees +       │     │   Response      │
│                 │◀────│    reasons)     │◀────│                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │
        │                       ▼
        │               ┌─────────────────┐
        │               │  Knowledge Base │
        │               │  - Procedures   │
        │               │  - Safety rules │
        │               │  - Part info    │
        │               └─────────────────┘
        │
        ▼
   Worker performs
   the physical task
```

**Core loop:**
1. Worker shows their camera what they're looking at
2. Guide sees and understands the scene using Claude's vision
3. Guide provides real-time audio/text guidance
4. Worker executes, asks questions, or says "done" to move on
5. Repeat until task complete

## Quick Start

```bash
# Clone and install
git clone <repo-url>
cd guide
pip install -e .

# Configure
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env

# Run
python -m guide.cli
# or
guide
```

Open http://localhost:8000/demo for the web UI.

## Architecture

```
guide/
├── core/
│   ├── vision.py      # Claude multimodal for image understanding
│   ├── voice.py       # Speech-to-text and text-to-speech
│   ├── guide.py       # Main AI orchestrator
│   ├── knowledge.py   # Procedures, safety rules, part database
│   └── session.py     # Session and state management
├── api/
│   └── app.py         # FastAPI with REST + WebSocket
└── cli.py             # Server entry point
```

### Key Components

**VisionAnalyzer** (`core/vision.py`)
- Uses Claude's multimodal capabilities to understand images
- Identifies objects, tools, equipment, hazards
- Provides contextual analysis for the current task step

**AIGuide** (`core/guide.py`)
- Main orchestrator that ties everything together
- Manages conversation flow and task progress
- Generates contextual, actionable guidance

**KnowledgeBase** (`core/knowledge.py`)
- Stores procedures as structured step-by-step instructions
- Safety rules with severity levels
- Extensible for trade-specific knowledge

**Session** (`core/session.py`)
- Tracks state: current task, step progress, conversation history
- Persists context across interactions

## API

### REST Endpoints

```bash
# Create a session
POST /sessions
{"trade": "hvac"}

# Start a task
POST /sessions/{id}/start
{"task_description": "Replace the air filter"}

# Send an image
POST /sessions/{id}/image
[multipart: image file + optional message]

# Send a message
POST /sessions/{id}/message
{"message": "what size wrench do I need?"}

# List procedures
GET /procedures?trade=hvac
```

### WebSocket (Real-time)

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/{session_id}');

// Start task
ws.send(JSON.stringify({
  type: 'start',
  task: 'Replace thermostat',
  image_base64: '...' // optional
}));

// Send image
ws.send(JSON.stringify({
  type: 'image',
  data: '...base64...',
  message: 'Is this the right wire?'
}));

// Send command
ws.send(JSON.stringify({
  type: 'command',
  command: 'next' // or 'help', 'repeat', 'skip'
}));

// Receive guidance
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // {type: 'guidance', message: '...', current_step: 2, total_steps: 6, ...}
};
```

## Built-in Procedures

The knowledge base includes starter procedures for common tasks:

**HVAC**
- Replace air filter
- Install smart thermostat

**Plumbing**
- Replace faucet cartridge

**Electrical**
- Replace electrical outlet

Add your own procedures by extending the `KnowledgeBase` class or adding them at runtime.

## Configuration

Environment variables (`.env`):

```bash
# Required
ANTHROPIC_API_KEY=your-key

# Optional: for voice features
OPENAI_API_KEY=your-key

# Server
HOST=0.0.0.0
PORT=8000

# Model
DEFAULT_MODEL=claude-sonnet-4-20250514
```

## Extending Guide

### Adding a New Trade

1. Add trade-specific knowledge to `KnowledgeBase._load_default_knowledge()`
2. Add trade-specific system prompts in `VisionAnalyzer._build_system_prompt()`
3. Create procedures following the `Procedure` and `Step` dataclasses

### Adding Procedures

```python
from guide.core.knowledge import KnowledgeBase, Procedure, Step

kb = KnowledgeBase()
kb.add_procedure(Procedure(
    id="custom-task",
    name="My Custom Task",
    trade="general",
    description="How to do the thing",
    steps=[
        Step(number=1, instruction="First, do this", details="..."),
        Step(number=2, instruction="Then, do that", details="..."),
    ],
    safety_warnings=["Be careful of X"],
    tools_required=["Tool A", "Tool B"],
))
```

### Custom Vision Analysis

Extend `VisionAnalyzer` for domain-specific image understanding:

```python
class HVACVisionAnalyzer(VisionAnalyzer):
    def analyze_refrigerant_gauges(self, image_data: bytes) -> dict:
        return self.quick_check(
            image_data,
            "Read the pressure gauges. What are the high and low side pressures?"
        )
```

## What's Next

This is a foundation. To build a production system, consider:

1. **Voice-first interface** — Hands-free operation via smart glasses or earbuds
2. **Persistent knowledge base** — Vector database for semantic search over manuals/docs
3. **Video streaming** — Continuous analysis instead of discrete images
4. **AR overlays** — Point at specific parts of the image ("put the wire HERE")
5. **Learning from experts** — Record expert workers to build new procedures
6. **Offline mode** — On-device models for areas without connectivity
7. **Multi-language** — Support workers in their native language

## Philosophy

The goal isn't to replace skilled workers — it's to create more of them. To give anyone the ability to do meaningful, well-paid physical work. To solve the skilled labor shortage while creating economic opportunity.

AI that augments human capability, not AI that replaces it.

---

Built for [Y Combinator W25 RFS: AI for Physical Work](https://www.ycombinator.com/rfs#ai-physical-work)
