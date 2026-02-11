#!/usr/bin/env python3
"""Seed the database with initial task templates.

Usage:
    python scripts/seed_tasks.py

This is informational - task templates are stored in code (prompts.py),
not in the database. This script just verifies the templates are valid.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.agent.prompts import TASK_TEMPLATES, get_system_prompt


def main():
    print("HVAC Copilot - Task Templates\n")
    print("=" * 60)

    for task_id, template in TASK_TEMPLATES.items():
        print(f"\n[{task_id}]")
        print(f"  Name: {template['name']}")
        print(f"  Description: {template['description']}")
        print(f"  Safety notes: {len(template['safety_notes'])}")

        # Test that the prompt generates correctly
        prompt = get_system_prompt(task_id)
        print(f"  Prompt length: {len(prompt)} chars")

    print("\n" + "=" * 60)
    print(f"\nTotal templates: {len(TASK_TEMPLATES)}")
    print("\nAll templates valid!")


if __name__ == "__main__":
    main()
