# semantic_parser.py - NER-ONLY VERSION
# ============================================================
# Layer 2: Semantic parser with NER extraction (98.8% F1 score)
#
# Strategy:
# 1. NER extraction (98.8% F1 score)
# 2. Validation to remove false positives
# 3. No regex fallback - trust the trained model
# ============================================================

import re
from typing import List, Dict, Any, Optional, Tuple
import sys
from intent_classifier import get_intent_classifier

# NEW: Import spaCy NER model
import spacy

# Load NER model once at module level (lazy loading)
_NER_MODEL = None

def get_ner_model():
    """Lazy load NER model."""
    global _NER_MODEL
    if _NER_MODEL is None:
        try:
            print("🔄 Loading NER model...", file=sys.stderr)
            _NER_MODEL = spacy.load("course_ner_model")
            print("✅ NER model loaded successfully", file=sys.stderr)
        except Exception as e:
            print(f"⚠️  NER model not found, NER model not available: {e}", file=sys.stderr)
            _NER_MODEL = None
    return _NER_MODEL


# Course-related intents that can trigger DB queries
COURSE_INTENTS = {
    "course_info",
    "instructor_lookup",
    "course_location",
    "course_time",
    "schedule_query",
    "event_query",
    "time_query",
}

# Intent override configuration
INTENT_OVERRIDE_CONFIG = {
    "keywords_to_intent": {
        "course_info": ["section", "sections"],
        "schedule_query": ["time", "when", "schedule", "meet", "meets", "meeting"],
        "course_location": ["where", "location", "room", "building", "place"],
        "instructor_lookup": ["who", "teach", "teaches", "instructor", "professor", "prof"],
    },
    "safe_intents": {"chitchat", "greeting"},
    "topic_change_keywords": {"instead", "actually", "wait", "no", "what about", "how about", "tell me about"},
    "confidence_threshold": 0.40,
}

# Validation blacklists
NON_ENTITY_WORDS = {
    'food', 'waiting', 'counting', 'start', 'after', 'march', 
    'before', 'during', 'the', 'and', 'or', 'but'
}

WH_WORDS = ("who", "what", "when", "where", "which", "how")

WEEKDAY_MAP = {
    "monday": "Mon", "mon": "Mon", "mondays": "Mon",
    "tuesday": "Tue", "tue": "Tue", "tues": "Tue", "tuesdays": "Tue",
    "wednesday": "Wed", "wed": "Wed", "wednesdays": "Wed",
    "thursday": "Thu", "thu": "Thu", "thur": "Thu", "thurs": "Thu", "thursdays": "Thu",
    "friday": "Fri", "fri": "Fri", "fridays": "Fri",
    "saturday": "Sat", "sat": "Sat", "saturdays": "Sat",
    "sunday": "Sun", "sun": "Sun", "sundays": "Sun",
}

SCHOOL_PREFIXES = {
    "MET", "CAS", "ENG", "QST", "GRS", "SAR", "SHA",
    "CFA", "COM", "SED", "SMG", "STH"
}

# COURSE_NAME_STOPWORDS removed - not needed with NER-only approach


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def normalize_text(text: str) -> str:
    return (text or "").strip()


def _split_on_question_mark(text: str) -> List[str]:
    """First pass: split on '?' into rough question segments."""
    parts = [p.strip() for p in text.split("?")]
    return [p for p in parts if p]


def _split_on_and_with_wh(clause: str) -> List[str]:
    """
    Second pass: if clause contains 'and' + WH-word later, split there.
    E.g.: "Who teaches Digging Deep and when does it meet"
    """
    lower = clause.lower()
    idx = lower.find(" and ")
    if idx == -1:
        return [clause]

    before = clause[:idx].strip()
    after = clause[idx + 5:].strip()

    if not after:
        return [clause]

    if any(word in after.lower().split()[:3] for word in WH_WORDS):
        return [before, after]

    return [clause]


def split_into_clauses(user_input: str) -> List[str]:
    """Split user input into candidate clauses for multi-intent handling."""
    user_input = normalize_text(user_input)
    if not user_input:
        return []

    segments = _split_on_question_mark(user_input)
    clauses: List[str] = []
    
    for seg in segments:
        subparts = _split_on_and_with_wh(seg)
        for s in subparts:
            s = s.strip(", ").strip()
            if s:
                clauses.append(s)

    # NEW: Split on "and + course name"
    clauses = _split_on_and_with_course_names(clauses)

    # Deduplicate consecutive identical clauses
    deduped: List[str] = []
    for c in clauses:
        if not deduped or deduped[-1].lower() != c.lower():
            deduped.append(c)
    return deduped

def _split_on_and_with_course_names(clauses: List[str]) -> List[str]:
    """
    Split clauses that contain multiple course names connected by 'and'.
    
    Example:
    "who teaches linear algebra and differential equations"
    → ["who teaches linear algebra", "who teaches differential equations"]
    """
    result = []
    
    for clause in clauses:
        # Quick check: does it have "and"?
        if ' and ' not in clause.lower():
            result.append(clause)
            continue
        
        # Extract course names using NER
        try:
            entities = extract_entities_ner(clause)
            course_names = entities.get('course_names', [])
            
            # If we have multiple course names, try to split
            if len(course_names) >= 2:
                # Find the base query (everything before first course name)
                lower_clause = clause.lower()
                first_course_lower = course_names[0].lower()
                
                # Find where first course appears
                pos = lower_clause.find(first_course_lower)
                if pos > 0:
                    base_query = clause[:pos].strip()
                    
                    # Create separate clause for each course
                    for course_name in course_names:
                        new_clause = f"{base_query} {course_name}"
                        result.append(new_clause)
                else:
                    # Couldn't find position, keep original
                    result.append(clause)
            else:
                # Only one or no course names, keep original
                result.append(clause)
                
        except Exception as e:
            # If NER fails, keep original clause
            print(f"   ⚠️  Error splitting course names: {e}", file=sys.stderr)
            result.append(clause)
    
    return result


# ============================================================
# NER EXTRACTION (Primary Method - 98.8% Accurate)
# ============================================================

def extract_entities_ner(text: str) -> Dict[str, List[str]]:
    """
    Extract entities using NER model (98.8% F1-score).
    Returns empty dict if model not available.
    """
    nlp = get_ner_model()
    
    # Empty result structure
    empty_result = {
        "instructors": [],
        "course_codes": [],
        "course_names": [],
        "weekdays": [],
        "times": [],
        "buildings": [],
        "sections": []
    }
    
    if nlp is None:
        return empty_result
    
    try:
        doc = nlp(text)
    except Exception as e:
        print(f"⚠️  NER extraction error: {e}", file=sys.stderr)
        return empty_result
    
    entities = {
        "instructors": [],
        "course_codes": [],
        "course_names": [],
        "weekdays": [],
        "times": [],
        "buildings": [],
        "sections": []
    }
    
    for ent in doc.ents:
        entity_text = ent.text.strip()
        
        if ent.label_ == "INSTRUCTOR":
            entities["instructors"].append(entity_text)
        elif ent.label_ == "COURSE_CODE":
            entities["course_codes"].append(entity_text)
        elif ent.label_ == "COURSE_NAME":
            entities["course_names"].append(entity_text)
        elif ent.label_ == "WEEKDAY":
            entities["weekdays"].append(entity_text)
        elif ent.label_ == "TIME":
            entities["times"].append(entity_text)
        elif ent.label_ == "BUILDING":
            entities["buildings"].append(entity_text)
        elif ent.label_ == "SECTION":
            entities["sections"].append(entity_text)
    
    return entities


# ============================================================
# (Regex functions removed - NER-only approach)
# ============================================================

def normalize_course_code(code: str) -> str:
    """Normalize course code for comparison (remove extra spaces)."""
    parts = code.upper().split()
    return " ".join(parts)


def validate_entities(entities: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Filter out obvious false positives."""
    
    # Common department codes that are NOT instructors
    DEPT_CODES = {'cs', 'ma', 'met', 'cas', 'eng', 'qst', 'grs', 'sar', 'sha', 'cfa', 'com', 'sed', 'smg', 'sth'}
    
    # Validate instructors
    valid_instructors = []
    for instructor in entities['instructors']:
        instructor_lower = instructor.lower()
        
        # Skip if it's a department code
        if instructor_lower in DEPT_CODES:
            print(f"   ❌ Filtered '{instructor}' (department code)", file=sys.stderr)
            continue
        
        # Skip if it's in our non-entity words
        if instructor_lower in NON_ENTITY_WORDS:
            print(f"   ❌ Filtered '{instructor}' (non-entity word)", file=sys.stderr)
            continue
        
        # Skip if too short
        if len(instructor) < 2:
            print(f"   ❌ Filtered '{instructor}' (too short)", file=sys.stderr)
            continue
        
        # Skip if it's a number
        if instructor.isdigit():
            print(f"   ❌ Filtered '{instructor}' (number)", file=sys.stderr)
            continue
        
        # Check if this instructor name appears in any course code
        # E.g., "cs" in "cs 575" or "CS 575"
        is_part_of_course_code = False
        for code in entities['course_codes']:
            code_parts = code.lower().split()
            if instructor_lower in code_parts:
                is_part_of_course_code = True
                print(f"   ❌ Filtered '{instructor}' (part of course code '{code}')", file=sys.stderr)
                break
        
        if is_part_of_course_code:
            continue
        
        # NEW: Check if instructor is part of any course name
        is_part_of_course_name = False
        for course_name in entities['course_names']:
            course_name_words = course_name.lower().split()
            if instructor_lower in course_name_words:
                is_part_of_course_name = True
                print(f"   ❌ Filtered '{instructor}' (part of course name '{course_name}')", file=sys.stderr)
                break
        
        if is_part_of_course_name:
            continue
        
        # If we made it here, it's a valid instructor
        print(f"   ✅ Kept '{instructor}' (valid instructor)", file=sys.stderr)
        valid_instructors.append(instructor)
    
    entities['instructors'] = valid_instructors
    
    # Validate buildings
    entities['buildings'] = [
        b for b in entities['buildings']
        if (b.lower() not in NON_ENTITY_WORDS and
            len(b) >= 2)
    ]
    
    # Validate weekdays
    entities['weekdays'] = [
        w for w in entities['weekdays']
        if w.lower() not in NON_ENTITY_WORDS
    ]
    
    # Validate course names
    entities['course_names'] = [
        cn for cn in entities['course_names']
        if (cn.lower() not in NON_ENTITY_WORDS and
            len(cn) >= 5 and  # Min length for course name
            not cn.isdigit())
    ]
    
    return entities


def extract_all_entities_ner_only(text: str) -> Dict[str, Any]:
    """
    NER-ONLY extraction (98.8% F1 score).
    No regex fallback - trust the trained model completely.
    """
    # Extract using NER
    ner_entities = extract_entities_ner(text)
    
    print(f"🔍 [NER] Extracted:", file=sys.stderr)
    print(f"   Instructors: {ner_entities['instructors']}", file=sys.stderr)
    print(f"   Course codes: {ner_entities['course_codes']}", file=sys.stderr)
    print(f"   Course names: {ner_entities['course_names']}", file=sys.stderr)
    print(f"   Weekdays: {ner_entities['weekdays']}", file=sys.stderr)
    
    # Validate to remove false positives
    validated_entities = validate_entities(ner_entities)
    
    print(f"🔍 [FINAL] After validation:", file=sys.stderr)
    print(f"   Instructors: {validated_entities['instructors']}", file=sys.stderr)
    print(f"   Course codes: {validated_entities['course_codes']}", file=sys.stderr)
    print(f"   Course names: {validated_entities['course_names']}", file=sys.stderr)
    
    return validated_entities

# Alias for backward compatibility
extract_all_entities_hybrid = extract_all_entities_ner_only

# ============================================================
# BACKWARD COMPATIBILITY WRAPPERS
# ============================================================

def extract_course_codes(text: str) -> List[str]:
    """Backward compatible: Use hybrid extraction."""
    entities = extract_all_entities_hybrid(text)
    return entities["course_codes"]


def extract_instructor_names(text: str) -> List[str]:
    """Backward compatible: Use hybrid extraction."""
    entities = extract_all_entities_hybrid(text)
    return entities["instructors"]


def extract_weekdays(text: str) -> List[str]:
    """Backward compatible: Use hybrid extraction."""
    entities = extract_all_entities_hybrid(text)
    return entities["weekdays"]


# ============================================================
# REST OF ORIGINAL CODE (Unchanged)
# ============================================================

def detect_requested_attributes(text: str) -> List[str]:
    """Detect what information user is asking about."""
    text_lower = text.lower()
    attrs: List[str] = []
    
    if any(w in text_lower for w in ["who", "instructor", "professor", "prof", "teach"]):
        attrs.append("instructor")
    if any(w in text_lower for w in ["where", "location", "room", "building"]):
        attrs.append("location")
    if any(w in text_lower for w in ["when", "time", "schedule", "meet"]):
        attrs.append("time")
    if any(w in text_lower for w in ["section", "sections"]):
        attrs.append("sections")
    
    return attrs if attrs else ["info"]


def extract_section_from_text(text: str) -> str:
    """Extract section like 'section B3' or 'sec A1'."""
    match = re.search(r'\b(?:section|sec)\s+([A-Z]\d{1,2})\b', text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return ""


def classify_intent_ml(text: str) -> Dict[str, Any]:
    """ML-based intent classification."""
    classifier = get_intent_classifier()
    if not classifier:
        return {"primary_intent": "chitchat", "confidence": 0.5, "all_intents": []}
    
    result = classifier.classify_intent(text, top_k=3)
    
    # Debug: Show what classifier returned
    print(f"🔍 Classifier returned: {type(result)} = {result}", file=sys.stderr)
    
    # Handle empty result
    if not result or len(result) == 0:
        return {"primary_intent": "chitchat", "confidence": 0.5, "all_intents": []}
    
    # Handle different return formats
    if isinstance(result, dict):
        # Format: {"primary_intent": "course_info", "confidence": 0.95, "top_k": [...]}
        primary = result.get("intent") or result.get("primary_intent", "chitchat")
        conf = result.get("confidence", 0.5)
        all_intents = result.get("top_k", [])
        
        # Convert numpy strings to Python strings
        if hasattr(primary, 'item'):  # Check if it's numpy type
            primary = str(primary)
        
        print(f"   Dict format: intent={primary}, conf={conf}", file=sys.stderr)
        
        return {
            "primary_intent": primary,
            "confidence": float(conf),  # Ensure it's a Python float
            "all_intents": all_intents,
        }
    elif isinstance(result, list) and len(result) > 0:
        # Format: [("course_info", 0.95), ("chitchat", 0.03), ...]
        intent_raw = result[0][0]
        conf_raw = result[0][1]
        
        # Convert numpy strings to Python strings
        intent = str(intent_raw) if hasattr(intent_raw, 'item') else intent_raw
        conf = float(conf_raw)
        
        print(f"   List format: {result[0]}", file=sys.stderr)
        return {
            "primary_intent": intent,
            "confidence": conf,
            "all_intents": result,
        }
    else:
        # Fallback
        return {"primary_intent": "chitchat", "confidence": 0.5, "all_intents": []}


def should_override_intent(
    text: str,
    intent: str,
    confidence: float,
    context_course: Optional[str],
    context_instructor: Optional[str],
    has_new_entities: bool,
    requested_attributes: Optional[List[str]] = None  # NEW: Pass in requested attributes
) -> Tuple[bool, Optional[str]]:
    """Determine if intent should be overridden based on context."""
    config = INTENT_OVERRIDE_CONFIG
    
    # Never override safe intents
    if intent in config["safe_intents"]:
        return False, None
    
    # Don't override if high confidence and not clearly wrong
    if confidence >= config["confidence_threshold"] and intent in COURSE_INTENTS:
        return False, None
    
    # Don't override if user is changing topic
    text_lower = text.lower()
    if any(kw in text_lower for kw in config["topic_change_keywords"]):
        return False, None
    
    # Don't override if new entities mentioned (not continuation)
    if has_new_entities:
        return False, None
    
    # Check if we have context to use
    if not (context_course or context_instructor):
        return False, None
    
    # NEW: Handle queries with requested attributes but no entities
    # Example: "when?" with active context should become schedule_query
    if requested_attributes and not has_new_entities:
        # Map attributes to intents
        attrs_lower = [a.lower() for a in requested_attributes]
        
        if "instructor" in attrs_lower:
            return True, "instructor_lookup"
        elif "location" in attrs_lower:
            return True, "course_location"
        elif "time" in attrs_lower or "schedule" in attrs_lower:
            return True, "schedule_query"
        elif "sections" in attrs_lower:
            return True, "course_info"
    
    # Map keywords to intents
    for new_intent, keywords in config["keywords_to_intent"].items():
        if any(kw in text_lower for kw in keywords):
            return True, new_intent
    
    # If confidence is very low and we have context, default to course_info
    if confidence < 0.30 and context_course:
        return True, "course_info"
    
    return False, None


def build_semantic_parse(user_input: str, context: Optional[Any] = None) -> Dict[str, Any]:
    """
    Main semantic parse entry point - HYBRID VERSION.
    Uses NER extraction (98.8% F1 score).
    """
    raw = user_input or ""
    norm = normalize_text(raw)

    # Intent classification
    full_result = classify_intent_ml(norm)
    primary_intent = full_result["primary_intent"]
    primary_conf = full_result["confidence"]

    # HYBRID entity extraction
    global_entities = extract_all_entities_hybrid(raw)
    
    # Debug: Show what was extracted
    print(f"🔍 NER Extracted:", file=sys.stderr)
    print(f"   Course codes: {global_entities['course_codes']}", file=sys.stderr)
    print(f"   Course names: {global_entities['course_names']}", file=sys.stderr)
    print(f"   Instructors: {global_entities['instructors']}", file=sys.stderr)
    
    global_course_codes = global_entities["course_codes"]
    global_instr_names = global_entities["instructors"]
    global_weekdays = global_entities["weekdays"]
    global_course_names = global_entities["course_names"]
    global_attrs = detect_requested_attributes(raw)
    
    # Course name queries for fuzzy search (if no codes found)
    # FIXED: Store ALL course names, not just the first one
    global_course_name_queries = []
    if  global_course_codes:
        if global_course_names:
            # Use ALL extracted course names from NER
            global_course_name_queries = global_course_names
            
            print(f"   ✓ Using NER course names: {global_course_name_queries}", file=sys.stderr)
        else:
            # NER found no course name - trust it and leave empty
            # The LLM will handle cases where course info is unavailable
            print(f"   ℹ️  No course name found by NER (this is correct for queries like 'give me sections')", file=sys.stderr)
    
    # Intent override logic
    context_course = getattr(context, 'active_course', None) if context else None
    context_instructor = getattr(context, 'active_instructor', None) if context else None
    has_new_entities = bool(global_course_codes or global_instr_names or global_course_name_queries)
    
    should_override, new_intent = should_override_intent(
        raw,
        primary_intent,
        primary_conf,
        context_course,
        context_instructor,
        has_new_entities,
        global_attrs  # NEW: Pass requested attributes
    )
    
    if should_override and new_intent:
        print(f"🔄 Intent Override: {primary_intent} ({primary_conf:.1%}) → {new_intent} (context-based)", file=sys.stderr)
        primary_intent = new_intent
        primary_conf = 1.0
        
        # Inject context entities if missing
        if context_course and not global_course_codes:
            global_course_codes = [context_course]
            print(f"   ✓ Injected course from context: {context_course}", file=sys.stderr)
        
        if context_instructor and not global_instr_names:
            global_instr_names = [context_instructor]
            print(f"   ✓ Injected instructor from context: {context_instructor}", file=sys.stderr)
    
    # Extract section if mentioned
    section_from_keyword = extract_section_from_text(raw)
    if section_from_keyword and global_course_codes:
        first_code = global_course_codes[0]
        if not re.search(r'[A-Z]\d{1,2}$', first_code):
            global_course_codes[0] = f"{first_code} {section_from_keyword}"

    # Multi-query handling
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

        # HYBRID extraction for each clause
        c_entities = extract_all_entities_hybrid(clause)
        c_codes = c_entities["course_codes"]
        c_instr = c_entities["instructors"]
        c_days = c_entities["weekdays"]
        c_attrs = detect_requested_attributes(clause)
        
        # Check for section keyword
        c_section = extract_section_from_text(clause)
        if c_section and c_codes:
            first_code = c_codes[0]
            if not re.search(r'[A-Z]\d{1,2}$', first_code):
                c_codes[0] = f"{first_code} {c_section}"

        subqueries.append({
            "intent": c_intent,
            "confidence": c_conf,
            "text": clause,
            "course_codes": c_codes,
            "instructor_names": c_instr,
            "weekdays": c_days,
            "requested_attributes": c_attrs,
            "multi_course": len(c_codes) > 1,
        })

    is_multi_query = False
    if len(subqueries) > 1 and len(set(clause_intents)) > 1:
        is_multi_query = True
    
    # Resolve pronoun references
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
        "course_name_queries": global_course_name_queries,  # FIXED: plural
        "subqueries": subqueries,
    }

    return result


def _resolve_pronoun_references(subqueries: List[Dict[str, Any]], global_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Resolve pronouns in multi-query scenarios."""
    resolved = []
    
    context_courses = []
    context_instructors = []
    context_weekdays = []
    
    for i, subq in enumerate(subqueries):
        intent = (subq.get("intent") or "").lower()
        confidence = subq.get("confidence", 0.0)
        
        is_pronoun_query = (
            (intent == "chitchat" or confidence < 0.5) and
            not subq.get("course_codes") and
            not subq.get("instructor_names") and
            subq.get("requested_attributes")
        )
        
        if is_pronoun_query:
            inherited = subq.copy()
            
            if context_courses:
                inherited["course_codes"] = context_courses.copy()
            elif global_data.get("course_codes"):
                inherited["course_codes"] = global_data["course_codes"].copy()
            
            if context_instructors:
                inherited["instructor_names"] = context_instructors.copy()
            elif global_data.get("instructor_names"):
                inherited["instructor_names"] = global_data["instructor_names"].copy()
            
            if context_weekdays:
                inherited["weekdays"] = context_weekdays.copy()
            elif global_data.get("weekdays"):
                inherited["weekdays"] = global_data["weekdays"].copy()
            
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
            resolved.append(subq)
            
            if subq.get("course_codes"):
                context_courses = subq["course_codes"]
            if subq.get("instructor_names"):
                context_instructors = subq["instructor_names"]
            if subq.get("weekdays"):
                context_weekdays = subq["weekdays"]
    
    return resolved


# ============================================================
# CLI TEST
# ============================================================
if __name__ == "__main__":
    print("Semantic parser test mode (NER-ONLY). Type a query (or 'quit').\n")
    while True:
        msg = input("You: ").strip()
        if msg.lower() in {"quit", "exit", "bye"}:
            break
        parsed = build_semantic_parse(msg)
        from pprint import pprint
        pprint(parsed)
        print("-" * 60)