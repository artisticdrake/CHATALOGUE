import pytest
from unittest.mock import patch, MagicMock

import chatalogue


@pytest.fixture(autouse=True)
def reset_globals():
    """Ensure global context is reset before each test."""
    chatalogue._global_context = None
    chatalogue._global_history = []
    yield
    chatalogue._global_context = None
    chatalogue._global_history = []


# ------------------------------------------------------------
# Helper mocks for semantic → DB pipeline
# ------------------------------------------------------------

@pytest.fixture
def mock_semantic():
    return {
        "course_codes": ["MA 242"],
        "instructor_names": [],
        "weekdays": [],
        "subqueries": [],
        "primary_intent": "lookup"
    }


@pytest.fixture
def mock_query_request():
    return {"subqueries": []}


@pytest.fixture
def mock_db_result():
    return {"subresults": []}


# ------------------------------------------------------------
# chat_loop() basic test
# ------------------------------------------------------------
def test_chat_loop_basic(mock_semantic, mock_query_request, mock_db_result):
    with patch("chatalogue.build_semantic_parse", return_value=mock_semantic), \
         patch("chatalogue.process_semantic_query", return_value=mock_query_request), \
         patch("chatalogue.call_external_db_service", return_value=[]), \
         patch("chatalogue.inject_db_results", return_value=mock_db_result), \
         patch("chatalogue.rag_answer_with_db", return_value="Test Answer"):

        resp = chatalogue.chat_loop("Where is MA 242?")
        assert resp == "Test Answer"


# ------------------------------------------------------------
# reset command
# ------------------------------------------------------------
def test_chat_loop_reset():
    ctx = chatalogue.get_or_create_context()
    ctx.active_course = "MA 242"
    assert ctx.active_course == "MA 242"

    resp = chatalogue.chat_loop("reset")
    assert resp == "Context reset. Starting fresh!"

    # Context should be completely cleared
    new_ctx = chatalogue.get_or_create_context()
    assert new_ctx.active_course is None
    assert new_ctx.turn_count == 0


# ------------------------------------------------------------
# context command
# ------------------------------------------------------------
def test_chat_loop_context():
    ctx = chatalogue.get_or_create_context()
    ctx.active_course = "CS 101"
    ctx.active_instructor = "Smith"

    expected = "Current context: Course: CS 101 | Instructor: Smith"
    resp = chatalogue.chat_loop("context")
    assert "CS 101" in resp
    assert "Smith" in resp


# ------------------------------------------------------------
# context auto-reset on topic change
# ------------------------------------------------------------
def test_context_resets_on_topic_change(mock_semantic, mock_query_request, mock_db_result):
    # First message sets context
    with patch("chatalogue.build_semantic_parse", return_value=mock_semantic), \
         patch("chatalogue.process_semantic_query", return_value=mock_query_request), \
         patch("chatalogue.call_external_db_service", return_value=[]), \
         patch("chatalogue.inject_db_results", return_value=mock_db_result), \
         patch("chatalogue.rag_answer_with_db", return_value="OK"):

        chatalogue.chat_loop("Tell me about MA 242")
        ctx = chatalogue.get_or_create_context()
        assert ctx.active_course == "MA 242"

    # Now topic change keyword forces reset
    mock_semantic2 = mock_semantic.copy()
    mock_semantic2["course_codes"] = ["BIO 101"]

    with patch("chatalogue.build_semantic_parse", return_value=mock_semantic2), \
         patch("chatalogue.process_semantic_query", return_value=mock_query_request), \
         patch("chatalogue.call_external_db_service", return_value=[]), \
         patch("chatalogue.inject_db_results", return_value=mock_db_result), \
         patch("chatalogue.rag_answer_with_db", return_value="OK"):

        chatalogue.chat_loop("Actually what about BIO 101?")
        ctx = chatalogue.get_or_create_context()
        assert ctx.active_course == "BIO 101"  # old course replaced


# ------------------------------------------------------------
# Pronoun resolution
# ------------------------------------------------------------
def test_pronoun_resolution():
    ctx = chatalogue.ConversationContext()
    ctx.active_course = "MA 242"
    sem = {
        "course_codes": [],
        "instructor_names": [],
        "weekdays": [],
        "subqueries": []
    }

    resolved = ctx.resolve_pronouns(sem, "Where is it?")
    assert resolved["course_codes"] == ["MA 242"]


# ------------------------------------------------------------
# update() stores known facts
# ------------------------------------------------------------
def test_context_update_stores_known_facts():
    ctx = chatalogue.ConversationContext()
    semantic = {"course_codes": ["CS 101"], "instructor_names": []}

    db_result = {
        "subresults": [{
            "course_code_used": "CS 101",
            "rows": [{
                "instructor": "Smith",
                "location": "CAS 200",
                "days": "MWF",
                "times": "9:00",
                "section": "B1"
            }]
        }]
    }

    ctx.update(semantic, db_result)

    assert "CS 101" in ctx.known_facts
    assert ctx.known_facts["CS 101"]["instructor"] == "Smith"
    assert ctx.active_course == "CS 101"
    assert ctx.turn_count == 1


# ------------------------------------------------------------
# error msg returned if exception occurs
# ------------------------------------------------------------
def test_chat_loop_error_handling():
    with patch("chatalogue.build_semantic_parse", side_effect=Exception("Boom!")):
        resp = chatalogue.chat_loop("hi")
        assert "something went wrong" in resp.lower()
