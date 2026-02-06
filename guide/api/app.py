"""FastAPI application with REST and WebSocket endpoints."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from guide.config import get_settings
from guide.core.guide import AIGuide
from guide.core.knowledge import KnowledgeBase
from guide.core.session import Session, SessionManager, SessionState
from guide.core.voice import VoiceProcessor

app = FastAPI(
    title="Guide",
    description="Real-time AI guidance for physical work",
    version="0.1.0",
)

# CORS for mobile/web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
session_manager = SessionManager()
knowledge_base = KnowledgeBase()


# --- Pydantic models ---


class CreateSessionRequest(BaseModel):
    trade: str = "general"


class CreateSessionResponse(BaseModel):
    session_id: str
    trade: str
    state: str


class StartTaskRequest(BaseModel):
    task_description: str
    image_base64: str | None = None


class MessageRequest(BaseModel):
    message: str


class GuideResponseModel(BaseModel):
    message: str
    action: str | None = None
    warnings: list[str] | None = None
    current_step: int | None = None
    total_steps: int | None = None
    step_instruction: str | None = None


class SessionInfo(BaseModel):
    session_id: str
    trade: str
    state: str
    task: str
    current_step: int | None
    total_steps: int | None


class ProcedureInfo(BaseModel):
    id: str
    name: str
    trade: str
    description: str
    difficulty: str
    steps_count: int


# --- REST Endpoints ---


@app.get("/")
async def root():
    """Health check and API info."""
    return {
        "name": "Guide API",
        "version": "0.1.0",
        "status": "running",
    }


@app.post("/sessions", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest):
    """Create a new guidance session."""
    session = session_manager.create_session(trade=request.trade)
    return CreateSessionResponse(
        session_id=session.id,
        trade=session.trade,
        state=session.state.value,
    )


@app.get("/sessions/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str):
    """Get session information."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionInfo(
        session_id=session.id,
        trade=session.trade,
        state=session.state.value,
        task=session.task_description,
        current_step=session.current_step if session.procedure_id else None,
        total_steps=len(session.step_progress) if session.step_progress else None,
    )


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    if session_manager.delete_session(session_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Session not found")


@app.post("/sessions/{session_id}/start", response_model=GuideResponseModel)
async def start_task(session_id: str, request: StartTaskRequest):
    """Start a new task in the session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    guide = AIGuide()

    image_data = None
    if request.image_base64:
        image_data = base64.b64decode(request.image_base64)

    response = guide.start_task(
        session=session,
        task_description=request.task_description,
        image_data=image_data,
    )

    return GuideResponseModel(
        message=response.message,
        action=response.action,
        warnings=response.warnings,
        current_step=response.current_step,
        total_steps=response.total_steps,
        step_instruction=response.step_instruction,
    )


@app.post("/sessions/{session_id}/image", response_model=GuideResponseModel)
async def process_image(
    session_id: str,
    image: UploadFile = File(...),
    message: str | None = Form(None),
):
    """Process an image from the worker's camera."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    guide = AIGuide()
    image_data = await image.read()

    response = guide.process_image(
        session=session,
        image_data=image_data,
        user_message=message,
    )

    return GuideResponseModel(
        message=response.message,
        action=response.action,
        warnings=response.warnings,
        current_step=response.current_step,
        total_steps=response.total_steps,
        step_instruction=response.step_instruction,
    )


@app.post("/sessions/{session_id}/message", response_model=GuideResponseModel)
async def process_message(session_id: str, request: MessageRequest):
    """Process a text message from the worker."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    guide = AIGuide()
    response = guide.process_message(session=session, message=request.message)

    return GuideResponseModel(
        message=response.message,
        action=response.action,
        warnings=response.warnings,
        current_step=response.current_step,
        total_steps=response.total_steps,
        step_instruction=response.step_instruction,
    )


@app.get("/procedures", response_model=list[ProcedureInfo])
async def list_procedures(trade: str | None = None, query: str | None = None):
    """List available procedures."""
    if query:
        procedures = knowledge_base.search_procedures(query, trade=trade)
    else:
        procedures = list(knowledge_base._procedures.values())
        if trade:
            procedures = [p for p in procedures if p.trade == trade]

    return [
        ProcedureInfo(
            id=p.id,
            name=p.name,
            trade=p.trade,
            description=p.description,
            difficulty=p.difficulty,
            steps_count=len(p.steps),
        )
        for p in procedures
    ]


@app.get("/procedures/{procedure_id}")
async def get_procedure(procedure_id: str):
    """Get full procedure details."""
    procedure = knowledge_base.get_procedure(procedure_id)
    if not procedure:
        raise HTTPException(status_code=404, detail="Procedure not found")

    return {
        "id": procedure.id,
        "name": procedure.name,
        "trade": procedure.trade,
        "description": procedure.description,
        "difficulty": procedure.difficulty,
        "estimated_time": procedure.estimated_time,
        "tools_required": procedure.tools_required,
        "safety_warnings": procedure.safety_warnings,
        "steps": [
            {
                "number": s.number,
                "instruction": s.instruction,
                "details": s.details,
                "warnings": s.warnings,
                "tools_needed": s.tools_needed,
                "verification": s.verification,
            }
            for s in procedure.steps
        ],
    }


@app.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    """Transcribe audio to text."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=501, detail="Speech-to-text not configured")

    voice = VoiceProcessor()
    audio_data = await audio.read()

    # Determine format from filename
    fmt = "webm"
    if audio.filename:
        if audio.filename.endswith(".mp3"):
            fmt = "mp3"
        elif audio.filename.endswith(".wav"):
            fmt = "wav"
        elif audio.filename.endswith(".m4a"):
            fmt = "m4a"

    result = voice.transcribe(audio_data, format=fmt)
    return {"text": result.text, "confidence": result.confidence}


@app.post("/synthesize")
async def synthesize_speech(text: str = Form(...), voice: str = Form("nova")):
    """Convert text to speech."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=501, detail="Text-to-speech not configured")

    voice_processor = VoiceProcessor()
    audio_data = voice_processor.synthesize(text, voice=voice)

    return StreamingResponse(
        iter([audio_data]),
        media_type="audio/mpeg",
        headers={"Content-Disposition": "attachment; filename=speech.mp3"},
    )


# --- WebSocket for real-time interaction ---


class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[session_id] = websocket

    def disconnect(self, session_id: str):
        self.active_connections.pop(session_id, None)

    async def send(self, session_id: str, data: dict):
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_json(data)


ws_manager = ConnectionManager()


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket for real-time bidirectional communication.

    Message types:
    - {"type": "start", "task": "...", "image_base64": "..."}
    - {"type": "image", "data": "base64...", "message": "optional"}
    - {"type": "message", "text": "..."}
    - {"type": "command", "command": "next|repeat|help|skip"}

    Responses:
    - {"type": "guidance", "message": "...", "step": N, "total": M, ...}
    - {"type": "warning", "warnings": [...]}
    - {"type": "error", "message": "..."}
    """
    session = session_manager.get_session(session_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    await ws_manager.connect(session_id, websocket)
    guide = AIGuide()

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            try:
                if msg_type == "start":
                    image_data = None
                    if data.get("image_base64"):
                        image_data = base64.b64decode(data["image_base64"])

                    response = guide.start_task(
                        session=session,
                        task_description=data["task"],
                        image_data=image_data,
                    )

                elif msg_type == "image":
                    image_data = base64.b64decode(data["data"])
                    response = guide.process_image(
                        session=session,
                        image_data=image_data,
                        user_message=data.get("message"),
                    )

                elif msg_type == "message":
                    response = guide.process_message(
                        session=session,
                        message=data["text"],
                    )

                elif msg_type == "command":
                    command = data["command"]
                    response = guide.process_message(
                        session=session,
                        message=command,
                    )

                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown message type: {msg_type}",
                    })
                    continue

                # Send response
                response_data = {
                    "type": "guidance",
                    "message": response.message,
                    "action": response.action,
                    "current_step": response.current_step,
                    "total_steps": response.total_steps,
                    "step_instruction": response.step_instruction,
                }

                if response.warnings:
                    await websocket.send_json({
                        "type": "warning",
                        "warnings": response.warnings,
                    })

                await websocket.send_json(response_data)

            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "message": str(e),
                })

    except WebSocketDisconnect:
        ws_manager.disconnect(session_id)


# --- Demo UI ---


@app.get("/demo", response_class=HTMLResponse)
async def demo_ui():
    """Simple demo UI for testing."""
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Guide Demo</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .container { max-width: 600px; margin: 0 auto; }
        h1 { color: #333; }
        .card { background: white; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        button { background: #007AFF; color: white; border: none; padding: 12px 24px; border-radius: 8px; font-size: 16px; cursor: pointer; }
        button:hover { background: #0056b3; }
        button:disabled { background: #ccc; }
        input, textarea { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 16px; margin-bottom: 12px; }
        .response { background: #e8f4f8; padding: 16px; border-radius: 8px; margin-top: 12px; }
        .warning { background: #fff3cd; padding: 12px; border-radius: 8px; margin-bottom: 12px; }
        .step-indicator { color: #666; font-size: 14px; margin-bottom: 8px; }
        #preview { max-width: 100%; max-height: 200px; margin-top: 12px; border-radius: 8px; }
        .hidden { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔧 Guide Demo</h1>

        <div class="card" id="setup">
            <h3>1. Select Trade</h3>
            <select id="trade">
                <option value="general">General</option>
                <option value="hvac">HVAC</option>
                <option value="plumbing">Plumbing</option>
                <option value="electrical">Electrical</option>
            </select>
            <button onclick="createSession()">Start Session</button>
        </div>

        <div class="card hidden" id="task-input">
            <h3>2. What do you need help with?</h3>
            <textarea id="task" placeholder="e.g., Replace the air filter in my HVAC system"></textarea>
            <input type="file" id="initial-image" accept="image/*" capture="environment">
            <img id="preview" class="hidden">
            <button onclick="startTask()">Start Task</button>
        </div>

        <div class="card hidden" id="interaction">
            <h3>Guide</h3>
            <div id="warnings"></div>
            <div id="step-indicator" class="step-indicator"></div>
            <div id="response" class="response">Ready to help!</div>

            <h4>Send Image</h4>
            <input type="file" id="camera" accept="image/*" capture="environment">
            <button onclick="sendImage()">📷 Send What I See</button>

            <h4>Or Type/Speak</h4>
            <input type="text" id="message" placeholder="Ask a question or say 'next' for next step">
            <button onclick="sendMessage()">Send</button>
            <button onclick="sendCommand('next')">✓ Done / Next</button>
            <button onclick="sendCommand('help')">❓ Help</button>
        </div>
    </div>

    <script>
        let sessionId = null;
        let ws = null;

        document.getElementById('initial-image').onchange = function(e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    document.getElementById('preview').src = e.target.result;
                    document.getElementById('preview').classList.remove('hidden');
                };
                reader.readAsDataURL(file);
            }
        };

        async function createSession() {
            const trade = document.getElementById('trade').value;
            const resp = await fetch('/sessions', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({trade})
            });
            const data = await resp.json();
            sessionId = data.session_id;

            // Connect WebSocket
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws/${sessionId}`);
            ws.onmessage = handleWSMessage;

            document.getElementById('setup').classList.add('hidden');
            document.getElementById('task-input').classList.remove('hidden');
        }

        async function startTask() {
            const task = document.getElementById('task').value;
            const fileInput = document.getElementById('initial-image');
            let imageBase64 = null;

            if (fileInput.files[0]) {
                imageBase64 = await fileToBase64(fileInput.files[0]);
            }

            ws.send(JSON.stringify({
                type: 'start',
                task: task,
                image_base64: imageBase64
            }));

            document.getElementById('task-input').classList.add('hidden');
            document.getElementById('interaction').classList.remove('hidden');
        }

        async function sendImage() {
            const fileInput = document.getElementById('camera');
            if (!fileInput.files[0]) {
                alert('Please select an image first');
                return;
            }
            const imageBase64 = await fileToBase64(fileInput.files[0]);
            const message = document.getElementById('message').value;

            ws.send(JSON.stringify({
                type: 'image',
                data: imageBase64,
                message: message || undefined
            }));

            document.getElementById('message').value = '';
        }

        function sendMessage() {
            const text = document.getElementById('message').value;
            if (!text) return;

            ws.send(JSON.stringify({
                type: 'message',
                text: text
            }));

            document.getElementById('message').value = '';
        }

        function sendCommand(cmd) {
            ws.send(JSON.stringify({
                type: 'command',
                command: cmd
            }));
        }

        function handleWSMessage(event) {
            const data = JSON.parse(event.data);

            if (data.type === 'guidance') {
                document.getElementById('response').innerText = data.message;
                if (data.current_step && data.total_steps) {
                    document.getElementById('step-indicator').innerText =
                        `Step ${data.current_step} of ${data.total_steps}: ${data.step_instruction || ''}`;
                }
            } else if (data.type === 'warning') {
                document.getElementById('warnings').innerHTML =
                    '<div class="warning">⚠️ ' + data.warnings.join('<br>⚠️ ') + '</div>';
            } else if (data.type === 'error') {
                document.getElementById('response').innerText = '❌ Error: ' + data.message;
            }
        }

        function fileToBase64(file) {
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => {
                    const base64 = reader.result.split(',')[1];
                    resolve(base64);
                };
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });
        }

        // Enter key to send message
        document.getElementById('message').onkeypress = function(e) {
            if (e.key === 'Enter') sendMessage();
        };
    </script>
</body>
</html>
"""
