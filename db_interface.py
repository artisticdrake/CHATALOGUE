# db_interface.py
# ============================================================
# DB Interface Layer - Generates SQL queries without executing them
# Sends query params to external DB service, receives results back
# ============================================================

from __future__ import annotations
from typing import Any, Dict, List, Optional
import re
import sys

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------

# Map semantic_parse attributes to DB columns
COURSE_ATTR_TO_COLS: Dict[str, List[str]] = {
    "location":     ["location"],
    "instructor":   ["instructor"],
    "time":         ["days", "times"],
    "schedule":     ["days", "times", "location"],
    "course_name":  ["course_name"],
    "course_number": ["course_number"],
    "all": ["course_number", "course_name", "section",
            "instructor", "location", "days", "times"],
}

# Weekday mapping
WEEKDAY_TO_DB_FORMAT: Dict[str, str] = {
    "MON": "M", "MONDAY": "M",
    "TUE": "T", "TUESDAY": "T",
    "WED": "W", "WEDNESDAY": "W",
    "THU": "R", "THUR": "R", "THURS": "R", "THURSDAY": "R",
    "FRI": "F", "FRIDAY": "F",
    "SAT": "SA", "SATURDAY": "SA",
    "SUN": "SU", "SUNDAY": "SU",
}

COURSE_INTENTS = {
    "course_info",
    "instructor_lookup",
    "course_location",
    "course_time",
    "schedule_query",
    "event_query",
    "time_query",
}


# ------------------------------------------------------------
# QUERY BUILDER (NO DB CONNECTION)
# ------------------------------------------------------------

def build_query_params(
    *,
    course_code: Optional[str],
    instructor_name: Optional[str],
    weekdays: Optional[List[str]],
    requested_attributes: List[str],
) -> Dict[str, Any]:
    """
    Build SQL query parameters without executing.
    
    Returns:
        {
            "select_columns": ["course_number", "section", ...],
            "where_conditions": [
                {"column": "course_number", "operator": "LIKE", "value": "%cs 575%"},
                {"column": "section", "operator": "=", "value": "A1"},
                ...
            ],
            "order_by": ["course_number ASC", "section ASC"]
        }
    """
    # Determine SELECT columns
    select_cols = _get_select_columns(requested_attributes)
    
    # Build WHERE conditions
    where_conditions = []
    
    # Course code (may include section)
    section_filter = None
    if course_code:
        parts = course_code.strip().split()
        
        # Check if last part is section (A1, B3, etc.)
        if len(parts) >= 2 and re.match(r"^[A-Z]\d{1,2}$", parts[-1]):
            section_filter = parts[-1]
            course_code_without_section = " ".join(parts[:-1])
            norm = _normalize_course_code(course_code_without_section)
        else:
            norm = _normalize_course_code(course_code)
        
        where_conditions.append({
            "column": "course_number",
            "operator": "LIKE",
            "value": f"%{norm}%",
            "case_insensitive": True
        })
        
        if section_filter:
            where_conditions.append({
                "column": "section",
                "operator": "=",
                "value": section_filter
            })
    
    # Instructor
    if instructor_name:
        where_conditions.append({
            "column": "instructor",
            "operator": "LIKE",
            "value": f"%{instructor_name.strip().lower()}%",
            "case_insensitive": True
        })
    
    # Weekdays (AND logic)
    if weekdays:
        db_days = []
        for w in weekdays:
            w_upper = (w or "").strip().upper()
            if not w_upper:
                continue
            db_day = WEEKDAY_TO_DB_FORMAT.get(w_upper, w_upper)
            db_days.append(db_day)
        
        for db_day in db_days:
            where_conditions.append({
                "column": "days",
                "operator": "LIKE",
                "value": f"%{db_day.lower()}%",
                "case_insensitive": True
            })
    
    return {
        "select_columns": select_cols,
        "where_conditions": where_conditions,
        "order_by": ["course_number ASC", "section ASC"]
    }


def build_sql_string(query_params: Dict[str, Any]) -> tuple[str, List[Any]]:
    """
    Convert query params to SQL string and parameter list.
    
    Returns:
        (sql_string, params_list)
        
    Example:
        ("SELECT course_number, section FROM public_classes WHERE LOWER(course_number) LIKE ? ORDER BY course_number ASC",
         ["%cs 575%"])
    """
    select_cols = query_params["select_columns"]
    where_conditions = query_params["where_conditions"]
    order_by = query_params.get("order_by", [])
    
    # Build SELECT
    sql = "SELECT " + ", ".join(select_cols) + " FROM public_classes"
    
    # Build WHERE
    params = []
    if where_conditions:
        where_clauses = []
        for cond in where_conditions:
            column = cond["column"]
            operator = cond["operator"]
            case_insensitive = cond.get("case_insensitive", False)
            
            if case_insensitive:
                where_clauses.append(f"REPLACE(LOWER({column}), ' ', '') {operator} ?")
            else:
                where_clauses.append(f"{column} {operator} ?")
            
            params.append(cond["value"])
        
        sql += " WHERE " + " AND ".join(where_clauses)
    
    # Build ORDER BY
    if order_by:
        sql += " ORDER BY " + ", ".join(order_by)
    
    return sql, params


# ------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------

def _get_select_columns(attrs: List[str]) -> List[str]:
    """Map semantic_parse attributes to DB columns."""
    if not attrs:
        attrs = ["all"]
    
    # Always include these base columns
    cols: List[str] = ["course_number", "course_name", "section",
            "instructor", "location", "days", "times"]
    
    for attr in attrs:
        key = (attr or "").lower()
        mapped = COURSE_ATTR_TO_COLS.get(key)
        if not mapped:
            mapped = COURSE_ATTR_TO_COLS["all"]
        for c in mapped:
            if c not in cols:
                cols.append(c)
    
    # Deduplicate
    seen = set()
    deduped: List[str] = []
    for c in cols:
        if c not in seen:
            deduped.append(c)
            seen.add(c)
    return deduped


def _normalize_course_code(raw: str) -> str:
    """Normalize course code for fuzzy matching."""
    if not raw:
        return ""
    raw = raw.strip()
    raw = raw.replace("-", " ")
    parts = raw.split()
    return " ".join(parts).lower()


# ------------------------------------------------------------
# MAIN INTERFACE FUNCTION
# ------------------------------------------------------------

def process_semantic_query(semantic_parse: Dict[str, Any], fuzzy_results: Optional[List[Dict]] = None) -> Dict[str, Any]:
    """
    Process semantic_parse parse into SQL query.
    Two-stage flow: fuzzy search first if needed, then build query.
    """
    
    # STAGE 1: Check if we need fuzzy search (MAIN or SUBQUERIES)
    if fuzzy_results is None:
        # Check main query
        if needs_fuzzy_search(semantic_parse):
            return build_fuzzy_search_request(semantic_parse)

        # NEW: Check EACH subquery
        subqueries = semantic_parse.get("subqueries", [])
        for idx, subq in enumerate(subqueries):
            # Check if this subquery needs fuzzy search
            has_codes = bool(subq.get("course_codes"))
            has_names = bool(subq.get("course_names"))
            intent = str(subq.get("intent", "")).lower()

            course_related = intent in {"course_info", "instructor_lookup", "course_location", "course_time", "schedule_query"}

            if not has_codes and has_names and course_related:
                # This subquery needs fuzzy search!
                course_name = subq["course_names"][0]
                return {
                    "query_type": "fuzzy_course_search",
                    "search_term": course_name,
                    "needs_fuzzy_search": True,
                    "subquery_index": idx,  # Track which subquery this is for
                    "fuzzy_search_request": {
                        "query_type": "fuzzy_course_search",
                        "search_term": course_name
                    }
                }

    # STAGE 2: If fuzzy results provided, inject them
    if fuzzy_results:
        course_codes = [result["course_number"] for result in fuzzy_results]

        # Inject into main semantic_parse
        if not semantic_parse.get("course_codes"):
            if semantic_parse.get("course_name_queries"):
                # Add to existing course codes (accumulate from multiple fuzzy searches)
                if "course_codes" not in semantic_parse:
                    semantic_parse["course_codes"] = []
                semantic_parse["course_codes"].extend(course_codes)
                print(f"   ✓ Injected into main query: {course_codes}", file=sys.stderr)

        # NEW: Inject into subqueries that need it
        subqueries = semantic_parse.get("subqueries", [])
        for subq in subqueries:
            if subq.get("course_names") and not subq.get("course_codes"):
                subq["course_codes"] = course_codes
                print(f"   ✓ Injected into subquery: {course_codes}", file=sys.stderr)
                break
       
    # Rest of the function remains EXACTLY THE SAME
    subqueries = _resolve_subqueries(semantic_parse)
    results = []
    
    for idx, subq in enumerate(subqueries):
        intent_raw = subq.get("intent") or semantic_parse.get("primary_intent") or ""
        intent = str(intent_raw).lower()
        
        requested_attrs = subq.get("requested_attributes") or semantic_parse.get("requested_attributes") or []
        weekdays = _weekdays_for_subquery(subq, semantic_parse)
        
        # FIXED: Handle multiple instructors (not just first one)
        instructor_names = subq.get("instructor_names") or semantic_parse.get("instructor_names") or []
        if not instructor_names:
            instructor_names = [None]
        
        # Handle multiple course codes
        course_codes = subq.get("course_codes") or semantic_parse.get("course_codes") or []
        if not course_codes:
            course_codes = [None]
        
        # FIXED: Generate query for EACH combination of course and instructor
        for course_code in course_codes:
            for instructor_name in instructor_names:
                # Override chitchat if entities present
                should_query = False
                
                if intent in COURSE_INTENTS or intent == "instructor_lookup":
                    should_query = True
                elif intent in ["chitchat", "unknown"]:
                    if instructor_name or course_code or weekdays:
                        should_query = True
                
                if should_query:
                    # Build query params
                    query_params = build_query_params(
                        course_code=course_code,
                        instructor_name=instructor_name,
                        weekdays=weekdays,
                        requested_attributes=requested_attrs
                    )
                    
                    # Generate SQL string
                    sql_string, sql_params = build_sql_string(query_params)
                    
                    results.append({
                        "index": len(results),
                        "intent": intent,
                        "subquery_text": subq.get("text", ""),
                        "requested_attributes": requested_attrs,
                        "course_code_used": course_code,
                        "instructor_used": instructor_name,
                        "weekdays_used": weekdays,
                        "query_params": query_params,
                        "sql_string": sql_string,
                        "sql_params": sql_params
                    })
                else:
                    results.append({
                        "index": len(results),
                        "intent": intent,
                        "subquery_text": subq.get("text", ""),
                        "requested_attributes": requested_attrs,
                        "course_code_used": course_code,
                        "instructor_used": instructor_name,
                        "weekdays_used": weekdays,
                        "query_params": None,
                        "sql_string": None,
                        "sql_params": None
                    })
    
    return {"subqueries": results}


def inject_db_results(query_result: Dict[str, Any], db_rows: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Inject DB results back into query result structure.
    
    Args:
        query_result: Output from process_semantic_query()
        db_rows: List of row lists, one per subquery
                 [[{row1}, {row2}], [{row3}], ...]
    
    Returns:
        Updated query_result with "rows" field added to each subquery
    """
    subqueries = query_result.get("subqueries", [])
    
    for i, subq in enumerate(subqueries):
        if i < len(db_rows):
            subq["rows"] = db_rows[i]
        else:
            subq["rows"] = []
    
    return {"subresults": subqueries}


# ------------------------------------------------------------
# HELPER FUNCTIONS (from original db_layer.py)
# ------------------------------------------------------------

def _resolve_subqueries(semantic_parse: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize semantic_parse into list of subquery dicts."""
    is_multi = bool(semantic_parse.get("is_multi_query"))
    subqs = semantic_parse.get("subqueries") or []
    
    if not is_multi or not subqs:
        return [{
            "intent": semantic_parse.get("primary_intent"),
            "course_codes": semantic_parse.get("course_codes") or [],
            "instructor_names": semantic_parse.get("instructor_names") or [],
            "requested_attributes": semantic_parse.get("requested_attributes") or [],
            "weekdays": semantic_parse.get("weekdays") or [],
            "text": semantic_parse.get("raw_text") or semantic_parse.get("normalized_text") or "",
        }]
    
    return subqs

def needs_fuzzy_search(semantic_parse: Dict[str, Any]) -> bool:
    """Check if we need to do a fuzzy course name search first."""
    has_codes = bool(semantic_parse.get("course_codes"))
    has_name_queries = bool(semantic_parse.get("course_name_queries"))  # FIXED: plural
    intent_raw = semantic_parse.get("primary_intent", "")
    
    # Convert numpy string to regular string
    intent = str(intent_raw).lower() if intent_raw else ""
    
    course_related_intents = {
        "course_info", "instructor_lookup", "course_location",
        "course_time", "schedule_query"
    }
    
    result = (
        not has_codes and
        has_name_queries and  # FIXED: plural
        intent in course_related_intents
    )
    
    # DEBUG OUTPUT
    import sys
    print(f"🔍 needs_fuzzy_search() check:", file=sys.stderr)
    print(f"   has_codes: {has_codes}", file=sys.stderr)
    print(f"   has_name_queries: {has_name_queries}", file=sys.stderr)
    print(f"   intent: '{intent}' (in course intents: {intent in course_related_intents})", file=sys.stderr)
    print(f"   RESULT: {result}", file=sys.stderr)
    
    return result



def build_fuzzy_search_request(semantic_parse: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build fuzzy search request payload.
    FIXED: Returns info for first course name, but marks that more exist.
    """
    course_name_queries = semantic_parse.get("course_name_queries", [])
    
    if not course_name_queries:
        return {
            "query_type": "fuzzy_course_search",
            "search_term": ""
        }
    
    # Return request for FIRST course name, with metadata about others
    return {
        "query_type": "fuzzy_course_search",
        "search_term": course_name_queries[0],
        "needs_fuzzy_search": True,
        "remaining_course_names": course_name_queries[1:],  # Store the rest
        "current_course_index": 0,
        "fuzzy_search_request": {
            "query_type": "fuzzy_course_search",
            "search_term": course_name_queries[0]
        }
    }

def _instructor_for_subquery(subq: Dict[str, Any], root: Dict[str, Any]) -> Optional[str]:
    """Get instructor name for subquery."""
    sub_instr = subq.get("instructor_names") or []
    if sub_instr:
        return sub_instr[0]
    
    root_instr = root.get("instructor_names") or []
    if root_instr:
        return root_instr[0]
    
    return None


def _weekdays_for_subquery(subq: Dict[str, Any], root: Dict[str, Any]) -> List[str]:
    """Get weekdays for subquery."""
    sub_days = subq.get("weekdays") or []
    if sub_days:
        return sub_days
    return root.get("weekdays") or []


# ------------------------------------------------------------
# EXAMPLE USAGE
# ------------------------------------------------------------

if __name__ == "__main__":
    # Example semantic_parse parse
    semantic_parse = {
        "primary_intent": "instructor_lookup",
        "course_codes": ["MA 226"],
        "instructor_names": [],
        "weekdays": [],
        "requested_attributes": ["instructor"]
    }
    
    # Generate query params
    result = process_semantic_query(semantic_parse)
    
    print("="*80)
    print("QUERY TO SEND TO DB SERVICE:")
    print("="*80)
    for subq in result["subqueries"]:
        print(f"\nSubquery {subq['index']}:")
        print(f"  Intent: {subq['intent']}")
        print(f"  SQL: {subq['sql_string']}")
        print(f"  Params: {subq['sql_params']}")
    
    print("\n" + "="*80)
    print("EXPECTED FROM DB SERVICE:")
    print("="*80)
    print("List of row lists: [[{row1}, {row2}], [{row3}], ...]")
    
    # Simulate DB response
    db_response = [
        [
            {"course_number": "CAS MA 226", "section": "A1", "instructor": "Goh"},
            {"course_number": "CAS MA 226", "section": "A2", "instructor": "Goh"}
        ]
    ]
    
    # Inject results back
    final_result = inject_db_results(result, db_response)
    
    print("\n" + "="*80)
    print("FINAL RESULT WITH DB DATA:")
    print("="*80)
    print(final_result)