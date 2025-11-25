# chat_driver.py - SIMPLIFIED RAG-FIRST ARCHITECTURE
# Everything goes through RAG with DB context
# Uses external DB service (run_query.py) for all database operations

from __future__ import annotations
from typing import Any, Dict, List, Optional
import traceback
import os
import json
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
        print(f"Error calling DB service: {e}")
        traceback.print_exc()
        # Return empty results on error
        num_subqueries = len(query_request.get("subqueries", []))
        return [[] for _ in range(num_subqueries)]

# chatalogue.py - Add this after the imports and before ConversationContext

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
        
        # 1) Semantic parse
        semantic = build_semantic_parse(user_text)
        
        # 2) Check if we should reset context (topic change)
        if context.should_reset_context(user_text, semantic):
            context.reset()
        
        # 3) Resolve pronouns using context
        semantic = context.resolve_pronouns(semantic, user_text)
        
        # 4) Generate query parameters (NO DB ACCESS HERE)
        query_request = process_semantic_query(semantic)
        
        # 5) ⭐ CALL EXTERNAL DB SERVICE ⭐
        db_rows = call_external_db_service(query_request)
        
        # 6) Inject results back into our format
        db_result = inject_db_results(query_request, db_rows)
        
        # 7) Update context from results
        context.update(semantic, db_result)
        
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
# CONVERSATION CONTEXT MANAGER
# ============================================================

class ConversationContext:
    """Tracks conversation state and entities across turns."""
    
    def __init__(self):
        self.active_course: Optional[str] = None
        self.active_section: Optional[str] = None
        self.active_instructor: Optional[str] = None
        self.active_weekdays: List[str] = []
        
        self.known_facts: Dict[str, Any] = {}
        self.turn_count: int = 0
        self.last_intent: Optional[str] = None
        
        self.topic_change_keywords = {
            'instead', 'rather', 'actually', 'wait',
            'no', "let's talk about", 'tell me about',
            'what about', 'how about', 'switch to'
        }
    
    def should_reset_context(self, user_text: str, semantic: Dict[str, Any]) -> bool:
        text_lower = user_text.lower()
        
        if any(keyword in text_lower for keyword in self.topic_change_keywords):
            return True
        
        new_courses = semantic.get('course_codes', [])
        if new_courses and self.active_course:
            if not any(self.active_course in nc or nc in self.active_course for nc in new_courses):
                return True
        
        if self.turn_count > 10:
            return True
        
        return False
    
    def resolve_pronouns(self, semantic: Dict[str, Any], user_text: str) -> Dict[str, Any]:
        text_lower = user_text.lower()
        has_pronoun = any(p in text_lower for p in ['it', 'that', 'this', 'them', 'those'])
        
        if has_pronoun:
            if not semantic['course_codes'] and self.active_course:
                semantic['course_codes'] = [self.active_course]
            
            if not semantic['instructor_names'] and self.active_instructor:
                semantic['instructor_names'] = [self.active_instructor]
            
            if not semantic['weekdays'] and self.active_weekdays:
                semantic['weekdays'] = self.active_weekdays.copy()
        
        for subq in semantic.get('subqueries', []):
            if not subq.get('course_codes') and self.active_course:
                subq['course_codes'] = [self.active_course]
            if not subq.get('instructor_names') and self.active_instructor:
                subq['instructor_names'] = [self.active_instructor]
        
        return semantic
    
    def update(self, semantic: Dict[str, Any], db_result: Dict[str, Any]):
        if semantic.get('course_codes'):
            self.active_course = semantic['course_codes'][0]
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
        
        self.turn_count += 1
    
    def reset(self):
        self.active_course = None
        self.active_section = None
        self.active_instructor = None
        self.active_weekdays = []
        self.known_facts = {}
        self.turn_count = 0
        self.last_intent = None
    
    def compress(self) -> str:
        parts = []
        
        if self.active_course:
            parts.append(f"Course: {self.active_course}")
        
        if self.active_instructor:
            parts.append(f"Instructor: {self.active_instructor}")
        
        if self.active_course and self.active_course in self.known_facts:
            facts = self.known_facts[self.active_course]
            if facts.get('location'):
                parts.append(f"Location: {facts['location']}")
            if facts.get('days') and facts.get('times'):
                parts.append(f"Time: {facts['days']} {facts['times']}")
        
        return " | ".join(parts) if parts else "No active context"


# ============================================================
# FORMAT DB RESULTS FOR RAG
# ============================================================

def format_db_results_for_rag(db_result: Dict[str, Any]) -> str:
    """Convert DB results into structured text for LLM."""
    subresults = db_result.get('subresults', [])
    
    if not subresults:
        return "Database: No results found."
    
    formatted_parts = []
    
    for sub in subresults:
        rows = sub.get('rows', [])
        course_code = sub.get('course_code_used', '')
        instructor_used = sub.get('instructor_used', '')
        
        if not rows:
            if course_code:
                formatted_parts.append(f"No data found for {course_code}")
            elif instructor_used:
                formatted_parts.append(f"No classes found for instructor {instructor_used}")
            continue
        
        # SINGLE SPECIFIC SECTION QUERY (e.g., "Where is C4?" with context MA 242)
        if len(rows) == 1:
            row = rows[0]
            section_info = f"Course: {row.get('course_number', '')} Section {row.get('section', '')}\n"
            section_info += f"Instructor: {row.get('instructor', '')}\n"
            section_info += f"Location: {row.get('location', '')}\n"
            section_info += f"Time: {row.get('days', '')} {row.get('times', '')}\n"
            formatted_parts.append(section_info)
            continue
        
        # Group by instructor if it's a course query
        if course_code and not instructor_used:
            instructors_dict = {}
            for row in rows:
                instr = row.get('instructor', 'Unknown')
                if instr not in instructors_dict:
                    instructors_dict[instr] = []
                instructors_dict[instr].append(row)
            
            course_info = f"Course: {course_code}\n"
            course_info += f"Instructors:\n"
            
            for instr, instr_rows in instructors_dict.items():
                sections = [r.get('section', '') for r in instr_rows]
                locations = list(set([r.get('location', '') for r in instr_rows if r.get('location')]))
                times = list(set([f"{r.get('days', '')} {r.get('times', '')}" for r in instr_rows if r.get('days')]))
                
                course_info += f"  - {instr}: {len(sections)} sections ({', '.join(sections)})\n"
                if locations:
                    course_info += f"    Locations: {', '.join(locations)}\n"
                if times:
                    course_info += f"    Times: {', '.join(times[:5])}\n"
            
            formatted_parts.append(course_info)
        
        # Instructor query
        elif instructor_used:
            instructor_info = f"Instructor: {instructor_used}\n"
            instructor_info += f"Courses taught ({len(rows)}):\n"
            for row in rows[:10]:
                instructor_info += f"  - {row.get('course_number', '')} {row.get('section', '')}: {row.get('days', '')} {row.get('times', '')} in {row.get('location', '')}\n"
            if len(rows) > 10:
                instructor_info += f"  ... and {len(rows) - 10} more\n"
            formatted_parts.append(instructor_info)
        
        # Weekday query or multiple results
        else:
            results_info = f"Found {len(rows)} classes:\n"
            for row in rows[:10]:
                results_info += f"  - {row.get('course_number', '')} {row.get('section', '')}: {row.get('instructor', '')} | {row.get('days', '')} {row.get('times', '')} | {row.get('location', '')}\n"
            if len(rows) > 10:
                results_info += f"  ... and {len(rows) - 10} more\n"
            formatted_parts.append(results_info)
    
    return "\n".join(formatted_parts)


# ============================================================
# RAG WITH DB CONTEXT
# ============================================================

def rag_answer_with_db(
    user_text: str,
    context: ConversationContext,
    semantic: Dict[str, Any],
    db_result: Dict[str, Any]
) -> str:
    """
    Generate answer using RAG with full DB context.
    LLM decides what to do with the data.
    """
    
    if client is None:
        return "RAG is unavailable. Please set OPENAI_API_KEY environment variable."
    
    # Format DB results
    db_info = format_db_results_for_rag(db_result)
    
    # Get conversation context
    compressed_ctx = context.compress()
    
    # System prompt
    system_prompt = """You are a helpful campus course assistant chatbot.

YOUR JOB:
- Answer student questions about courses using the database information provided
- Respond to greetings naturally 
- Be direct and concise (1-2 sentences for factual queries)
- NO frequent filler phrases like "feel free to ask", "let me know if you need more"
- Just answer the question directly

GREETINGS:
- If user greets you, Greet back warmly and briefly

DATABASE USAGE:
- The database info is FACTS - use it exactly as provided
- If database shows multiple instructors, list ALL of them
- If database shows multiple sections, mention the count
- Never make up course codes, instructors, locations, or times
- For single section queries, provide FULL details (instructor, location, time)

EXAMPLES:
Good: "MA 226 is taught by Goh (6 sections), Moore (6 sections), and Chung (6 sections)."
Bad: "MA 226 is taught by Goh. Feel free to ask more!"

Good: "MA 242 C4 is taught by Weinstein, meets MWF 9:05-9:55 am in CAS 211."
Bad: "C4 is located in the CAS building."

Keep it professional, accurate, and complete."""

    # User prompt with DB context
    context_str = f"Conversation context: {compressed_ctx}\n" if compressed_ctx != "No active context" else ""
    
    user_prompt = f"""{context_str}
DATABASE INFORMATION:
{db_info}

STUDENT QUESTION: {user_text}

Provide a direct, concise answer using the database information above."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=150,
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
    print("All queries go through RAG with external database service")
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
            semantic = build_semantic_parse(user_text)
            
            # 2) Check if we should reset context (topic change)
            if context.should_reset_context(user_text, semantic):
                context.reset()
            
            # 3) Resolve pronouns using context
            semantic = context.resolve_pronouns(semantic, user_text)
            
            # 4) Generate query parameters (NO DB ACCESS HERE)
            query_request = process_semantic_query(semantic)
            
            # 5) ⭐ CALL EXTERNAL DB SERVICE ⭐
            db_rows = call_external_db_service(query_request)
            
            # 6) Inject results back into our format
            db_result = inject_db_results(query_request, db_rows)
            
            # 7) Update context from results
            context.update(semantic, db_result)
            
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