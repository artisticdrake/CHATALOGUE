# db_layer.py
# ============================================================
# Fresh DB layer that:
# - consumes semantic parser output
# - looks at intents + requested_attributes
# - queries /mnt/data/courses_metcs.sqlite (public_classes)
# - returns structured results per subquery
# ============================================================

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

import re
import sqlite3
import logging

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
#  CONFIG
# ------------------------------------------------------------

DB_PATH = "courses_metcs.sqlite"

# Semantic "requested_attributes" → DB columns
COURSE_ATTR_TO_COLS: Dict[str, List[str]] = {
    "location":     ["location"],
    "instructor":   ["instructor"],
    "time":         ["days", "times"],
    "schedule":     ["days", "times", "location"],
    "course_name":  ["course_name"],
    "course_number": ["course_number"],
    # Fallback: everything useful
    "all": ["course_number", "course_name", "section",
            "instructor", "location", "days", "times"],
}

# Map semantic parser weekday format to database format
# Parser outputs: Mon, Tue, Wed, Thu, Fri, Sat, Sun
# Database uses: M, T, W, R, F, Sa, Su (R = Thursday)
WEEKDAY_TO_DB_FORMAT: Dict[str, str] = {
    "MON": "M",
    "MONDAY": "M",
    "TUE": "T",
    "TUESDAY": "T",
    "WED": "W",
    "WEDNESDAY": "W",
    "THU": "R",  # Database uses R for Thursday
    "THUR": "R",
    "THURS": "R",
    "THURSDAY": "R",
    "FRI": "F",
    "FRIDAY": "F",
    "SAT": "SA",  # Assuming Saturday uses SA
    "SATURDAY": "SA",
    "SUN": "SU",  # Assuming Sunday uses SU
    "SUNDAY": "SU",
}

# Course-related intents that should hit public_classes
COURSE_INTENTS = {
    "course_info",
    "instructor_lookup",
    "course_location",
    "course_time",
    "schedule_query",  # Added to handle "when does X meet" queries
    "event_query",     # Handle "when/where" combined queries
    "time_query",      # Alternative time intent name
}


# ------------------------------------------------------------
#  LOW-LEVEL DB HELPERS (FRESH)
# ------------------------------------------------------------

def _get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """
    Open a new sqlite connection.
    Caller is responsible for closing (we do that in this module).
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _normalize_course_code(raw: str) -> str:
    """
    Turn 'cs 575', 'CS-575', 'CS575' → 'cs 575' (loosely normalized).
    We'll use LIKE '%cs 575%' on course_number anyway.
    """
    if not raw:
        return ""
    raw = raw.strip()
    # unify spaces/hyphens a bit
    raw = raw.replace("-", " ")
    # collapse multiple spaces
    parts = raw.split()
    return " ".join(parts).lower()


def _columns_for_requested_attributes(attrs: List[str]) -> List[str]:
    """
    Map semantic requested_attributes to actual DB columns.
    Always include course_number + section + instructor as identification.
    """
    if not attrs:
        attrs = ["all"]

    # ALWAYS include these base columns
    cols: List[str] = ["course_number", "section", "instructor"]  # Added instructor
    
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

def _query_public_classes(
    *,
    course_code: Optional[str],
    instructor_name: Optional[str],
    weekdays: Optional[List[str]],
    requested_attributes: List[str],
) -> List[Dict[str, Any]]:
    """
    Core query function for the public_classes table.
    
    course_code can now include section, e.g.:
      - "CS 575" (matches all sections)
      - "CS 575 A1" (matches only section A1)
      - "MA 226 B3" (matches only section B3)

    Returns: list of row dicts.
    """
    select_cols = _columns_for_requested_attributes(requested_attributes)

    where_clauses: List[str] = []
    params: List[Any] = []

    # Course code → may include section
    section_filter = None
    if course_code:
        # Check if course_code includes a section (e.g. "MA 226 B3")
        parts = course_code.strip().split()
        
        # Pattern: last part is section if it matches A1, B3, C10 format
        if len(parts) >= 2 and re.match(r"^[A-Z]\d{1,2}$", parts[-1]):
            section_filter = parts[-1]
            course_code_without_section = " ".join(parts[:-1])
            norm = _normalize_course_code(course_code_without_section)
        else:
            norm = _normalize_course_code(course_code)
        
        # Fuzzy match on course_number
        where_clauses.append("LOWER(course_number) LIKE ?")
        params.append(f"%{norm}%")
        
        # Exact match on section if provided
        if section_filter:
            where_clauses.append("section = ?")
            params.append(section_filter)

    # Instructor name → fuzzy match on instructor
    if instructor_name:
        where_clauses.append("LOWER(instructor) LIKE ?")
        params.append(f"%{instructor_name.strip().lower()}%")

    # Weekdays → Use AND logic to match classes that meet on ALL requested days
    if weekdays:
        # Convert semantic parser format (Mon, Tue, Wed) to DB format (M, T, W, R, F)
        db_days = []
        for w in weekdays:
            w_upper = (w or "").strip().upper()
            if not w_upper:
                continue
            
            # Map to database format
            db_day = WEEKDAY_TO_DB_FORMAT.get(w_upper, w_upper)
            db_days.append(db_day)
        
        # Add each day as a separate WHERE condition (AND logic)
        # This ensures days column contains ALL requested days
        for db_day in db_days:
            where_clauses.append("UPPER(days) LIKE ?")
            params.append(f"%{db_day}%")

    base_sql = "SELECT " + ", ".join(select_cols) + " FROM public_classes"
    if where_clauses:
        base_sql += " WHERE " + " AND ".join(where_clauses)
    base_sql += " ORDER BY course_number ASC, section ASC"

    logger.debug("DB QUERY: %s | params=%s", base_sql, params)

    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(base_sql, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ------------------------------------------------------------
#  SEMANTIC → DB LAYER
# ------------------------------------------------------------

def _resolve_subqueries(semantic: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Normalize semantic into a list of subquery dicts.
    If is_multi_query is False or subqueries is empty, we create one
    synthetic subquery from the root fields.
    """
    is_multi = bool(semantic.get("is_multi_query"))
    subqs = semantic.get("subqueries") or []

    if not is_multi or not subqs:
        # Single synthetic subquery
        return [{
            "intent": semantic.get("primary_intent"),
            "course_codes": semantic.get("course_codes") or [],
            "instructor_names": semantic.get("instructor_names") or [],
            "requested_attributes": semantic.get("requested_attributes") or [],
            "weekdays": semantic.get("weekdays") or [],
            "text": semantic.get("raw_text")
                    or semantic.get("normalized_text")
                    or "",
        }]

    return subqs


def _course_code_for_subquery(
    subq: Dict[str, Any],
    root: Dict[str, Any],
) -> Optional[str]:
    """
    Decide which course_code to use for this subquery.
    Priority:
      - first from subquery.course_codes
      - else first from root.course_codes
      - else None
    """
    sub_codes = subq.get("course_codes") or []
    if sub_codes:
        return sub_codes[0]

    root_codes = root.get("course_codes") or []
    if root_codes:
        return root_codes[0]

    return None


def _instructor_for_subquery(
    subq: Dict[str, Any],
    root: Dict[str, Any],
) -> Optional[str]:
    """
    Decide which instructor_name to use for this subquery.
    Similar priority as course code.
    """
    sub_instr = subq.get("instructor_names") or []
    if sub_instr:
        return sub_instr[0]

    root_instr = root.get("instructor_names") or []
    if root_instr:
        return root_instr[0]

    return None


def _weekdays_for_subquery(
    subq: Dict[str, Any],
    root: Dict[str, Any],
) -> List[str]:
    """
    Merge weekday info from subquery/root. You can customize this.
    """
    sub_days = subq.get("weekdays") or []
    if sub_days:
        return sub_days
    return root.get("weekdays") or []


# Around line 220-280 in _resolve_subqueries and run_semantic_db_layer

def run_semantic_db_layer(semantic: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle multiple course codes by creating separate subqueries for each.
    Override chitchat intent if entities are detected.
    """
    subqueries = _resolve_subqueries(semantic)
    results: List[Dict[str, Any]] = []

    for idx, subq in enumerate(subqueries):
        intent_raw = subq.get("intent") or semantic.get("primary_intent") or ""
        intent = str(intent_raw).lower()

        requested_attrs = subq.get("requested_attributes") or semantic.get("requested_attributes") or []
        instructor_name = _instructor_for_subquery(subq, semantic)
        weekdays = _weekdays_for_subquery(subq, semantic)
        
        # Handle multiple course codes
        course_codes = subq.get("course_codes") or semantic.get("course_codes") or []
        
        if not course_codes:
            course_codes = [None]
        
        # Query each course separately
        for course_code in course_codes:
            # OVERRIDE CHITCHAT: If entities detected, force DB query
            should_query = False
            
            if intent in COURSE_INTENTS or intent == "instructor_lookup":
                should_query = True
            elif intent in ["chitchat", "unknown"]:
                # Force query if we have entities
                if instructor_name or course_code or weekdays:
                    should_query = True
            
            if should_query:
                rows = _query_public_classes(
                    course_code=course_code,
                    instructor_name=instructor_name,
                    weekdays=weekdays,
                    requested_attributes=requested_attrs,
                )
            else:
                rows = []

            results.append({
                "index": len(results),
                "intent": intent,
                "subquery_text": subq.get("text", ""),
                "requested_attributes": requested_attrs,
                "course_code_used": course_code,
                "instructor_used": instructor_name,
                "weekdays_used": weekdays,
                "rows": rows,
            })

    return {"subresults": results}