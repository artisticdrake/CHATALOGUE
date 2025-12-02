# chat_driver.py - SIMPLIFIED RAG-FIRST ARCHITECTURE
# Everything goes through RAG with DB context
# Uses external DB service (run_query.py) for all database operations

from __future__ import annotations
from typing import Any, Dict, List, Optional
import traceback
import os
import json
import sys
from openai import OpenAI

from semantic_parser import build_semantic_parse
from db_interface import process_semantic_query, inject_db_results

# Initialize OpenAI
try:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
except Exception as e:
    print(f"Warning: OpenAI client initialization failed: {e}")
    client = None


# ============================================================
# EXTERNAL DB SERVICE INTEGRATION
# ============================================================

def call_external_db_service(query_request: Dict[str, Any]) -> List[List[Dict[str, Any]]]:
    """
    Call external DB service (run_query.py) by importing their module.
    
    Args:
        query_request: Query parameters from process_semantic_query()
        
    Returns:
        List of row lists: [[{row1}, {row2}], [{row3}], ...]
    """
    try:
        # Import their function
        from run_query import handle_request
        
        # Call their function
        db_rows = handle_request(query_request)
        return db_rows
        
    except Exception as e:
        print(f"Error calling DB service: {e}", file=sys.stderr)
        traceback.print_exc()
        # Return empty results on error
        num_subqueries = len(query_request.get("subqueries", []))
        return [[] for _ in range(num_subqueries)]


# ============================================================
# GLOBAL CONTEXT (for GUI integration)
# ============================================================

# Create a global context that persists across GUI calls
_global_context = None
_global_history = []

def get_or_create_context():
    """Get or create the global conversation context."""
    global _global_context
    if _global_context is None:
        _global_context = ConversationContext()
    return _global_context


# ============================================================
# GUI INTEGRATION FUNCTION
# ============================================================

def chat_loop(user_text: str) -> str:
    """
    Main function called by the GUI.
    Processes user input and returns bot response.
    
    Args:
        user_text: User's message from GUI
        
    Returns:
        Bot's response string
    """
    global _global_context, _global_history
    
    # Get or create context
    context = get_or_create_context()
    
    try:
        # Handle special commands
        if user_text.lower() in {"reset", "clear"}:
            context.reset()
            return "Context reset. Starting fresh!"
        
        if user_text.lower() == "context":
            return f"Current context: {context.compress()}\nTurn count: {context.turn_count}"
        
        # 1) Semantic parse (with context for intent override)
        semantic = build_semantic_parse(user_text, context)
        
        # 2) Check if we should reset context (topic change)
        if context.should_reset_context(user_text, semantic):
            context.reset()
        
        # 3) Resolve pronouns AND implicit references using context
        semantic = context.resolve_references(semantic, user_text)
        
        # 4) Generate query parameters (NO DB ACCESS HERE)
        query_request = process_semantic_query(semantic)
        
        # 4a) CHECK IF FUZZY SEARCH NEEDED 
        # FIXED: Loop through ALL course names (not just one)
        course_name_queries = semantic.get("course_name_queries", [])
        accumulated_course_codes = []
        
        for course_name in course_name_queries:
            # Create fuzzy search request for this course name
            fuzzy_search_request = {
                "query_type": "fuzzy_course_search",
                "search_term": course_name
            }
            
            # Call DB service with fuzzy search request
            fuzzy_results = call_external_db_service(fuzzy_search_request)
            
            # Accumulate course codes from fuzzy results
            for result in fuzzy_results:
                code = result.get('course_number')
                if code and code not in accumulated_course_codes:
                    accumulated_course_codes.append(code)
        
        # Inject ALL accumulated course codes back into semantic parse
        if accumulated_course_codes:
            semantic['course_codes'] = accumulated_course_codes
            # Re-generate query with all course codes
            query_request = process_semantic_query(semantic)
        
        # 5) CALL EXTERNAL DB SERVICE 
        db_rows = call_external_db_service(query_request)
        
        # 6) Inject results back into our format
        db_result = inject_db_results(query_request, db_rows)
        
        # 7) Update context from results
        context.update(semantic, db_result, user_text)
        
        # 8) ALWAYS use RAG with DB context
        answer = rag_answer_with_db(user_text, context, semantic, db_result)
        
        # 9) Save history (compressed)
        _global_history.append({
            "user": user_text,
            "bot": answer,
            "context": context.compress(),
            "turn": context.turn_count
        })
        
        # Keep only last 10 turns
        if len(_global_history) > 10:
            _global_history = _global_history[-10:]
        
        return answer
        
    except Exception as e:
        error_msg = f"Sorry, something went wrong: {str(e)}"
        traceback.print_exc()
        return error_msg


# For backwards compatibility with old GUI code that might call this
def process_user_input(user_text: str) -> str:
    """Alias for chat_loop for backwards compatibility."""
    return chat_loop(user_text)


# ============================================================
# CONVERSATION CONTEXT MANAGER (ENHANCED)
# ============================================================

class ConversationContext:
    """Tracks conversation state and entities across turns with enhanced context handling."""
    
    def __init__(self):
        self.active_course: Optional[str] = None
        self.active_section: Optional[str] = None
        self.active_instructor: Optional[str] = None
        self.active_weekdays: List[str] = []
        
        self.known_facts: Dict[str, Any] = {}
        self.turn_count: int = 0
        self.last_intent: Optional[str] = None
        
        # NEW: Conversation history for context summary
        self.conversation_history: List[Dict[str, str]] = []
        
        self.topic_change_keywords = {
            'instead', 'rather', 'actually', 'wait',
            'no', "let's talk about", 'tell me about',
            'what about', 'how about', 'switch to'
        }
    
    def should_reset_context(self, user_text: str, semantic: Dict[str, Any]) -> bool:
        """Check if context should be reset based on user signals."""
        text_lower = user_text.lower()
        
        # Explicit topic change
        if any(keyword in text_lower for keyword in self.topic_change_keywords):
            return True
        
        # New course that doesn't match active course
        new_courses = semantic.get('course_codes', [])
        if new_courses and self.active_course:
            if not any(self.active_course in nc or nc in self.active_course for nc in new_courses):
                return True
        
        # Too many turns
        if self.turn_count > 10:
            return True
        
        return False
    
    def should_query_context(self, user_text: str, semantic: Dict[str, Any]) -> bool:
        """
        Decide if we should query the active course from context.
        
        Don't query for high-confidence non-course intents:
        - event, weather, alert, chitchat with confidence > 0.8
        
        Query for everything else if context exists.
        """
        if not self.active_course:
            return False
        
        intent = semantic.get("primary_intent", "")
        confidence = semantic.get("primary_confidence", 0.0)
        
        # Skip high-confidence non-course intents
        skip_intents = {"event_query", "weather", "alert_query", "chitchat"}
        if intent in skip_intents and confidence > 0.8:
            print(f"   ℹ️  Skipping context query for {intent} (confidence: {confidence:.2%})", file=sys.stderr)
            return False
        
        # Query for everything else
        return True
    
    def should_inject_context(self, semantic: Dict[str, Any], user_text: str) -> tuple[bool, str]:
        """
        Decide if we should inject context based on:
        1. Intent confidence
        2. Extracted entities
        3. Context similarity (topic change detection)
        
        Returns:
            (should_inject: bool, reason: str)
        """
        confidence = semantic.get('primary_confidence', 0.0)
        intent = semantic.get('primary_intent', '')
        
        # Check what entities user mentioned
        has_course_codes = bool(semantic.get('course_codes'))
        has_instructor_names = bool(semantic.get('instructor_names'))
        has_course_names = bool(semantic.get('course_names') or semantic.get('course_name_queries'))
        has_any_entities = has_course_codes or has_instructor_names or has_course_names
        
        # Check for explicit pronouns (but filter out false positives)
        text_lower = user_text.lower()
        time_phrases = ['this semester', 'this year', 'that semester', 'that year', 'this term', 'that term']
        text_has_time_phrase = any(phrase in text_lower for phrase in time_phrases)
        
        has_clear_pronoun = (
            ' it ' in text_lower or text_lower.startswith('it ') or text_lower.endswith(' it') or
            ' them ' in text_lower or
            ' those ' in text_lower or
            (' this ' in text_lower and not text_has_time_phrase) or
            (' that ' in text_lower and not text_has_time_phrase)
        )
        
        # Check for topic change (NEW entity different from context)
        has_topic_change = False
        if has_instructor_names and self.active_instructor:
            new_instructor = semantic['instructor_names'][0].lower()
            old_instructor = self.active_instructor.lower()
            if new_instructor != old_instructor:
                has_topic_change = True
        
        if has_course_codes and self.active_course:
            new_course = semantic['course_codes'][0].lower()
            old_course = self.active_course.lower()
            if new_course not in old_course and old_course not in new_course:
                has_topic_change = True
        
        # RULE 1: High confidence (>85%) + entities = Don't inject (new query)
        if confidence > 0.85 and has_any_entities:
            return False, f"High confidence ({confidence:.1%}) with entities - treating as new query"
        
        # RULE 2: Topic change = Don't inject (different subject)
        if has_topic_change:
            return False, "Topic changed - new entity mentioned that differs from context"
        
        # RULE 3: Clear pronoun = Inject (explicit reference)
        if has_clear_pronoun:
            return True, "Explicit pronoun detected (it/them/those/this/that)"
        
        # RULE 4: Low confidence (<50%) + no entities = Inject (continuation)
        if confidence < 0.50 and not has_any_entities:
            return True, f"Low confidence ({confidence:.1%}) without entities - likely continuation"
        
        # RULE 5: Medium confidence + course intent + no entities = Inject
        course_intents = {'course_info', 'instructor_lookup', 'schedule_query', 'course_location', 'course_time'}
        if intent in course_intents and not has_any_entities and confidence > 0.30:
            return True, f"Course-related intent ({intent}) without entities - checking context"
        
        # Default: Don't inject
        return False, "No clear indication to use context"
    
    def resolve_references(self, semantic: Dict[str, Any], user_text: str) -> Dict[str, Any]:
        """
        Resolve both explicit pronouns AND implicit references.
        Uses the new should_inject_context() decision function.
        """
        # NEW: Use the decision function
        should_inject, reason = self.should_inject_context(semantic, user_text)
        
        print(f"   🤔 Context injection decision: {reason}", file=sys.stderr)
        
        if should_inject:
            # Don't inject if user provided course names (they need fuzzy search first)
            has_course_names = bool(semantic.get('course_names') or semantic.get('course_name_queries'))
            
            # HIERARCHY: Only inject ONE thing based on priority
            # Priority 1: Course (most comprehensive - gets all instructors, sections, times)
            # Priority 2: Instructor (only if no course)
            # Priority 3: Weekdays (only if no course/instructor)
            
            injected = False
            
            # Priority 1: Course code (highest priority - most complete information)
            if not semantic.get('course_codes') and self.active_course and not has_course_names:
                semantic['course_codes'] = [self.active_course]
                print(f"   ✓ Injected course from context: {self.active_course}", file=sys.stderr)
                print(f"   ℹ️  Skipping instructor/weekday injection (course provides complete info)", file=sys.stderr)
                injected = True
            
            # Priority 2: Instructor (only if no course injected)
            elif not injected and not semantic.get('instructor_names') and self.active_instructor:
                intent = semantic.get('primary_intent', '')
                is_instructor_query = intent == 'instructor_lookup'
                
                if not is_instructor_query:
                    semantic['instructor_names'] = [self.active_instructor]
                    print(f"   ✓ Injected instructor from context: {self.active_instructor}", file=sys.stderr)
                    print(f"   ℹ️  Skipping weekday injection (instructor provides broader info)", file=sys.stderr)
                    injected = True
                elif is_instructor_query:
                    print(f"   ℹ️  Skipped instructor injection (intent=instructor_lookup)", file=sys.stderr)
            
            # Priority 3: Weekdays (only if neither course nor instructor injected)
            if not injected and not semantic.get('weekdays') and self.active_weekdays:
                semantic['weekdays'] = self.active_weekdays.copy()
                print(f"   ✓ Injected weekdays from context: {self.active_weekdays}", file=sys.stderr)
        else:
            print(f"   ✗ Not injecting context", file=sys.stderr)
        
        # Also resolve for subqueries (for multi-intent queries)
        course_related_intents = {
            'course_info', 'instructor_lookup', 'course_location',
            'schedule_query', 'course_time'
        }
        
        for subq in semantic.get('subqueries', []):
            # Check if subquery has its OWN entities
            has_own_course_code = bool(subq.get('course_codes'))
            has_own_course_name = bool(subq.get('course_names'))
            has_own_instructor = bool(subq.get('instructor_names'))

            # If subquery has ANY entities, DON'T inject context
            if has_own_course_code or has_own_course_name or has_own_instructor:
                continue  # Skip this subquery, it has its own entities        

            # Only inject if COMPLETELY EMPTY and should_inject is True
            subq_empty = not subq.get('course_codes') and not subq.get('instructor_names')
            if subq_empty and should_inject:
                if self.active_course:
                    subq['course_codes'] = [self.active_course]
        
        return semantic
    
    # Alias for backward compatibility
    def resolve_pronouns(self, semantic: Dict[str, Any], user_text: str) -> Dict[str, Any]:
        """Backward compatibility alias."""
        return self.resolve_references(semantic, user_text)
    
    def build_context_summary(self, current_query: str) -> str:
        """
        Build a summary of recent conversation for the LLM.
        Includes last 3-5 turns to help LLM understand context.
        """
        if not self.conversation_history and not self.active_course:
            return ""
        
        summary_parts = []
        
        # Add active context
        if self.active_course:
            summary_parts.append(f"Current topic: {self.active_course}")
            if self.active_instructor:
                summary_parts.append(f"Known instructor: {self.active_instructor}")
            if self.known_facts.get(self.active_course):
                facts = self.known_facts[self.active_course]
                if facts.get('location'):
                    summary_parts.append(f"Known location: {facts['location']}")
        
        # Add recent conversation (last 3 turns)
        if self.conversation_history:
            summary_parts.append("\nRecent conversation:")
            for turn in self.conversation_history[-3:]:
                summary_parts.append(f"  - User asked: \"{turn['query']}\"")
                if turn.get('intent'):
                    summary_parts.append(f"    (Intent: {turn['intent']})")
        
        # Add current query
        summary_parts.append(f"\nCurrent query: \"{current_query}\"")
        
        return "\n".join(summary_parts)
    
    def update(self, semantic: Dict[str, Any], db_result: Dict[str, Any], user_text: str = ""):
        """Update context with new information from query and results."""
        # Update active entities
        if semantic.get('course_codes'):
            self.active_course = semantic['course_codes'][0]
            # Check if section is included in course code
            if ' ' in self.active_course:
                parts = self.active_course.split()
                if len(parts) > 2 and parts[-1][0].isalpha():
                    self.active_section = parts[-1]
        
        if semantic.get('instructor_names'):
            self.active_instructor = semantic['instructor_names'][0]
        
        if semantic.get('weekdays'):
            self.active_weekdays = semantic['weekdays']
        
        if semantic.get('primary_intent'):
            self.last_intent = semantic['primary_intent']
        
        # Extract facts from DB results
        for sub in db_result.get('subresults', []):
            rows = sub.get('rows', [])
            if rows:
                row = rows[0]
                course_key = sub.get('course_code_used') or self.active_course
                if course_key:
                    if course_key not in self.known_facts:
                        self.known_facts[course_key] = {}
                    
                    self.known_facts[course_key].update({
                        'instructor': row.get('instructor'),
                        'location': row.get('location'),
                        'days': row.get('days'),
                        'times': row.get('times'),
                        'section': row.get('section')
                    })
        
        # Save to conversation history
        self.conversation_history.append({
            'query': user_text or semantic.get('raw_text', ''),
            'intent': semantic.get('primary_intent', ''),
            'turn': self.turn_count
        })
        
        # Keep only last 10 turns
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-10:]
        
        self.turn_count += 1
    
    def reset(self):
        """Reset all context."""
        self.active_course = None
        self.active_section = None
        self.active_instructor = None
        self.active_weekdays = []
        self.known_facts = {}
        self.turn_count = 0
        self.last_intent = None
        self.conversation_history = []
    
    def compress(self) -> str:
        """Get a compressed string representation of current context."""
        parts = []
        if self.active_course:
            parts.append(f"Course: {self.active_course}")
        if self.active_section:
            parts.append(f"Section: {self.active_section}")
        if self.active_instructor:
            parts.append(f"Instructor: {self.active_instructor}")
        if self.active_weekdays:
            parts.append(f"Days: {', '.join(self.active_weekdays)}")
        
        # Add location and time from known_facts if available
        if self.active_course and self.active_course in self.known_facts:
            facts = self.known_facts[self.active_course]
            if facts.get('location'):
                parts.append(f"Location: {facts['location']}")
            if facts.get('times'):
                parts.append(f"Time: {facts.get('days', '')} {facts['times']}")
        
        return " | ".join(parts) if parts else "No active context"


# ============================================================
# DB RESULT FORMATTING
# ============================================================

def format_db_results_for_rag(db_result: Dict[str, Any]) -> str:
    """Format DB results into readable text for RAG."""
    if not db_result or not db_result.get("subresults"):
        return "No database results available."
    
    formatted_parts = []
    
    for subresult in db_result["subresults"]:
        rows = subresult.get("rows", [])
        if not rows:
            continue
        
        intent = subresult.get("intent", "")
        course_used = subresult.get("course_code_used")
        instructor_used = subresult.get("instructor_used")
        
        # Course query
        if course_used and not instructor_used:
            course_info = f"Course: {course_used}\n"
            course_info += f"Sections ({len(rows)}):\ncourse_number, section, course_name, instructor, days, times, location\n"
            for row in rows:
                course_info += f"  {row.get('course_number', '')} | {row.get('section', '')} | {row.get('course_name', '')} | {row.get('instructor', '')} | {row.get('days', '')} | {row.get('times', '')} | {row.get('location', '')}\n"
            formatted_parts.append(course_info)
        
        # Instructor query
        elif instructor_used:
            instructor_info = f"Instructor: {instructor_used}\n " 
            instructor_info += f"Courses taught ({len(rows)}):\ncourse_number, section, course_name, instructor, days, times, location\n"
            for row in rows[:100]:
                instructor_info += f"  - {row.get('course_number', '')} | {row.get('section', '')} | {row.get('course_name', '')} | {row.get('instructor', '')} | {row.get('days', '')} | {row.get('times', '')} | {row.get('location', '')}\n"
            if len(rows) > 100:
                instructor_info += f"  ... and {len(rows) - 100} more\n"
            formatted_parts.append(instructor_info)
        
        # Weekday query or multiple results
        else:
            results_info = f"Found {len(rows)} classes:\ncourse_number, section, course_name, instructor, days, times, location\n"
            for row in rows[:100]:
                results_info += f"  - {row.get('course_number', '')} | {row.get('section', '')} | {row.get('course_name', '')} | {row.get('instructor', '')} | {row.get('days', '')} | {row.get('times', '')} | {row.get('location', '')}\n"
            if len(rows) > 100:
                results_info += f"  ... and {len(rows) - 100} more\n"
            formatted_parts.append(results_info)
    
    return "\n".join(formatted_parts)


# ============================================================
# RAG WITH DB CONTEXT (ENHANCED)
# ============================================================

def rag_answer_with_db(
    user_text: str,
    context: ConversationContext,
    semantic: Dict[str, Any],
    db_result: Dict[str, Any]
) -> str:
    """
    Generate answer using RAG with full DB context and conversation history.
    LLM decides what to do with the data.
    """
    
    if client is None:
        return "RAG is unavailable. Please set OPENAI_API_KEY environment variable."
    
    # Format DB results
    db_info = format_db_results_for_rag(db_result)
    
    # Build context summary (NEW!)
    context_summary = context.build_context_summary(user_text)
    
    # System prompt
    system_prompt = """You are a helpful campus course assistant chatbot.

YOUR JOB:
- Answer student questions about courses using the database information provided
- Respond to greetings naturally 
- Be direct and concise (1-2 sentences for factual queries)
- NO frequent filler phrases like "feel free to ask", "let me know if you need more"
- Just answer the question directly

GREETINGS:
- If user greets you, greet back warmly and briefly

DATABASE USAGE:
- The database info is ABSOLUTE TRUTH- use it exactly as provided
- If the specific information requested is NOT in the database results, explicitly say it's not found/doesn't exist
- Never infer, extrapolate, or guess information that isn't explicitly shown in the data
- If database shows multiple instructors, list ALL of them
- If database shows multiple sections, mention the count
- Never make up course codes, sections, instructors, locations, or times or anything else.
- For single section queries, provide FULL details (instructor, location, time)

CONVERSATION CONTEXT:
- You have access to recent conversation history
- Use this to understand what the user is referring to
- If user says "show me sections" and context shows they asked about example 123, they mean example 123 sections

EXAMPLES:
Good: "EXAMPLECODE 123 is taught by INSTRUCTOR1 (A sections), INSTRUCTOR2 (B sections), and INSTRUCTOR3 (C sections)."
Bad: "EXAMPLECODE 123 is taught by INSTRUCTOR1. Feel free to ask more!"

Good: "EXAMPLECODE 123 SECTION X is taught by INSTRUCTOR1, meets DAY AND TIME in EXAMPLE PLACE."
Bad: "C4 is located in the CAS building."

Keep it professional, accurate, and complete."""

    # User prompt with DB context AND conversation context
    context_str = ""
    if context_summary:
        context_str = f"CONVERSATION CONTEXT:\n{context_summary}\n\n"
    
    user_prompt = f"""{context_str}DATABASE INFORMATION:
{db_info}

STUDENT QUESTION: {user_text}

Provide a direct, concise answer using the database information above."""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=500,
            temperature=0.2,
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        return f"Sorry, I encountered an error: {str(e)}"


# ============================================================
# MAIN DRIVER
# ============================================================

def main():
    print("=" * 80)
    print("ENHANCED CAMPUS CHATBOT - RAG-FIRST ARCHITECTURE")
    print("With improved context handling and conversation awareness")
    print("=" * 80)
    print("Type your question. Commands: 'exit', 'quit', 'reset', 'context'")
    print()

    context = ConversationContext()
    history: List[Dict[str, str]] = []

    while True:
        try:
            user_text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not user_text:
            continue

        # Handle commands
        if user_text.lower() in {"exit", "quit", "bye"}:
            print("Bot: Bye!")
            break
        
        if user_text.lower() == "reset":
            context.reset()
            print("Bot: Context reset. Starting fresh!")
            continue
        
        if user_text.lower() == "context":
            print(f"Bot: Current context: {context.compress()}")
            print(f"     Turn count: {context.turn_count}")
            continue

        try:
            # 1) Semantic parse
            semantic = build_semantic_parse(user_text, context)
            
            # 2) Check if we should reset context (topic change)
            if context.should_reset_context(user_text, semantic):
                context.reset()
            
            # 3) Resolve pronouns AND implicit references using context
            semantic = context.resolve_references(semantic, user_text)
            
            # 4) Generate query parameters (NO DB ACCESS HERE)
            query_request = process_semantic_query(semantic)

            # 4a) CHECK IF FUZZY SEARCH NEEDED 
            # FIXED: Loop through ALL course names
            course_name_queries = semantic.get("course_name_queries", [])
            accumulated_course_codes = []
            
            for course_name in course_name_queries:
                # Create fuzzy search request for this course name
                fuzzy_search_request = {
                    "query_type": "fuzzy_course_search",
                    "search_term": course_name
                }
                
                print(f"🔍 Fuzzy search for: '{course_name}'", file=sys.stderr)
                
                # Call DB service with fuzzy search request
                fuzzy_results = call_external_db_service(fuzzy_search_request)
                
                print(f"✅ Found {len(fuzzy_results)} course(s)", file=sys.stderr)
                for result in fuzzy_results[:5]:  # Show first 5
                    print(f"   - {result.get('course_number')}: {result.get('course_name')}", file=sys.stderr)
                
                # Accumulate course codes from fuzzy results
                for result in fuzzy_results:
                    code = result.get('course_number')
                    if code and code not in accumulated_course_codes:
                        accumulated_course_codes.append(code)
            
            # Inject ALL accumulated course codes back into semantic parse
            if accumulated_course_codes:
                semantic['course_codes'] = accumulated_course_codes
                print(f"   ✓ Injected all course codes: {accumulated_course_codes}", file=sys.stderr)
                # Re-generate query with all course codes
                query_request = process_semantic_query(semantic)
                
            # 5) CALL EXTERNAL DB SERVICE
            db_rows = call_external_db_service(query_request)
            
            # 6) Inject results back into our format
            db_result = inject_db_results(query_request, db_rows)
            
            # 7) Update context from results
            context.update(semantic, db_result, user_text)
            
            # 8) ALWAYS use RAG with DB context
            answer = rag_answer_with_db(user_text, context, semantic, db_result)
            
            # 9) Save history (compressed)
            history.append({
                "user": user_text,
                "bot": answer,
                "context": context.compress(),
                "turn": context.turn_count
            })
            
            # Keep only last 10 turns
            if len(history) > 10:
                history = history[-10:]

        except Exception as e:
            print("Bot: Sorry, something went wrong.")
            print(f"     Error: {str(e)}")
            traceback.print_exc()
            continue

        # 10) Print response
        print(f"Bot: {answer}")


if __name__ == "__main__":
    main()