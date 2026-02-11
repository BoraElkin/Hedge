"""Gemini vision module for image analysis.

Used for chat mode (single image uploads) as opposed to
real-time video streaming via LiveKit.
"""

from __future__ import annotations

import base64
import io
import os
from dataclasses import dataclass, field

import google.generativeai as genai
from PIL import Image

from .prompts import get_system_prompt


@dataclass
class VisionResponse:
    """Response from vision analysis."""

    message: str
    hazards: list[str] = field(default_factory=list)
    objects_detected: list[str] = field(default_factory=list)
    suggested_action: str | None = None
    confidence: float = 0.8


class GeminiVision:
    """Analyze images using Gemini's vision capabilities.

    Used for chat mode where users send individual photos
    rather than streaming video.
    """

    def __init__(self) -> None:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel("gemini-2.0-flash-exp")

    def resize_if_needed(self, image_data: bytes, max_size: int = 1568) -> bytes:
        """Resize image if larger than max_size while preserving aspect ratio."""
        img = Image.open(io.BytesIO(image_data))

        if max(img.size) <= max_size:
            return image_data

        ratio = max_size / max(img.size)
        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        # Convert to RGB if necessary (for PNG with transparency)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(buffer, format="JPEG", quality=85)
        return buffer.getvalue()

    def analyze(
        self,
        image_data: bytes,
        task_context: str,
        user_message: str | None = None,
        task_template: str = "general",
    ) -> VisionResponse:
        """Analyze an image in the context of the current task.

        Args:
            image_data: Raw image bytes (JPEG, PNG, etc.)
            task_context: Description of what the worker is doing
            user_message: Optional question or comment from the user
            task_template: Task template ID for specialized prompts
        """
        # Resize if needed
        image_data = self.resize_if_needed(image_data)

        # Build the prompt
        system_prompt = get_system_prompt(task_template, task_context)

        user_prompt = self._build_analysis_prompt(task_context, user_message)

        # Create image part for Gemini
        image_part = {
            "mime_type": "image/jpeg",
            "data": base64.b64encode(image_data).decode("utf-8"),
        }

        # Call Gemini
        response = self._model.generate_content(
            [
                system_prompt,
                image_part,
                user_prompt,
            ],
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=1024,
            ),
        )

        return self._parse_response(response.text)

    def quick_check(
        self,
        image_data: bytes,
        question: str,
    ) -> str:
        """Quick visual check - ask a simple question about the image."""
        image_data = self.resize_if_needed(image_data)

        image_part = {
            "mime_type": "image/jpeg",
            "data": base64.b64encode(image_data).decode("utf-8"),
        }

        response = self._model.generate_content(
            [image_part, question],
            generation_config=genai.types.GenerationConfig(
                temperature=0.5,
                max_output_tokens=512,
            ),
        )

        return response.text

    def _build_analysis_prompt(
        self,
        task_context: str,
        user_message: str | None = None,
    ) -> str:
        """Build the analysis prompt."""
        prompt = f"""Look at this image. The technician is working on: {task_context}

"""
        if user_message:
            prompt += f"They're asking: {user_message}\n\n"

        prompt += """Provide helpful guidance:

1. Describe what you see that's relevant to their task
2. Point out any safety hazards immediately (say STOP if critical)
3. Tell them what to do next - one clear step at a time
4. If you can't see clearly, ask them to adjust the camera

Be concise and talk like a helpful senior technician, not a robot."""

        return prompt

    def _parse_response(self, raw: str) -> VisionResponse:
        """Parse the response from Gemini."""
        # Extract hazards if mentioned
        hazards = []
        hazard_keywords = ["STOP", "WARNING", "DANGER", "CAUTION", "hazard", "unsafe"]
        for keyword in hazard_keywords:
            if keyword.lower() in raw.lower():
                # Try to extract the hazard description
                lines = raw.split("\n")
                for line in lines:
                    if keyword.lower() in line.lower():
                        hazards.append(line.strip())
                        break

        return VisionResponse(
            message=raw,
            hazards=hazards,
            confidence=0.85,
        )


# Singleton instance
_vision_instance: GeminiVision | None = None


def get_vision() -> GeminiVision:
    """Get or create the Gemini vision instance."""
    global _vision_instance
    if _vision_instance is None:
        _vision_instance = GeminiVision()
    return _vision_instance
