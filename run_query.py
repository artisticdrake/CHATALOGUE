import sqlite3
import json
import sys
from typing import Any, Dict, List, Tuple

DB_PATH = "courses_metcs.sqlite"
TABLE_NAME = "public_classes"


# -------------------------------
# DB helpers
# -------------------------------

def connect_db() -> Tuple[sqlite3.Connection, sqlite3.Cursor]:
    """Open a connection to the SQLite database and return (conn, cursor)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    return conn, cursor


def disconnect_db(conn: sqlite3.Connection) -> None:
    """Commit any pending changes and close the connection."""
    conn.commit()
    conn.close()


# -------------------------------
# Core execution logic
# -------------------------------

def run_subquery(cursor: sqlite3.Cursor, subquery: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Execute a single subquery and return a list of dicts.

    subquery structure (example):
    {
        "index": 0,
        "intent": "instructor_lookup",
        "sql_string": "SELECT course_number, section, instructor FROM public_classes WHERE LOWER(course_number) LIKE ? ORDER BY course_number ASC, section ASC",
        "sql_params": ["%ma 226%"],
        "query_params": {...}
    }
    """
    sql_string = subquery["sql_string"]
    sql_params = subquery.get("sql_params", [])

    cursor.execute(sql_string, sql_params)

    # Get column names from the cursor
    column_names = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    # Convert each row to a dict {column_name: value}
    results = [
        {col: value for col, value in zip(column_names, row)}
        for row in rows
    ]

    return results


def handle_request(payload: Dict[str, Any]) -> List[List[Dict[str, Any]]]:
    """
    Handle the full JSON payload with multiple subqueries.

    Input (from them):
    {
        "subqueries": [ {...}, {...}, ... ]
    }

    Output (to them):
    [
        [ {row1}, {row2}, ... ],   # results for subquery 0
        [ {row1}, {row2}, ... ],   # results for subquery 1
        ...
    ]
    """
    conn, cursor = connect_db()
    try:
        all_results: List[List[Dict[str, Any]]] = []

        for subquery in payload.get("subqueries", []):
            results_for_subquery = run_subquery(cursor, subquery)
            all_results.append(results_for_subquery)

        return all_results
    finally:
        disconnect_db(conn)


# -------------------------------
# Example CLI usage
# -------------------------------
# You can run this script and pipe JSON in via stdin:
#
#   echo '{"subqueries":[... ]}' | python script.py
#
# And it will print JSON output to stdout.
# -------------------------------

if __name__ == "__main__":
    # Read JSON from stdin (what your friend sends you)
    payload = json.load(sys.stdin)

    # Run the queries
    response = handle_request(payload)

    # Print JSON to stdout (what you send back)
    json.dump(response, sys.stdout, indent=4)
    print()  # newline at the end



