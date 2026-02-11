"""Task templates routes."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.agent.prompts import TASK_TEMPLATES

router = APIRouter()


class TaskTemplate(BaseModel):
    id: str
    name: str
    description: str
    safety_notes: list[str]


@router.get("/", response_model=list[TaskTemplate])
async def list_tasks():
    """List all available task templates."""
    return [
        TaskTemplate(
            id=task_id,
            name=template["name"],
            description=template["description"],
            safety_notes=template["safety_notes"],
        )
        for task_id, template in TASK_TEMPLATES.items()
    ]


@router.get("/{task_id}", response_model=TaskTemplate)
async def get_task(task_id: str):
    """Get details of a specific task template."""
    if task_id not in TASK_TEMPLATES:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Task template not found")

    template = TASK_TEMPLATES[task_id]
    return TaskTemplate(
        id=task_id,
        name=template["name"],
        description=template["description"],
        safety_notes=template["safety_notes"],
    )
