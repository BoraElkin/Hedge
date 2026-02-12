"""iMessage bridge for macOS using AppleScript."""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from guide.bridges.base import (
    IncomingMessage,
    MessageBridge,
    MessageType,
    OutgoingMessage,
)


class iMessageBridge(MessageBridge):
    """iMessage integration via AppleScript (macOS only).

    Requires macOS with Messages app configured.
    """

    platform = "imessage"

    def __init__(
        self,
        on_message: Callable[[IncomingMessage], None] | None = None,
        poll_interval: int = 2,
    ):
        """Initialize iMessage bridge.

        Args:
            on_message: Callback for incoming messages
            poll_interval: How often to poll for new messages (seconds)
        """
        self.on_message = on_message
        self.poll_interval = poll_interval
        self._last_message_time = datetime.now()
        self._running = False

        # Verify we're on macOS
        if os.uname().sysname != "Darwin":
            raise RuntimeError("iMessage bridge requires macOS")

    def _run_applescript(self, script: str) -> str:
        """Execute AppleScript and return output."""
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"AppleScript error: {result.stderr}")
        return result.stdout.strip()

    async def send_message(self, message: OutgoingMessage) -> bool:
        """Send message via iMessage."""
        try:
            # Clean phone number/email for AppleScript
            recipient = message.recipient_id.strip()

            if message.text:
                # Send text message
                script = f'''
                tell application "Messages"
                    set targetService to 1st account whose service type = iMessage
                    set targetBuddy to participant "{recipient}" of targetService
                    send "{message.text}" to targetBuddy
                end tell
                '''
                self._run_applescript(script)

            if message.media_data or message.media_url:
                # Send image/file
                if message.media_data:
                    # Save to temp file
                    temp_path = Path("/tmp/guide_imessage_attachment.jpg")
                    temp_path.write_bytes(message.media_data)
                    file_path = str(temp_path)
                else:
                    file_path = message.media_url

                script = f'''
                tell application "Messages"
                    set targetService to 1st account whose service type = iMessage
                    set targetBuddy to participant "{recipient}" of targetService
                    send POSIX file "{file_path}" to targetBuddy
                end tell
                '''
                self._run_applescript(script)

                # Clean up temp file
                if message.media_data and temp_path.exists():
                    temp_path.unlink()

            return True

        except Exception as e:
            print(f"Error sending iMessage: {e}")
            return False

    async def send_text(self, recipient_id: str, text: str) -> bool:
        """Send a simple text message."""
        return await self.send_message(OutgoingMessage(
            recipient_id=recipient_id,
            text=text
        ))

    async def send_image(
        self,
        recipient_id: str,
        image_url: str | None = None,
        image_data: bytes | None = None,
        caption: str | None = None,
    ) -> bool:
        """Send an image with optional caption."""
        # Send caption first if provided
        if caption:
            await self.send_text(recipient_id, caption)

        return await self.send_message(OutgoingMessage(
            recipient_id=recipient_id,
            media_url=image_url,
            media_data=image_data
        ))

    def parse_webhook(self, payload: dict) -> IncomingMessage | None:
        """Parse webhook payload. iMessage uses polling, not webhooks."""
        # iMessage doesn't use webhooks - we poll for messages instead
        # This method is here to satisfy the abstract base class
        return None

    def _get_recent_messages(self) -> list[dict]:
        """Get recent messages using SQLite query of Messages database.

        macOS stores messages in ~/Library/Messages/chat.db
        """
        try:
            # Query the Messages database
            db_path = Path.home() / "Library/Messages/chat.db"

            # Get messages since last poll
            timestamp_ns = int(self._last_message_time.timestamp() * 1_000_000_000)

            script = f'''
            tell application "Messages"
                set messageList to {{}}
                repeat with aChat in chats
                    try
                        set recentMessages to messages of aChat whose date > (current date) - {self.poll_interval}
                        repeat with aMessage in recentMessages
                            if direction of aMessage is incoming then
                                set messageInfo to {{}}
                                set end of messageInfo to text of aMessage
                                set end of messageInfo to (id of participant 1 of aChat as string)
                                set end of messageInfo to (name of participant 1 of aChat as string)
                                set end of messageList to messageInfo
                            end if
                        end repeat
                    end try
                end repeat
                return messageList
            end tell
            '''

            result = self._run_applescript(script)

            # Parse result (format: "text, sender_id, sender_name, text2, ...")
            messages = []
            if result:
                parts = result.split(", ")
                for i in range(0, len(parts), 3):
                    if i + 2 < len(parts):
                        messages.append({
                            "text": parts[i],
                            "sender_id": parts[i + 1],
                            "sender_name": parts[i + 2],
                        })

            return messages

        except Exception as e:
            print(f"Error reading messages: {e}")
            return []

    async def _poll_messages(self):
        """Poll for new messages."""
        while self._running:
            try:
                messages = self._get_recent_messages()

                for msg_data in messages:
                    incoming = IncomingMessage(
                        platform="imessage",
                        sender_id=msg_data["sender_id"],
                        sender_name=msg_data.get("sender_name"),
                        message_type=MessageType.TEXT,
                        text=msg_data["text"],
                        timestamp=datetime.now(),
                        raw_payload=msg_data,
                    )

                    if self.on_message:
                        if asyncio.iscoroutinefunction(self.on_message):
                            await self.on_message(incoming)
                        else:
                            self.on_message(incoming)

                self._last_message_time = datetime.now()

            except Exception as e:
                print(f"Error polling messages: {e}")

            await asyncio.sleep(self.poll_interval)

    async def start(self):
        """Start listening for messages."""
        self._running = True
        await self._poll_messages()

    async def stop(self):
        """Stop listening for messages."""
        self._running = False
