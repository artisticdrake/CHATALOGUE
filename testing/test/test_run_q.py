import pytest
from unittest.mock import MagicMock, patch

import run_query


# ============================================================
# connect_db / disconnect_db
# ============================================================

@patch("sqlite3.connect")
def test_connect_db(mock_connect):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor

    conn, cursor = run_query.connect_db()

    assert conn is mock_conn
    assert cursor is mock_cursor
    mock_connect.assert_called_once_with(run_query.DB_PATH)


def test_disconnect_db():
    mock_conn = MagicMock()

    run_query.disconnect_db(mock_conn)

    mock_conn.commit.assert_called_once()
    mock_conn.close.assert_called_once()


# ============================================================
# run_subquery
# ============================================================

def test_run_subquery_basic():
    mock_cursor = MagicMock()

    # Fake cursor behavior
    mock_cursor.description = [("course_number",), ("section",), ("instructor",)]
    mock_cursor.fetchall.return_value = [
        ("CAS MA 226", "A1", "Goh"),
        ("CAS MA 226", "A2", "Goh")
    ]

    subquery = {
        "sql_string": "SELECT * FROM public_classes WHERE course_number LIKE ?",
        "sql_params": ["%cas ma 226%"]
    }

    results = run_query.run_subquery(mock_cursor, subquery)

    # SQL executed correctly
    mock_cursor.execute.assert_called_once_with(
        "SELECT * FROM public_classes WHERE course_number LIKE ?",
        ["%cas ma 226%"]
    )

    # Rows converted correctly
    assert results == [
        {"course_number": "CAS MA 226", "section": "A1", "instructor": "Goh"},
        {"course_number": "CAS MA 226", "section": "A2", "instructor": "Goh"},
    ]


# ============================================================
# handle_request
# ============================================================

@patch("run_query.disconnect_db")
@patch("run_query.connect_db")
def test_handle_request(mock_connect_db, mock_disconnect_db):
    # Mock database connection + cursor
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_connect_db.return_value = (mock_conn, mock_cursor)

    # Fake cursor description + results for both queries
    mock_cursor.description = [("course_number",), ("section",)]
    mock_cursor.fetchall.side_effect = [
        [("MET CS 232", "A1")],
        [("MET CS 342", "A1")]
    ]

    payload = {
        "subqueries": [
            {"sql_string": "SELECT * FROM X", "sql_params": []},
            {"sql_string": "SELECT * FROM Y", "sql_params": []},
        ]
    }

    results = run_query.handle_request(payload)

    # Should return list of subquery results
    assert results == [
        [{"course_number": "MET CS 232", "section": "A1"}],
        [{"course_number": "MET CS 342", "section": "A1"}]
    ]

    # Ensure both queries executed
    assert mock_cursor.execute.call_count == 2
    mock_disconnect_db.assert_called_once_with(mock_conn)


# ============================================================
# run_subquery – missing params should not crash
# ============================================================

def test_run_subquery_missing_sql_params():
    mock_cursor = MagicMock()

    mock_cursor.description = [("course_number",), ("section",)]
    mock_cursor.fetchall.return_value = [("CS 101", "B2")]

    subquery = {
        "sql_string": "SELECT * FROM table",
        # sql_params intentionally missing → should default to []
    }

    results = run_query.run_subquery(mock_cursor, subquery)

    mock_cursor.execute.assert_called_once_with("SELECT * FROM table", [])
    assert results == [{"course_number": "CS 101", "section": "B2"}]
