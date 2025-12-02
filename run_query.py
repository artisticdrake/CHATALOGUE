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
    
    sql_string = subquery["sql_string"]
    sql_params = subquery.get("sql_params", [])

    if sql_string is None:
        return []
    
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

def fuzzy_search_courses(cursor: sqlite3.Cursor, search_term: str) -> List[Dict[str, Any]]:
    """
    Fuzzy search for courses by name.
    Returns list of matching courses with their codes.
    """
    search_pattern = f"%{search_term.lower()}%"
    
    # DEBUG: Print what we're searching for
    print(f"DEBUG: Searching for pattern: {search_pattern}", file=sys.stderr)
    
    sql = """
        SELECT DISTINCT course_number, course_name 
        FROM public_classes 
        WHERE LOWER(course_name) LIKE ?
        ORDER BY course_number
    """
    
    # DEBUG: Print the SQL
    print(f"DEBUG: SQL = {sql}", file=sys.stderr)
    
    cursor.execute(sql, [search_pattern])
    
    # DEBUG: Check what we got
    column_names = [desc[0] for desc in cursor.description]
    print(f"DEBUG: Columns = {column_names}", file=sys.stderr)
    
    rows = cursor.fetchall()
    print(f"DEBUG: Row count = {len(rows)}", file=sys.stderr)
    print(f"DEBUG: Rows = {rows}", file=sys.stderr)
    
    return [
        {col: value for col, value in zip(column_names, row)}
        for row in rows
    ]

def handle_request(payload: Dict[str, Any]) -> Any:
    """
    Handle requests - either fuzzy search or regular subqueries.
    """
    conn, cursor = connect_db()
    try:
        # Check if this is a fuzzy search request
        if payload.get("query_type") == "fuzzy_course_search":
            search_term = payload.get("search_term", "")
            return fuzzy_search_courses(cursor, search_term)
        
        # Otherwise, handle normal subqueries
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