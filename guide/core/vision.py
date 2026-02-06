"""Vision analysis using Claude's multimodal capabilities."""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from typing import Literal

import anthropic
from PIL import Image

from guide.config import get_settings


@dataclass
class VisualContext:
    """What the AI sees in the current frame."""

    description: str
    objects_detected: list[str] = field(default_factory=list)
    hazards: list[str] = field(default_factory=list)
    relevant_details: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0


@dataclass
class VisualAnalysis:
    """Full analysis result from vision system."""

    context: VisualContext
    raw_response: str
    suggested_action: str | None = None
    warnings: list[str] = field(default_factory=list)


class VisionAnalyzer:
    """Analyzes images using Claude's vision capabilities."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.default_model

    def encode_image(self, image_data: bytes, format: str = "jpeg") -> str:
        """Encode image bytes to base64."""
        return base64.standard_b64encode(image_data).decode("utf-8")

    def resize_if_needed(self, image_data: bytes, max_size: int = 1568) -> bytes:
        """Resize image if larger than max_size while preserving aspect ratio."""
        img = Image.open(io.BytesIO(image_data))

        if max(img.size) <= max_size:
            return image_data

        ratio = max_size / max(img.size)
        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return buffer.getvalue()

    def analyze(
        self,
        image_data: bytes,
        task_context: str,
        current_step: str | None = None,
        trade: str = "general",
        media_type: Literal["image/jpeg", "image/png", "image/webp", "image/gif"] = "image/jpeg",
    ) -> VisualAnalysis:
        """Analyze an image in the context of the current task.

        Args:
            image_data: Raw image bytes
            task_context: Description of what the worker is trying to accomplish
            current_step: The current step they're on, if any
            trade: The trade/domain (e.g., "hvac", "plumbing", "electrical")
            media_type: MIME type of the image
        """
        image_data = self.resize_if_needed(image_data)
        b64_image = self.encode_image(image_data)

        system_prompt = self._build_system_prompt(trade)
        user_prompt = self._build_analysis_prompt(task_context, current_step)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64_image,
                            },
                        },
                        {
                            "type": "text",
                            "text": user_prompt,
                        },
                    ],
                }
            ],
        )

        raw = response.content[0].text
        return self._parse_response(raw)

    def quick_check(
        self,
        image_data: bytes,
        question: str,
        media_type: Literal["image/jpeg", "image/png", "image/webp", "image/gif"] = "image/jpeg",
    ) -> str:
        """Quick visual check - ask a simple question about what's in the image."""
        image_data = self.resize_if_needed(image_data)
        b64_image = self.encode_image(image_data)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64_image,
                            },
                        },
                        {
                            "type": "text",
                            "text": question,
                        },
                    ],
                }
            ],
        )

        return response.content[0].text

    def _build_system_prompt(self, trade: str) -> str:
        base = """You are an expert AI assistant helping a worker complete physical tasks.
You can see through their camera and provide real-time guidance.

Your role is to:
1. Accurately describe what you see
2. Identify any safety hazards immediately
3. Recognize tools, parts, and equipment
4. Guide the worker through their task step by step
5. Point out potential problems before they happen

Be concise but thorough. Safety first, always."""

        trade_additions = {
            "hvac": """
You are specialized in HVAC systems. You can identify:
- AC units, furnaces, heat pumps, ductwork
- Refrigerant lines, condensate drains, electrical connections
- Common issues: dirty filters, frozen coils, faulty capacitors
- Required tools: manifold gauges, multimeter, vacuum pump""",

            "plumbing": """
You are specialized in plumbing. You can identify:
- Pipe types (copper, PVC, PEX, galvanized)
- Fixtures, valves, fittings, traps
- Common issues: leaks, clogs, corrosion, improper venting
- Required tools: pipe wrenches, cutters, soldering equipment""",

            "electrical": """
You are specialized in electrical work. You can identify:
- Wire gauges, panel types, circuit breakers
- Outlets, switches, junction boxes, conduit
- CRITICAL: Always verify power is OFF before any work
- Common issues: overloaded circuits, improper grounding, code violations""",

            "automotive": """
You are specialized in automotive repair. You can identify:
- Engine components, fluids, belts, hoses
- Suspension, brakes, steering components
- Common issues: wear patterns, leaks, damage indicators
- Required tools: socket sets, torque wrenches, diagnostic tools""",

            "general": """
You have broad knowledge across trades and can help with general repairs,
maintenance, and assembly tasks.""",
        }

        return base + trade_additions.get(trade, trade_additions["general"])

    def _build_analysis_prompt(self, task_context: str, current_step: str | None) -> str:
        prompt = f"""Analyze this image. The worker is trying to: {task_context}

"""
        if current_step:
            prompt += f"They are currently on this step: {current_step}\n\n"

        prompt += """Provide your analysis in this format:

WHAT I SEE: [Describe the scene, equipment, and relevant details]

HAZARDS: [List any safety concerns - say "None visible" if none]

OBJECTS: [List key objects/tools/parts visible]

ASSESSMENT: [Is the current situation correct for the task? What needs attention?]

NEXT ACTION: [What should the worker do next?]"""

        return prompt

    def _parse_response(self, raw: str) -> VisualAnalysis:
        """Parse the structured response from Claude."""
        context = VisualContext(description="", confidence=0.8)
        suggested_action = None
        warnings = []

        sections = {
            "WHAT I SEE:": "description",
            "HAZARDS:": "hazards",
            "OBJECTS:": "objects",
            "ASSESSMENT:": "assessment",
            "NEXT ACTION:": "action",
        }

        current_section = None
        current_content = []

        for line in raw.split("\n"):
            line = line.strip()

            # Check if this line starts a new section
            found_section = None
            for marker in sections:
                if line.upper().startswith(marker.upper()):
                    found_section = sections[marker]
                    line = line[len(marker):].strip()
                    break

            if found_section:
                # Save previous section
                if current_section and current_content:
                    self._assign_section(
                        current_section,
                        " ".join(current_content),
                        context,
                        warnings,
                    )
                current_section = found_section
                current_content = [line] if line else []
            elif current_section:
                current_content.append(line)

        # Save final section
        if current_section and current_content:
            content = " ".join(current_content)
            if current_section == "action":
                suggested_action = content
            else:
                self._assign_section(current_section, content, context, warnings)

        return VisualAnalysis(
            context=context,
            raw_response=raw,
            suggested_action=suggested_action,
            warnings=warnings,
        )

    def _assign_section(
        self,
        section: str,
        content: str,
        context: VisualContext,
        warnings: list[str],
    ) -> None:
        if section == "description":
            context.description = content
        elif section == "hazards":
            if content.lower() not in ("none", "none visible", "no hazards"):
                context.hazards = [h.strip() for h in content.split(",") if h.strip()]
                warnings.extend(context.hazards)
        elif section == "objects":
            context.objects_detected = [o.strip() for o in content.split(",") if o.strip()]
        elif section == "assessment":
            context.relevant_details["assessment"] = content
