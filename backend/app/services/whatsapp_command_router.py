"""Safe, predefined routing for WhatsApp commands.

Commands are matched locally. No model is allowed to invent a tool name or call an
arbitrary application function from an inbound message.
"""

from dataclasses import dataclass
from typing import Awaitable, Callable

from app.models.whatsapp_contact import WhatsAppContact


CommandHandler = Callable[[WhatsAppContact], Awaitable[str]]


@dataclass(frozen=True)
class WhatsAppToolDefinition:
    """A user-facing command and its exact aliases."""

    name: str
    aliases: frozenset[str]
    description: str


PREDEFINED_WHATSAPP_TOOLS: tuple[WhatsAppToolDefinition, ...] = (
    WhatsAppToolDefinition("latest", frozenset({"latest", "priority", "important"}), "Show the top priority emails."),
    WhatsAppToolDefinition("start", frozenset({"start", "subscribe"}), "Enable priority alerts."),
    WhatsAppToolDefinition("stop", frozenset({"stop", "unsubscribe"}), "Pause priority alerts."),
    WhatsAppToolDefinition("help", frozenset({"help", "menu"}), "Show available commands."),
)


class PredefinedWhatsAppToolRouter:
    """Dispatch an inbound command only to one of the registered handlers."""

    def __init__(self, handlers: dict[str, CommandHandler]):
        self._handlers = handlers
        self._routes = {
            alias: definition.name
            for definition in PREDEFINED_WHATSAPP_TOOLS
            for alias in definition.aliases
        }

    async def route(self, text: str, contact: WhatsAppContact) -> str:
        """Normalize the first token and invoke its predefined handler."""
        command = (text or "").strip().lower().split(maxsplit=1)[0] if text.strip() else ""
        tool_name = self._routes.get(command)
        if tool_name is None:
            return "Reply LATEST for important emails, STOP to pause alerts, or START to resume them."
        handler = self._handlers.get(tool_name)
        if handler is None:
            return "That WhatsApp command is temporarily unavailable."
        return await handler(contact)
