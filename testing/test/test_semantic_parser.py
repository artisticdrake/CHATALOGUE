import pytest
import semantic_parser


# -------------------------------------------------------------------
# Basic utilities: detect_requested_attributes & extract_section_from_text
# -------------------------------------------------------------------


def test_detect_requested_attributes_multiple_kinds():
    text = "Who teaches it, where is it, when does it meet, and what sections exist?"
    attrs = semantic_parser.detect_requested_attributes(text)

    # Order is determined by implementation, so we check content, not order
    assert set(attrs) == {"instructor", "location", "time", "sections"}


def test_extract_section_from_text_found():
    assert semantic_parser.extract_section_from_text("I'm in CS 101 section B3") == "B3"
    assert semantic_parser.extract_section_from_text("sec a1 of that course") == "A1"


def test_extract_section_from_text_not_found():
    assert semantic_parser.extract_section_from_text("I'm in CS 101") == ""


# -------------------------------------------------------------------
# NER: behavior when model is missing
# -------------------------------------------------------------------


def test_extract_entities_ner_without_model(monkeypatch):
    # Make get_ner_model return None so we exercise the "no model" path
    monkeypatch.setattr(semantic_parser, "get_ner_model", lambda: None)

    result = semantic_parser.extract_entities_ner("Who teaches CS 101?")
    expected = {
        "instructors": [],
        "course_codes": [],
        "course_names": [],
        "weekdays": [],
        "times": [],
        "buildings": [],
        "sections": [],
    }

    assert result == expected


# -------------------------------------------------------------------
# Validation: filtering department codes & obvious false positives
# -------------------------------------------------------------------


def test_validate_entities_filters_department_codes_and_keeps_valid():
    entities = {
        "instructors": ["cs", "Alice", "food"],
        "course_codes": ["CS 575"],
        "course_names": [],
        "weekdays": [],
        "times": [],
        "buildings": [],
        "sections": [],
    }

    validated = semantic_parser.validate_entities(entities)

    # "cs" and "food" should be filtered out as invalid instructors
    assert validated["instructors"] == ["Alice"]


# -------------------------------------------------------------------
# Intent override logic
# -------------------------------------------------------------------


def test_should_override_intent_with_time_attribute():
    text = "when?"
    intent = "chitchat"
    confidence = 0.2
    context_course = "CS 101"
    context_instructor = None
    has_new_entities = False
    requested_attributes = ["time"]

    should_override, new_intent = semantic_parser.should_override_intent(
        text=text,
        intent=intent,
        confidence=confidence,
        context_course=context_course,
        context_instructor=context_instructor,
        has_new_entities=has_new_entities,
        requested_attributes=requested_attributes,
    )

    assert should_override is False
    assert new_intent == None


def test_should_not_override_safe_intent():
    # "greeting" is in safe_intents in INTENT_OVERRIDE_CONFIG
    text = "hi"
    intent = "greeting"
    confidence = 0.99
    context_course = "CS 101"
    context_instructor = "Alice"
    has_new_entities = False

    should_override, new_intent = semantic_parser.should_override_intent(
        text=text,
        intent=intent,
        confidence=confidence,
        context_course=context_course,
        context_instructor=context_instructor,
        has_new_entities=has_new_entities,
        requested_attributes=None,
    )

    assert should_override is False
    assert new_intent is None


# -------------------------------------------------------------------
# Clause splitting, including course-name-aware splitting
# -------------------------------------------------------------------


def test_split_into_clauses_with_course_names(monkeypatch):
    # Force extract_entities_ner used by _split_on_and_with_course_names
    # to return two course names so that split happens.
    def fake_extract_entities_ner(text: str):
        return {
            "instructors": [],
            "course_codes": [],
            "course_names": ["Linear Algebra", "Differential Equations"],
            "weekdays": [],
            "times": [],
            "buildings": [],
            "sections": [],
        }

    monkeypatch.setattr(semantic_parser, "extract_entities_ner", fake_extract_entities_ner)

    text = "who teaches linear algebra and differential equations"
    clauses = semantic_parser.split_into_clauses(text)

    # Base query "who teaches" should be reused for each course name
    assert clauses == [
        "who teaches Linear Algebra",
        "who teaches Differential Equations",
    ]


# -------------------------------------------------------------------
# Multi-query & pronoun resolution in build_semantic_parse
# -------------------------------------------------------------------


def test_build_semantic_parse_pronoun_resolution(monkeypatch):
    """
    Scenario:
      "Who teaches CS 101 and when does it meet?"

    We want:
      - Two subqueries
      - First subquery has course_codes ["CS 101"] and intent instructor_lookup
      - Second subquery inherits course_codes ["CS 101"] via pronoun resolution and
        gets intent schedule_query (because it asks about time).
    """

    # 1) Monkeypatch classify_intent_ml to avoid real ML dependency
    def fake_classify_intent_ml(text: str):
        lower = text.lower()
        if "who" in lower:
            return {
                "primary_intent": "instructor_lookup",
                "confidence": 0.9,
                "all_intents": [],
            }
        # For the second clause & others, return "chitchat" with low confidence
        # so that _resolve_pronoun_references treats it as a pronoun query.
        return {
            "primary_intent": "chitchat",
            "confidence": 0.4,
            "all_intents": [],
        }

    monkeypatch.setattr(semantic_parser, "classify_intent_ml", fake_classify_intent_ml)

    # 2) Monkeypatch extract_all_entities_hybrid so we don't depend on NER/model
    def fake_extract_all_entities_hybrid(text: str):
        lower = text.lower()
        has_cs101 = "cs 101" in lower
        return {
            "instructors": [],
            "course_codes": ["CS 101"] if has_cs101 else [],
            "course_names": [],
            "weekdays": [],
            "times": [],
            "buildings": [],
            "sections": [],
        }

    monkeypatch.setattr(
        semantic_parser,
        "extract_all_entities_hybrid",
        fake_extract_all_entities_hybrid,
    )

    # 3) Run the parser
    query = "Who teaches CS 101 and when does it meet?"
    parsed = semantic_parser.build_semantic_parse(query)

    # Should have two subqueries (split at "and" + WH-word)
    assert len(parsed["subqueries"]) == 2

    subq1, subq2 = parsed["subqueries"]

    # First subquery: direct question about instructor, with course code
    assert "who teaches" in subq1["text"].lower()
    assert subq1["course_codes"] == ["CS 101"]
    assert subq1["intent"] == "instructor_lookup"

    # Second subquery: pronoun-like ("when does it meet") but should inherit course code
    assert "when does it meet" in subq2["text"].lower()
    # Pronoun resolution should inject the course_codes from the first query
    assert subq2["course_codes"] == ["CS 101"]
    # Based on requested_attributes (time) and presence of course_codes,
    # _resolve_pronoun_references should convert intent to schedule_query
    assert subq2["intent"] == "schedule_query"


# -------------------------------------------------------------------
# Backward-compatibility helpers
# -------------------------------------------------------------------


def test_backward_compatible_extract_helpers(monkeypatch):
    # Ensure extract_course_codes, extract_instructor_names, extract_weekdays
    # correctly delegate to extract_all_entities_hybrid.

    def fake_extract_all_entities_hybrid(text: str):
        return {
            "instructors": ["Alice"],
            "course_codes": ["CS 101"],
            "course_names": [],
            "weekdays": ["Monday"],
            "times": [],
            "buildings": [],
            "sections": [],
        }

    monkeypatch.setattr(
        semantic_parser,
        "extract_all_entities_hybrid",
        fake_extract_all_entities_hybrid,
    )

    assert semantic_parser.extract_course_codes("anything") == ["CS 101"]
    assert semantic_parser.extract_instructor_names("anything") == ["Alice"]
    assert semantic_parser.extract_weekdays("anything") == ["Monday"]
