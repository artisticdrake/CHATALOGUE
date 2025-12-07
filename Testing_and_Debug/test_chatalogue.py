import pytest
import chatalogue


# -------------------------------------------------------
# Test: call_external_db_service
# -------------------------------------------------------

def test_call_external_db_service(monkeypatch):
    """Ensure DB service is invoked and response is returned."""

    # Fake DB handler
    def fake_handler(req):
        return [[{"course_number": "CS101"}]]

    # Patch run_query.handle_request
    monkeypatch.setitem(
        chatalogue.sys.modules,
        "run_query",
        type("X", (), {"handle_request": fake_handler})
    )

    out = chatalogue.call_external_db_service({"subqueries": [{}]})
    assert out == [[{"course_number": "CS101"}]]


# -------------------------------------------------------
# Test: ConversationContext.reset()
# -------------------------------------------------------

def test_context_reset():
    ctx = chatalogue.ConversationContext()

    # Give the context some fake state
    ctx.active_course = "CS200"
    ctx.active_instructor = "John Smith"
    ctx.active_weekdays = ["Mon", "Wed"]
    ctx.turn_count = 5
    ctx.known_facts["CS200"] = {"location": "Bldg A"}

    ctx.reset()

    assert ctx.active_course is None
    assert ctx.active_instructor is None
    assert ctx.active_weekdays == []
    assert ctx.turn_count == 0
    assert ctx.known_facts == {}
    assert ctx.conversation_history == []


# -------------------------------------------------------
# Test: ConversationContext.compress()
# -------------------------------------------------------

def test_context_compress():
    ctx = chatalogue.ConversationContext()

    ctx.active_course = "CS350"
    ctx.active_instructor = "Lee"
    ctx.active_weekdays = ["Tue", "Thu"]
    ctx.known_facts["CS350"] = {"location": "ENG-101", "times": "10:00"}

    out = ctx.compress()

    assert "Course: CS350" in out
    assert "Instructor: Lee" in out
    assert "Days: Tue, Thu" in out
    assert "Location: ENG-101" in out
    assert "10:00" in out


# -------------------------------------------------------
# Test: should_reset_context
# -------------------------------------------------------

def test_should_reset_context_topic_change():
    ctx = chatalogue.ConversationContext()
    ctx.active_course = "CS100"

    semantic = {"course_codes": ["MATH200"]}

    # new course unrelated → should reset
    assert ctx.should_reset_context("tell me about math instead", semantic) is True


# -------------------------------------------------------
# Test: format_db_results_for_rag
# -------------------------------------------------------

def test_format_db_results_for_rag():
    db_result = {
        "subresults": [
            {
                "intent": "course_info",
                "course_code_used": "CS101",
                "rows": [
                    {
                        "course_number": "CS101",
                        "section": "A",
                        "course_name": "Intro",
                        "instructor": "Dr. X",
                        "days": "MW",
                        "times": "9AM",
                        "location": "Room 10"
                    }
                ]
            }
        ]
    }

    txt = chatalogue.format_db_results_for_rag(db_result)

    assert "Course: CS101" in txt
    assert "Intro" in txt
    assert "Dr. X" in txt
    assert "Room 10" in txt


# -------------------------------------------------------
# Test: rag_answer_with_db (intercept OpenAI call)
# -------------------------------------------------------

def test_rag_answer_no_openai(monkeypatch):
    """We intercept OpenAI client so rag_answer returns a stubbed answer."""

    def fake_chat_completion(*args, **kwargs):
        class R:
            choices = [type("X", (), {"message": type("Y", (), {"content": "FAKE"})})]
        return R()

    fake_client = type(
        "FakeOpenAI",
        (),
        {"chat": type("Z", (), {"completions": type("C", (), {"create": fake_chat_completion})})}
    )()

    monkeypatch.setattr(chatalogue, "client", fake_client)

    ctx = chatalogue.ConversationContext()

    out = chatalogue.rag_answer_with_db(
        user_text="hi",
        context=ctx,
        semantic={},
        db_result={"subresults": []}
    )

    assert out == "FAKE"


# -------------------------------------------------------
# Test: chat_loop (fully isolated)
# -------------------------------------------------------

def test_chat_loop_basic(monkeypatch):
    """Test main chat flow with stubbed components."""

    # Stub semantic parser
    def fake_semantic(text, ctx):
        return {"primary_intent": "greeting"}

    # Stub process semantic query
    def fake_process_semantic(sem):
        return {"subqueries": []}

    # Stub DB call
    def fake_db(req):
        return [[]]

    # Stub result injector
    def fake_inject(req, rows):
        return {"subresults": []}

    # Stub RAG
    def fake_rag(a, b, c, d):
        return "Hello!"

    monkeypatch.setattr(chatalogue, "build_semantic_parse", fake_semantic)
    monkeypatch.setattr(chatalogue, "process_semantic_query", fake_process_semantic)
    monkeypatch.setattr(chatalogue, "call_external_db_service", fake_db)
    monkeypatch.setattr(chatalogue, "inject_db_results", fake_inject)
    monkeypatch.setattr(chatalogue, "rag_answer_with_db", fake_rag)

    response = chatalogue.chat_loop("Hello")

    assert response == "Hello!"
