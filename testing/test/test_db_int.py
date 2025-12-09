import pytest
import db_interface as db


# -------------------------------------------------------
# Test: _normalize_course_code
# -------------------------------------------------------

def test_normalize_course_code():
    assert db._normalize_course_code("CS 350") == "cs350"
    assert db._normalize_course_code(" CS-111 ") == "cs111"
    assert db._normalize_course_code("") == ""
    assert db._normalize_course_code(None) == ""


# -------------------------------------------------------
# Test: _get_select_columns
# -------------------------------------------------------

def test_get_select_columns():
    # default attrs → should include all base columns
    cols = db._get_select_columns([])
    assert "course_number" in cols
    assert "instructor" in cols
    assert "times" in cols

    # explicitly request "location"
    cols = db._get_select_columns(["location"])
    assert "location" in cols

    # invalid attribute falls back to "all"
    cols = db._get_select_columns(["does_not_exist"])
    assert "course_name" in cols
    assert "times" in cols


# -------------------------------------------------------
# Test: build_query_params
# -------------------------------------------------------

def test_build_query_params_basic():
    qp = db.build_query_params(
        course_code="CS 350 A1",
        instructor_name="Lee",
        weekdays=["Mon", "Wed"],
        requested_attributes=["all"]
    )

    assert "select_columns" in qp
    assert len(qp["where_conditions"]) >= 3  # course + section + weekdays
    assert qp["order_by"] == ["course_number ASC", "section ASC"]

    # check section extracted correctly
    section_filter = [c for c in qp["where_conditions"] if c["column"] == "section"][0]
    assert section_filter["value"] == "A1"

    # instructor LIKE
    instr = [c for c in qp["where_conditions"] if c["column"] == "instructor"][0]
    assert "%lee%" in instr["value"]


# -------------------------------------------------------
# Test: build_sql_string
# -------------------------------------------------------

def test_build_sql_string():
    qp = {
        "select_columns": ["course_number", "instructor"],
        "where_conditions": [
            {
                "column": "course_number",
                "operator": "LIKE",
                "value": "%cs350%",
                "case_insensitive": True
            }
        ],
        "order_by": ["course_number ASC"]
    }

    sql, params = db.build_sql_string(qp)

    assert "SELECT course_number, instructor FROM public_classes" in sql
    assert "WHERE REPLACE(LOWER(course_number)," in sql
    assert params == ["%cs350%"]


# -------------------------------------------------------
# Test: needs_fuzzy_search
# -------------------------------------------------------

def test_needs_fuzzy_search():
    sem = {
        "course_codes": [],
        "course_name_queries": ["Intro to Something"],
        "primary_intent": "course_info",
    }

    assert db.needs_fuzzy_search(sem) is True

    sem2 = {
        "course_codes": ["CS101"],
        "course_name_queries": ["Intro"],
        "primary_intent": "course_info",
    }
    assert db.needs_fuzzy_search(sem2) is False


# -------------------------------------------------------
# Test: build_fuzzy_search_request
# -------------------------------------------------------

def test_build_fuzzy_search_request():
    sem = {"course_name_queries": ["Networks", "Security"]}
    req = db.build_fuzzy_search_request(sem)

    assert req["query_type"] == "fuzzy_course_search"
    assert req["search_term"] == "Networks"
    assert req["remaining_course_names"] == ["Security"]


# -------------------------------------------------------
# Test: process_semantic_query – fuzzy search stage
# -------------------------------------------------------

def test_process_semantic_query_fuzzy():
    sem = {
        "course_name_queries": ["Data Structures"],
        "primary_intent": "course_info",
        "course_codes": [],
    }

    out = db.process_semantic_query(sem)

    assert out["query_type"] == "fuzzy_course_search"
    assert out["search_term"] == "Data Structures"


# -------------------------------------------------------
# Test: process_semantic_query – non-fuzzy SQL generation
# -------------------------------------------------------

def test_process_semantic_query_sql():
    sem = {
        "primary_intent": "instructor_lookup",
        "course_codes": ["CS350"],
        "instructor_names": ["Smith"],
        "weekdays": [],
        "requested_attributes": ["instructor"]
    }

    out = db.process_semantic_query(sem)
    sub = out["subqueries"][0]

    assert "SELECT" in sub["sql_string"]
    assert "FROM public_classes" in sub["sql_string"]
    assert "%cs350%" in sub["sql_params"][0]
    assert "%smith%" in sub["sql_params"][1]


# -------------------------------------------------------
# Test: _resolve_subqueries
# -------------------------------------------------------

def test_resolve_subqueries_single():
    sem = {
        "primary_intent": "course_time",
        "course_codes": ["CS101"],
        "requested_attributes": ["time"],
        "raw_text": "when is CS101"
    }

    out = db._resolve_subqueries(sem)
    assert len(out) == 1
    assert out[0]["course_codes"] == ["CS101"]
    assert out[0]["requested_attributes"] == ["time"]

    # -------------------------------------------------------
    # Test: inject_db_results
    # -------------------------------------------------------


def test_inject_db_results():
    query_result = {
        "subqueries": [
            {"index": 0},
            {"index": 1},
        ]
    }

    db_rows = [
        [{"row": 1}],
        [{"row": 2}],
    ]

    out = db.inject_db_results(query_result, db_rows)
    assert out["subresults"][0]["rows"] == [{"row": 1}]
    assert out["subresults"][1]["rows"] == [{"row": 2}]

    # -------------------------------------------------------
    # Test: weekdays mapping in build_query_params
    # -------------------------------------------------------


def test_build_query_params_weekdays():
    qp = db.build_query_params(
        course_code=None,
        instructor_name=None,
        weekdays=["Mon", "Thursday"],
        requested_attributes=[]
    )

    conds = [c for c in qp["where_conditions"] if c["column"] == "days"]
    assert len(conds) == 2
    # "Mon" → "M"
    assert "%m%" in conds[0]["value"]
    # "Thursday" → "R"
    assert "%r%" in conds[1]["value"]
