"""Voice processing - speech-to-text and text-to-speech."""

from __future__ import annotations

import io
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from guide.config import get_settings


@dataclass
class TranscriptionResult:
    text: str
    confidence: float
    language: str = "en"


class VoiceProcessor:
    """Handles speech-to-text and text-to-speech conversion."""

    def __init__(self) -> None:
        settings = get_settings()
        self._openai_key = settings.openai_api_key
        self._anthropic_key = settings.anthropic_api_key

    def transcribe(self, audio_data: bytes, format: str = "webm") -> TranscriptionResult:
        """Convert speech to text using OpenAI Whisper API.

        Args:
            audio_data: Raw audio bytes
            format: Audio format (webm, mp3, wav, etc.)
        """
        if not self._openai_key:
            raise ValueError("OpenAI API key required for speech-to-text")

        # Write to temp file (Whisper API requires file upload)
        with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as f:
            f.write(audio_data)
            temp_path = Path(f.name)

        try:
            with open(temp_path, "rb") as audio_file:
                response = httpx.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self._openai_key}"},
                    files={"file": (f"audio.{format}", audio_file)},
                    data={
                        "model": "whisper-1",
                        "response_format": "json",
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                result = response.json()

                return TranscriptionResult(
                    text=result.get("text", ""),
                    confidence=0.9,  # Whisper doesn't return confidence
                    language=result.get("language", "en"),
                )
        finally:
            temp_path.unlink(missing_ok=True)

    def synthesize(
        self,
        text: str,
        voice: str = "nova",
        speed: float = 1.0,
    ) -> bytes:
        """Convert text to speech using OpenAI TTS API.

        Args:
            text: Text to speak
            voice: Voice to use (alloy, echo, fable, onyx, nova, shimmer)
            speed: Speech speed (0.25 to 4.0)

        Returns:
            MP3 audio bytes
        """
        if not self._openai_key:
            raise ValueError("OpenAI API key required for text-to-speech")

        response = httpx.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {self._openai_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "tts-1",
                "input": text,
                "voice": voice,
                "speed": speed,
                "response_format": "mp3",
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.content

    def synthesize_streaming(
        self,
        text: str,
        voice: str = "nova",
        speed: float = 1.0,
    ):
        """Stream text-to-speech audio chunks.

        Yields MP3 audio chunks as they're generated.
        """
        if not self._openai_key:
            raise ValueError("OpenAI API key required for text-to-speech")

        with httpx.stream(
            "POST",
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {self._openai_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "tts-1",
                "input": text,
                "voice": voice,
                "speed": speed,
                "response_format": "mp3",
            },
            timeout=60.0,
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes(chunk_size=4096):
                yield chunk


class BrowserVoice:
    """Helper for using browser-native speech APIs instead of paid APIs.

    This class provides the format/interface for client-side voice processing.
    The actual speech recognition and synthesis happens in the browser using
    the Web Speech API, which is free and works offline.
    """

    @staticmethod
    def get_client_config() -> dict:
        """Return configuration for client-side speech handling."""
        return {
            "speechRecognition": {
                "continuous": True,
                "interimResults": True,
                "language": "en-US",
            },
            "speechSynthesis": {
                "rate": 1.0,
                "pitch": 1.0,
                "volume": 1.0,
                # Browser will use default voice; can be overridden
                "preferredVoices": ["Google US English", "Samantha", "Alex"],
            },
        }
