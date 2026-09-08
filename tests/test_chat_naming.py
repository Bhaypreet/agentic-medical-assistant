"""Chats named after their opening message.

Every conversation was called "New Chat" until a report was uploaded, so
a sidebar with three of them in it gave no way to tell them apart.
"""

import uuid

from app.session.session_manager import (
    DEFAULT_CHAT_NAME,
    session_manager,
    title_from_message,
)

# ------------------------------------------------------------- titles


def test_a_short_question_is_used_verbatim():
    assert title_from_message("What is hypertension?") == "What is hypertension"


def test_a_long_message_is_clipped_on_a_word_boundary():
    title = title_from_message(
        "I have crushing chest pain radiating to my left arm and I am sweating"
    )

    assert title.endswith("...")
    assert len(title) <= 52
    # clipped between words, never mid-word
    assert not title[:-3].endswith(" ")
    assert title.split()[-1].rstrip(".") in "I have crushing chest pain radiating to my left arm"


def test_newlines_and_runs_of_space_collapse():
    assert title_from_message("what   is\n\ndiabetes") == "what is diabetes"


def test_pasted_markdown_punctuation_is_stripped():
    assert title_from_message("### Why am I dizzy?") == "Why am I dizzy"
    assert title_from_message("- my knee hurts") == "my knee hurts"


def test_empty_input_yields_no_title():
    for value in ("", "   ", "\n\n", None):
        assert title_from_message(value) == ""


# -------------------------------------------------------- persistence


def _session():
    return str(uuid.uuid4()), "owner-" + uuid.uuid4().hex[:8]


def test_the_first_message_names_the_chat():
    sid, owner = _session()
    session_manager.create_session(sid, owner=owner)

    assert session_manager.get_chat_name(sid, owner=owner) == DEFAULT_CHAT_NAME

    session_manager.ensure_chat_name(sid, "What is hypertension?", owner=owner)

    assert session_manager.get_chat_name(sid, owner=owner) == "What is hypertension"


def test_a_later_message_does_not_rename_the_chat():
    sid, owner = _session()
    session_manager.ensure_chat_name(sid, "First question", owner=owner)
    session_manager.ensure_chat_name(sid, "A completely different second question", owner=owner)

    assert session_manager.get_chat_name(sid, owner=owner) == "First question"


def test_a_report_upload_name_is_not_overwritten():
    """Uploading names the chat after the file; a later question must not
    take that away."""

    sid, owner = _session()
    session_manager.set_chat_name(sid, "bloodwork.pdf", owner=owner)
    session_manager.ensure_chat_name(sid, "what do these results mean?", owner=owner)

    assert session_manager.get_chat_name(sid, owner=owner) == "bloodwork.pdf"


def test_an_empty_message_leaves_the_default_in_place():
    sid, owner = _session()
    session_manager.create_session(sid, owner=owner)
    session_manager.ensure_chat_name(sid, "   ", owner=owner)

    assert session_manager.get_chat_name(sid, owner=owner) == DEFAULT_CHAT_NAME


def test_naming_is_scoped_to_the_owner():
    sid, owner = _session()
    session_manager.ensure_chat_name(sid, "my private question", owner=owner)

    assert session_manager.get_chat_name(sid, owner="someone-else") == DEFAULT_CHAT_NAME
