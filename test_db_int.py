import pytest
from UNIGUIDE import db_interface as db


# ============================================================
# build_query_params
# ============================================================

def test_build_query_params_basic():
    params = db.build_query_params(
        course_code="MA 242",
        instructor_name=None,
        weekdays=None,
        requested_attributes=["instructor"]
    )

    # Base column requirements
    assert "course_number" in params["select_columns"]
    assert "instructor" in params["select_columns"]

    # Course number LIKE condition added
    wc = params["where_conditions"]
    assert any("course_number" == c["column"] for c in wc)
    assert any("%ma 242%" == c["value"] for c in wc)


def test_build_query_params_with_section():
    params = db.build_query_params(
        course_code="MA 242 A1",
        instructor_name=None,
        weekdays=None,
        requested_attributes=["all"]
    )

    wc = params["where_conditions"]
    assert {"column": "section", "operator": "=", "value": "A1"} in wc


def test_build_query_params_with_instructor():
    params = db.build_query_params(
        course_code=None,
        instructor_name="Smith",
        weekdays=None,
        requested_attributes=[]
    )

    wc = params["where_conditions"]
    assert any(c["column"] == "instructor" for c in wc)
    assert any(c["value"] == "%smith%" for c in wc)


def test_build_query_params_weekdays():
    params = db.build_query_params(
        course_code=None,
        instructor_name=None,
        weekdays=["Mon", "Fri"],
        requested_attributes=[]
    )

    wc = params["where_conditions"]
    assert any(c["value"] == "%M%" for c in wc)
    assert any(c["value"] == "%F%" for c in wc)


# ============================================================
# build_sql_string
# ============================================================

def test_build_sql_string():
    qp = {
        "select_columns": ["course_number", "section"],
        "where_conditions": [
            {"column": "course_number", "operator": "LIKE", "value": "%ma 242%", "case_insensitive": True},
            {"column": "section", "operator": "=", "value": "A1"}
        ],
        "order_by": ["course_number ASC"]
    }

    sql, params = db.build_sql_string(qp)

    assert "SELECT course_number, section FROM public_classes" in sql
    assert "LOWER(course_number) LIKE ?" in sql
    assert "section = ?" in sql
    assert "ORDER BY course_number ASC" in sql

    assert params == ["%ma 242%", "A1"]


# ============================================================
# Helper functions
# ============================================================

def test_normalize_course_code():
    assert db._normalize_course_code("CS-575") == "cs 575"
    assert db._normalize_course_code("  MA   226 ") == "ma 226"


def test_get_select_columns_deduplication():
    cols = db._get_select_columns(["all", "instructor"])
    assert cols.count("instructor") == 1
    assert "location" in cols
    assert "days" in cols


# ============================================================
# process_semantic_query
# ============================================================

def test_process_semantic_query_basic():
    semantic = {
        "primary_intent": "instructor_lookup",
        "course_codes": ["MA 226"],
        "instructor_names": [],
        "weekdays": [],
        "requested_attributes": ["instructor"]
    }

    result = db.process_semantic_query(semantic)
    subq = result["subqueries"][0]

    assert subq["intent"] == "instructor_lookup"
    assert "SELECT" in subq["sql_string"]
    assert "%ma 226%" in subq["sql_params"][0]


def test_process_semantic_query_no_entities_skips_query():
    semantic = {
        "primary_intent": "chitchat",
        "course_codes": [],
        "instructor_names": [],
        "weekdays": [],
        "requested_attributes": []
    }

    result = db.process_semantic_query(semantic)
    subq = result["subqueries"][0]

    assert subq["sql_string"] is None
    assert subq["query_params"] is None


def test_process_semantic_multiple_course_codes():
    semantic = {
        "primary_intent": "course_info",
        "course_codes": ["MA 226", "MA 242"],
        "requested_attributes": ["instructor"],
        "instructor_names": [],
        "weekdays": []
    }

    result = db.process_semantic_query(semantic)

    # Should create 2 subqueries
    assert len(result["subqueries"]) == 2
    assert "%ma 226%" in result["subqueries"][0]["sql_params"][0]
    assert "%ma 242%" in result["subqueries"][1]["sql_params"][0]


# ============================================================
# inject_db_results
# ============================================================

def test_inject_db_results():
    query_result = {
        "subqueries": [
            {"index": 0},
            {"index": 1}
        ]
    }

    db_rows = [
        [{"course": "A"}],
        [{"course": "B"}]
    ]

    final = db.inject_db_results(query_result, db_rows)

    assert final["subresults"][0]["rows"] == [{"course": "A]()
