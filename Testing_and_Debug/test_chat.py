import unittest

import tkinter as tk
import chat_window


# ------------------------------------------------------------
#  Utility Function Tests (no mocks required)
# ------------------------------------------------------------

def test_hex_to_rgb():
    assert chat_window.hex_to_rgb("#ffffff") == (255, 255, 255)
    assert chat_window.hex_to_rgb("#000000") == (0, 0, 0)
    assert chat_window.hex_to_rgb("#ff0000") == (255, 0, 0)


def test_rgb_to_hex():
    assert chat_window.rgb_to_hex((255, 255, 255)) == "#ffffff"
    assert chat_window.rgb_to_hex((0, 0, 0)) == "#000000"


def test_blend_mid():
    assert chat_window.blend((0, 0, 0), (255, 255, 255), 0.5) == (127, 127, 127)


def test_now_ts():
    ts = chat_window.now_ts()
    assert isinstance(ts, str)
    assert len(ts) >= 4


# ------------------------------------------------------------
#  ChatBubble Tests (no mocks required)
# ------------------------------------------------------------

def test_chatbubble_creation():
    root = tk.Tk()
    root.withdraw()

    bubble = chat_window.ChatBubble(root, "Hello world", sender="user")

    assert bubble.text == "Hello world"
    assert bubble.sender == "user"

    root.destroy()


def test_chatbubble_clipboard_copy():
    root = tk.Tk()
    root.withdraw()

    bubble = chat_window.ChatBubble(root, "Copy this text")
    bubble.copy_to_clipboard()

    assert root.clipboard_get() == "Copy this text"

    root.destroy()


# ------------------------------------------------------------
#  ChatApp Tests (runs without mocks)
# ------------------------------------------------------------

def test_chatapp_initialization():
    app = chat_window.ChatApp()
    app.withdraw()

    # verify widgets exist
    assert hasattr(app, "chat_canvas")
    assert hasattr(app, "user_input")
    assert hasattr(app, "chat_frame")

    app.destroy()


def test_add_user_message():
    app = chat_window.ChatApp()
    app.withdraw()

    app.add_user("test message")

    assert "You: test message" in app.history
    assert len(app.history) == 2

    app.destroy()


def test_add_bot_message():
    app = chat_window.ChatApp()
    app.withdraw()

    app.add_bot("bot reply")

    assert "Bot: bot reply" in app.history
    assert len(app.history) == 2

    app.destroy()


def test_copy_all_copies_to_clipboard():
    app = chat_window.ChatApp()
    app.withdraw()

    app.add_user("one")
    app.add_bot("two")
    app.copy_all()

    clip = app.clipboard_get()
    assert "one" in clip
    assert "two" in clip

    app.destroy()


def test_clear_chat_removes_history():
    app = chat_window.ChatApp()
    app.withdraw()

    app.add_user("hi")
    app.add_bot("yo")

    app.clear_chat()

    assert app.history == ['Bot:  Welcome to Chatalogue, your campus companion! Ask me about courses, '
 'campus life, or support.']

    app.destroy()

if __name__ == "__main__":
    unittest.main()