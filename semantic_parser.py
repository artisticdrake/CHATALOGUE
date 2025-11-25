# semantic_parser.py
# ============================================================
# Layer 2: Semantic parser with multi-query handling.
#
# - Reuses the trained ML intent classifier (IntentClassifier)
# - Splits user input into clauses (multi-intent detection)
# - Classifies each clause with ML
# - Extracts coarse slots: course codes, instructor names, weekdays
# - Builds a structured "semantic parse" dict consumable by planner/DB
# ============================================================

import re
from typing import List, Dict, Any, Optional, Tuple

from intent_classifier import get_intent_classifier


# ------------------------------------------------------------
# Utility: basic normalization & tokenization
# ------------------------------------------------------------

WH_WORDS = ("who", "what", "when", "where", "which", "how")


def normalize_text(text: str) -> str:
    return (text or "").strip()


# ------------------------------------------------------------
# Clause splitting for multi-intent detection
# ------------------------------------------------------------

def _split_on_question_mark(text: str) -> List[str]:
    """
    First pass: split on '?' into rough question segments.
    """
    parts = [p.strip() for p in text.split("?")]
    return [p for p in parts if p]


def _split_on_and_with_wh(clause: str) -> List[str]:
    """
    Second pass: if clause contains 'and' + WH-word later, split there.

    E.g.:
      "Who teaches Digging Deep and when does it meet"
      -> ["Who teaches Digging Deep", "when does it meet"]
    """
    lower = clause.lower()
    # Find all " and " occurrences
    idx = lower.find(" and ")
    if idx == -1:
        return [clause]

    # Consider only the first " and " that is followed by a WH-word
    before = clause[:idx].strip()
    after = clause[idx + 5 :].strip()  # skip " and "

    if not after:
        return [clause]

    # Check if the second part starts with (or contains) a question word
    if any(word in after.lower().split()[:3] for word in WH_WORDS):
        return [before, after]

    # No WH-word after 'and' => treat as single clause
    return [clause]


def split_into_clauses(user_input: str) -> List[str]:
    """
    Split user input into candidate clauses for multi-intent handling.

    We first split on '?', then split each piece on "and" when followed by a WH-word.
    """
    user_input = normalize_text(user_input)
    if not user_input:
        return []

    # pass 1
    segments = _split_on_question_mark(user_input)

    clauses: List[str] = []
    for seg in segments:
        subparts = _split_on_and_with_wh(seg)
        for s in subparts:
            s = s.strip(", ").strip()
            if s:
                clauses.append(s)

    # De-duplicate consecutive identical clauses
    deduped: List[str] = []
    for c in clauses:
        if not deduped or deduped[-1].lower() != c.lower():
            deduped.append(c)
    return deduped


# ------------------------------------------------------------
# Slot extraction helpers (very simple versions; you can refine)
# ------------------------------------------------------------


WEEKDAY_MAP = {
    "monday": "Mon",
    "mon": "Mon",
    "tuesday": "Tue",
    "tue": "Tue",
    "tues": "Tue",
    "wednesday": "Wed",
    "wed": "Wed",
    "thursday": "Thu",
    "thu": "Thu",
    "thur": "Thu",
    "thurs": "Thu",
    "friday": "Fri",
    "fri": "Fri",
    "saturday": "Sat",
    "sat": "Sat",
    "sunday": "Sun",
    "sun": "Sun",
}


SCHOOL_PREFIXES = {
    "MET", "CAS", "ENG", "QST", "GRS", "SAR", "SHA",
    "CFA", "COM", "SED", "SMG", "STH"
}

# Fix 1: semantic_parser.py - Better multi-course extraction
# Around line 130-217 in extract_course_codes function

def extract_course_codes(text: str) -> List[str]:
    """Extract ALL course codes from text, including METCS575 format"""
    tokens = re.findall(r"[A-Za-z0-9]+", text)
    if not tokens:
        return []

    up = [tok.upper() for tok in tokens]
    found: List[str] = []

    # 1) SCHOOL + DEPT + NUM + SECTION
    i = 0
    while i < len(up) - 3:
        t0, t1, t2, t3 = up[i], up[i + 1], up[i + 2], up[i + 3]
        if (
            t0 in SCHOOL_PREFIXES
            and t1.isalpha() and 2 <= len(t1) <= 4
            and t2.isdigit() and 3 <= len(t2) <= 4
            and re.match(r"^[A-Z]\d{1,2}$", t3)
        ):
            code = f"{t0} {t1} {t2} {t3}"
            found.append(code)
            i += 4
            continue
        i += 1

    # 2) SCHOOL + DEPT + NUM
    i = 0
    while i < len(up) - 2:
        t0, t1, t2 = up[i], up[i + 1], up[i + 2]
        if (
            t0 in SCHOOL_PREFIXES
            and t1.isalpha() and 2 <= len(t1) <= 4
            and t2.isdigit() and 3 <= len(t2) <= 4
        ):
            code = f"{t0} {t1} {t2}"
            if not any(c.startswith(code + " ") for c in found):
                found.append(code)
                i += 3
                continue
        i += 1

    # 3) DEPT + NUM + SECTION
    i = 0
    while i < len(up) - 2:
        t0, t1, t2 = up[i], up[i + 1], up[i + 2]
        if (
            t0.isalpha() and 2 <= len(t0) <= 4
            and t1.isdigit() and 3 <= len(t1) <= 4
            and re.match(r"^[A-Z]\d{1,2}$", t2)
        ):
            code = f"{t0} {t1} {t2}"
            if code not in found:
                found.append(code)
                i += 3
                continue
        i += 1

    # 4) DEPT + NUM
    i = 0
    while i < len(up) - 1:
        t0, t1 = up[i], up[i + 1]
        if (
            t0.isalpha() and 2 <= len(t0) <= 4
            and t1.isdigit() and 3 <= len(t1) <= 4
        ):
            code = f"{t0} {t1}"
            if not any(c.startswith(code + " ") or c.endswith(" " + code) for c in found):
                found.append(code)
                i += 2
                continue
        i += 1

    # 5) GLUED PATTERNS - EXPANDED
    for tok in up:
        # Pattern: METCS575 (SCHOOL+DEPT+NUM)
        m = re.match(r"^([A-Z]{2,4})([A-Z]{2,4})(\d{3,4})$", tok)
        if m:
            school, dept, num = m.group(1), m.group(2), m.group(3)
            if school in SCHOOL_PREFIXES:
                code = f"{school} {dept} {num}"
                if not any(c.startswith(code + " ") or c.endswith(" " + code) for c in found):
                    found.append(code)
                continue
        
        # Pattern: CS575 (DEPT+NUM)
        m = re.match(r"^([A-Z]{2,4})(\d{3,4})$", tok)
        if m:
            dept, num = m.group(1), m.group(2)
            code = f"{dept} {num}"
            if not any(c.startswith(code + " ") or c.endswith(" " + code) for c in found):
                found.append(code)

    return found

def extract_weekdays(text: str) -> List[str]:
    """
    Extract weekday references from text.
    Handles both full names (Monday, Tuesday) and abbreviations (Mon, Tue, MWF, TR).
    """
    text_lower = (text or "").strip().lower()
    found: List[str] = []

    # Common day patterns
    DAYS_MAP = {
        "monday": "Mon", "mon": "Mon", "m": "Mon",
        "tuesday": "Tue", "tue": "Tue", "t": "Tue",
        "wednesday": "Wed", "wed": "Wed", "w": "Wed",
        "thursday": "Thu", "thu": "Thu", "thur": "Thu", "thurs": "Thu", "r": "Thu",
        "friday": "Fri", "fri": "Fri", "f": "Fri",
        "saturday": "Sat", "sat": "Sat",
        "sunday": "Sun", "sun": "Sun",
    }

    # SPECIAL PATTERNS FIRST (MWF, TR, MW, etc.)
    # Check for common abbreviated patterns as whole tokens
    special_patterns = {
        "mwf": ["Mon", "Wed", "Fri"],
        "tr": ["Tue", "Thu"],
        "mw": ["Mon", "Wed"],
        "tf": ["Tue", "Fri"],
        "wf": ["Wed", "Fri"],
    }
    
    # Tokenize and check for special patterns
    tokens = text_lower.split()
    for token in tokens:
        token_clean = token.strip(".,;:!?")
        if token_clean in special_patterns:
            found.extend(special_patterns[token_clean])
            return found  # Return immediately - user specified exact pattern
    
    # If no special pattern found, look for individual day names
    for pattern, day in DAYS_MAP.items():
        # Use word boundaries for full names
        if len(pattern) > 2:  # Full names like "monday", "tuesday"
            if re.search(r'\b' + pattern + r'\b', text_lower):
                if day not in found:
                    found.append(day)
        else:  # Single letter abbreviations - be more careful
            # Only match if it's a standalone word
            if re.search(r'\b' + pattern + r'\b', text_lower):
                if day not in found:
                    found.append(day)
    
    # Check for "weekend"
    if "weekend" in text_lower:
        if "Sat" not in found:
            found.append("Sat")
        if "Sun" not in found:
            found.append("Sun")

    return found

# Fix 3: semantic_parser.py - Better "section" keyword detection
# Add after extract_weekdays function around line 240

def extract_section_from_text(text: str) -> Optional[str]:
    """Extract section identifier like 'section B3' or 'section A1'"""
    text = text.lower()
    
    # Pattern: "section B3" or "section A1"
    match = re.search(r'\bsection\s+([a-z]\d{1,2})\b', text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    
    return None


import re
from typing import List

# Around line 210-284, update extract_instructor_names

# Around line 213, update extract_instructor_names

def extract_instructor_names(text: str) -> List[str]:
    """Extract instructor names, handling possessives and "about [name]" pattern."""
    t = (text or "").strip().lower()
    
    # Remove possessive 's
    t = t.replace("'s", " ")
    t = t.replace("'s", " ")
    
    names: List[str] = []

    STOP = {
        "who","what","when","where","which","why","how",
        "does","did","will","is","are","for","my","the","this","that",
        "prof","professor","dr","ta","instructor",
        "week","days","later","earlier","next","last","prior","before","after","weekdays",
        "weekend","today","tomorrow","tonight","meeting","meet","time","schedule","room","building","location",
        "held","description","syllabus","topics","info","information","assignment","assignments","homework","project","projects","due","exam","exams","final","midterm","quiz","quizzes","test","tests",
        "teach","teaches","teaching","taught","class","classes","course","courses","about","section","sections"
    }

    def is_valid_name(tok: str) -> bool:
        return (
            tok not in STOP
            and tok.isalpha()
            and len(tok) >= 3
        )

    # 1) "about [name]" pattern - NEW
    about_pat = r"\babout\s+([a-z]+)\b"
    for m in re.finditer(about_pat, t):
        token = m.group(1)
        if is_valid_name(token):
            cap = token.capitalize()
            if cap not in names:
                names.append(cap)

    # 2) title-based patterns
    title_pat = r"\b(?:professor|prof|dr|ta|instructor)\.?\s+([a-z]+)\b"
    for m in re.finditer(title_pat, t):
        token = m.group(1)
        if is_valid_name(token):
            cap = token.capitalize()
            if cap not in names:
                names.append(cap)

    # 3) verb-based
    teach_pat = r"\b(?:does|did|will)\s+([a-z]+)\s+teach(?:es|ing)?\b"
    for m in re.finditer(teach_pat, t):
        token = m.group(1)
        if is_valid_name(token):
            cap = token.capitalize()
            if cap not in names:
                names.append(cap)

    # 4) "classes does [name] teach"
    classes_pat = r"\bclasses\s+does\s+([a-z]+)\s+teach\b"
    for m in re.finditer(classes_pat, t):
        token = m.group(1)
        if is_valid_name(token):
            cap = token.capitalize()
            if cap not in names:
                names.append(cap)
    
    # 5) "taught by [name]"
    taught_by_pat = r"\btaught\s+by\s+([a-z]+)\b"
    for m in re.finditer(taught_by_pat, t):
        token = m.group(1)
        if is_valid_name(token):
            cap = token.capitalize()
            if cap not in names:
                names.append(cap)
    
    # 6) "[name] class/classes/course/section"
    name_class_pat = r"\b([a-z]+)\s+(?:class|classes|course|courses|section|sections)\b"
    for m in re.finditer(name_class_pat, t):
        token = m.group(1)
        if is_valid_name(token):
            cap = token.capitalize()
            if cap not in names:
                names.append(cap)

    return names





def detect_requested_attributes(text: str) -> List[str]:
    """
    Coarse attribute detection based on tokens + a few phrases.
    Avoids substring leaks like 'latest' → 'test' → exam.
    """
    lower = (text or "").lower()
    tokens = re.findall(r"[a-z]+", lower)
    token_set = set(tokens)

    attrs: List[str] = []

    # Instructor-related
    if (
        "who" in token_set
        or "teaches" in token_set
        or "teach" in token_set
        or "professor" in token_set
        or "prof" in token_set
        or "instructor" in token_set
        or "ta" in token_set
    ):
        attrs.append("instructor")

    # Time / schedule
    if (
        "when" in token_set
        or "time" in token_set
        or "meet" in token_set
        or "meeting" in token_set
        or "schedule" in token_set
        or "today" in token_set
        or "tomorrow" in token_set
        or "tonight" in token_set
        or "weekend" in token_set
    ):
        attrs.append("time")

    # Location (still okay to use substrings for multi-word phrases)
    if (
        "where" in token_set
        or "room" in token_set
        or "building" in token_set
        or "location" in token_set
        or "held" in token_set
    ):
        attrs.append("location")

    # Generic course info
    if (
        "description" in token_set
        or "about" in token_set
        or "syllabus" in token_set
        or "topics" in token_set
        or "info" in token_set
        or "information" in token_set
        or "what is" in lower  # phrase
    ):
        attrs.append("info")

    # Assignments
    if (
        "assignment" in token_set
        or "assignments" in token_set
        or "homework" in token_set
        or "project" in token_set
        or "projects" in token_set
        or "due" in token_set
    ):
        attrs.append("assignment")

    # Exams
    EXAM_TOKENS = {"exam", "exams", "final", "midterm", "quiz", "quizzes", "test", "tests"}
    if token_set & EXAM_TOKENS:
        attrs.append("exam")

    # De-dup in order
    return list(dict.fromkeys(attrs))




# ------------------------------------------------------------
# ML intent classification wrapper (reused for full + clauses)
# ------------------------------------------------------------

_classifier = None


def get_classifier():
    global _classifier
    if _classifier is None:
        _classifier = get_intent_classifier()
    return _classifier


def classify_intent_ml(text: str) -> Dict[str, Any]:
    clf = get_classifier()
    return clf.classify_intent(text, top_k=3)


# ------------------------------------------------------------
# Main semantic parse entrypoint
# ------------------------------------------------------------

# Fix 4: semantic_parser.py - Use section extraction in build_semantic_parse
# Around line 430-500, modify to:

def build_semantic_parse(user_input: str) -> Dict[str, Any]:
    raw = user_input or ""
    norm = normalize_text(raw)

    full_result = classify_intent_ml(norm)
    primary_intent = full_result["primary_intent"]
    primary_conf = full_result["confidence"]

    global_course_codes = extract_course_codes(raw)
    global_instr_names = extract_instructor_names(raw)
    global_weekdays = extract_weekdays(raw)
    global_attrs = detect_requested_attributes(raw)
    
    # NEW: Extract section if mentioned as "section B3"
    section_from_keyword = extract_section_from_text(raw)
    if section_from_keyword and global_course_codes:
        # Append section to first course code if it doesn't have one
        first_code = global_course_codes[0]
        if not re.search(r'[A-Z]\d{1,2}$', first_code):
            global_course_codes[0] = f"{first_code} {section_from_keyword}"

    clauses = split_into_clauses(raw)

    subqueries: List[Dict[str, Any]] = []
    clause_intents: List[str] = []

    if not clauses:
        clauses = [raw]

    for clause in clauses:
        c_norm = normalize_text(clause)
        if not c_norm:
            continue

        c_result = classify_intent_ml(c_norm)
        c_intent = c_result["primary_intent"]
        c_conf = c_result["confidence"]

        clause_intents.append(c_intent)

        c_codes = extract_course_codes(clause)
        c_instr = extract_instructor_names(clause)
        c_days = extract_weekdays(clause)
        c_attrs = detect_requested_attributes(clause)
        
        # NEW: Check for section keyword in this clause too
        c_section = extract_section_from_text(clause)
        if c_section and c_codes:
            first_code = c_codes[0]
            if not re.search(r'[A-Z]\d{1,2}$', first_code):
                c_codes[0] = f"{first_code} {c_section}"

        subqueries.append(
            {
                "intent": c_intent,
                "confidence": c_conf,
                "text": clause,
                "course_codes": c_codes,
                "instructor_names": c_instr,
                "weekdays": c_days,
                "requested_attributes": c_attrs,
                "multi_course": len(c_codes) > 1,
            }
        )

    is_multi_query = False
    if len(subqueries) > 1 and len(set(clause_intents)) > 1:
        is_multi_query = True
    
    # NEW: Resolve pronoun references in multi-query scenarios
    if is_multi_query or len(subqueries) > 1:
        subqueries = _resolve_pronoun_references(
            subqueries,
            {
                "course_codes": global_course_codes,
                "instructor_names": global_instr_names,
                "weekdays": global_weekdays,
            }
        )
    
    result: Dict[str, Any] = {
        "primary_intent": primary_intent,
        "primary_confidence": primary_conf,
        "is_multi_query": is_multi_query,
        "raw_text": raw,
        "normalized_text": norm.lower(),
        "course_codes": global_course_codes,
        "instructor_names": global_instr_names,
        "weekdays": global_weekdays,
        "requested_attributes": global_attrs,
        "subqueries": subqueries,  # Now with resolved pronouns
    }

    return result

def _resolve_pronoun_references(subqueries: List[Dict[str, Any]], global_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Resolve pronouns (it, them, etc.) in multi-query scenarios.
    If a subquery is chitchat/low-confidence with no entities, inherit from previous subqueries.
    """
    resolved = []
    
    # Collect context from non-chitchat subqueries
    context_courses = []
    context_instructors = []
    context_weekdays = []
    
    for i, subq in enumerate(subqueries):
        intent = (subq.get("intent") or "").lower()
        confidence = subq.get("confidence", 0.0)
        
        # If chitchat or low confidence AND missing entities AND has requested_attributes
        is_pronoun_query = (
            (intent == "chitchat" or confidence < 0.5) and
            not subq.get("course_codes") and
            not subq.get("instructor_names") and
            subq.get("requested_attributes")
        )
        
        if is_pronoun_query:
            # Inherit context from previous subqueries or global
            inherited = subq.copy()
            
            # Inherit course codes
            if context_courses:
                inherited["course_codes"] = context_courses.copy()
            elif global_data.get("course_codes"):
                inherited["course_codes"] = global_data["course_codes"].copy()
            
            # Inherit instructors
            if context_instructors:
                inherited["instructor_names"] = context_instructors.copy()
            elif global_data.get("instructor_names"):
                inherited["instructor_names"] = global_data["instructor_names"].copy()
            
            # Inherit weekdays
            if context_weekdays:
                inherited["weekdays"] = context_weekdays.copy()
            elif global_data.get("weekdays"):
                inherited["weekdays"] = global_data["weekdays"].copy()
            
            # Change intent based on what was inherited and what's requested
            attrs = inherited.get("requested_attributes", [])
            if inherited.get("course_codes"):
                if "instructor" in [a.lower() for a in attrs]:
                    inherited["intent"] = "instructor_lookup"
                elif "location" in [a.lower() for a in attrs]:
                    inherited["intent"] = "course_location"
                elif "time" in [a.lower() for a in attrs] or "schedule" in [a.lower() for a in attrs]:
                    inherited["intent"] = "schedule_query"
                else:
                    inherited["intent"] = "course_info"
            
            resolved.append(inherited)
        else:
            # Not a pronoun query - keep as is and update context
            resolved.append(subq)
            
            # Update context for future pronoun resolution
            if subq.get("course_codes"):
                context_courses = subq["course_codes"]
            if subq.get("instructor_names"):
                context_instructors = subq["instructor_names"]
            if subq.get("weekdays"):
                context_weekdays = subq["weekdays"]
    
    return resolved

# ------------------------------------------------------------
# CLI test
# ------------------------------------------------------------
if __name__ == "__main__":
    print("Semantic parser test mode. Type a query (or 'quit').\n")
    while True:
        msg = input("You: ").strip()
        if msg.lower() in {"quit", "exit", "bye"}:
            break
        parsed = build_semantic_parse(msg)
        from pprint import pprint
        pprint(parsed)
        print("-" * 60)