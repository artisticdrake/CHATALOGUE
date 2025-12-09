"""
Chatalogue package: BU course & campus assistant.

Public entry points:
- chat_loop(): core single-turn conversation function
- process_user_input(): backwards-compatible alias
- ConversationContext: conversation state manager
"""

from .chatalogue import chat_loop, process_user_input, ConversationContext

__all__ = [
    "chat_loop",
    "process_user_input",
    "ConversationContext",
]
