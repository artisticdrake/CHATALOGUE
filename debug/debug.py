"""
debug.py - Complete Pipeline Debugger for Chatalogue
Shows every step of query processing from user input to final answer
"""

import json
import sys
from typing import Any, Dict, List, Optional

from intent_classifier import get_intent_classifier
from semantic_parser import build_semantic_parse
from db_interface import process_semantic_query, inject_db_results, needs_fuzzy_search
from chatalogue import (
    ConversationContext,
    call_external_db_service,
    format_db_results_for_rag,
    rag_answer_with_db,
)

# ============================================================
# FORMATTING UTILITIES
# ============================================================

def print_header(title: str, char: str = "=") -> None:
    """Print a major section header."""
    width = 100
    print(f"\n{char * width}")
    print(title.center(width))
    print(f"{char * width}\n")


def print_subheader(title: str) -> None:
    """Print a subsection header."""
    print(f"\n{'-' * 100}")
    print(f"  {title}")
    print(f"{'-' * 100}")


def print_json(obj: Any, indent: int = 2) -> None:
    """Pretty print JSON object."""
    print(json.dumps(obj, indent=indent, ensure_ascii=False))


def print_kv(key: str, value: Any, indent: int = 0) -> None:
    """Print key-value pair with optional indentation."""
    prefix = "  " * indent
    if isinstance(value, (list, dict)):
        print(f"{prefix}{key}:")
        print_json(value)
    else:
        print(f"{prefix}{key}: {value}")


# ============================================================
# MAIN DEBUG PIPELINE
# ============================================================

def debug_pipeline(
    user_input: str,
    *,
    context: Optional[ConversationContext] = None,
    show_rag_prompt: bool = True,
    show_full_results: bool = True
) -> str:
    """
    Run complete debugging pipeline for a user query.
    
    Args:
        user_input: User's question
        context: Optional conversation context (for multi-turn)
        show_rag_prompt: Whether to print the RAG prompt
        show_full_results: Whether to print all DB rows (can be verbose)
    
    Returns:
        Final answer string
    """
    
    # Initialize context if not provided
    ctx = context or ConversationContext()
    
    print_header("CHATALOGUE DEBUG PIPELINE")
    print(f"User Input: {user_input}")
    print(f"Context: {ctx.compress()}")
    
    # ============================================================
    # STAGE 1: INTENT CLASSIFICATION
    # ============================================================
    print_header("STAGE 1: INTENT CLASSIFICATION", "=")
    
    clf = get_intent_classifier()
    intent_result = clf.classify_intent(user_input)
    
    print_kv("Primary Intent", intent_result["primary_intent"])
    print_kv("Confidence", f"{intent_result['confidence']:.2%}")
    print_kv("Top 3 Intents", intent_result["top_k"])
    
    # ============================================================
    # STAGE 2: SEMANTIC PARSING (NER + REGEX)
    # ============================================================
    print_header("STAGE 2: SEMANTIC PARSING", "=")
    
    semantic = build_semantic_parse(user_input, ctx)
    
    print_subheader("Extracted Entities")
    print_kv("Course Codes", semantic.get("course_codes"))
    print_kv("Instructor Names", semantic.get("instructor_names"))
    print_kv("Weekdays", semantic.get("weekdays"))
    print_kv("Course Name Queries", semantic.get("course_name_queries"))  # FIXED: plural
    print_kv("Requested Attributes", semantic.get("requested_attributes"))
    
    print_subheader("Intent Analysis")
    print_kv("Primary Intent", semantic.get("primary_intent"))
    print_kv("Primary Confidence", f"{semantic.get('primary_confidence', 0):.2%}")
    print_kv("Is Multi-Query", semantic.get("is_multi_query"))
    
    if semantic.get("subqueries"):
        print_subheader("Subqueries")
        for i, subq in enumerate(semantic["subqueries"]):
            print(f"\n  Subquery {i}:")
            print_kv("Intent", subq.get("intent"), indent=2)
            print_kv("Text", subq.get("text"), indent=2)
            print_kv("Course Codes", subq.get("course_codes"), indent=2)
            print_kv("Instructors", subq.get("instructor_names"), indent=2)
    
    # ============================================================
    # STAGE 3: CONTEXT HANDLING
    # ============================================================
    print_header("STAGE 3: CONTEXT HANDLING", "=")
    
    print_subheader("Before Context Update")
    print_kv("Active Course", ctx.active_course)
    print_kv("Active Instructor", ctx.active_instructor)
    print_kv("Turn Count", ctx.turn_count)
    
    # Check if context should reset
    should_reset = ctx.should_reset_context(user_input, semantic)
    print_kv("Should Reset Context", should_reset)
    
    if should_reset:
        print("→ Context reset triggered")
        ctx.reset()
    
    # Resolve pronouns
    semantic = ctx.resolve_pronouns(semantic, user_input)
    
    print_subheader("After Pronoun Resolution")
    print_kv("Course Codes", semantic.get("course_codes"))
    print_kv("Instructor Names", semantic.get("instructor_names"))
    print_kv("Weekdays", semantic.get("weekdays"))
    
    # ============================================================
    # STAGE 4: FUZZY SEARCH CHECK
    # ============================================================
    print_header("STAGE 4: FUZZY SEARCH CHECK", "=")
    
    needs_fuzzy = needs_fuzzy_search(semantic)
    print_kv("Needs Fuzzy Search", needs_fuzzy)
    
    if needs_fuzzy:
        course_name_queries = semantic.get("course_name_queries", [])
        print_kv("Course Name Queries", course_name_queries)
        
        # FIXED: Loop through ALL course names
        accumulated_course_codes = []
        all_fuzzy_results = []
        
        for course_name in course_name_queries:
            # Build fuzzy search request for this course name
            fuzzy_request = {
                "query_type": "fuzzy_course_search",
                "search_term": course_name
            }
            
            print_subheader(f"Fuzzy Search Request for: '{course_name}'")
            print_json(fuzzy_request)
            
            # Execute fuzzy search
            print_subheader("Calling External DB Service")
            fuzzy_results = call_external_db_service(fuzzy_request)
            
            print_subheader(f"Fuzzy Search Results for '{course_name}'")
            if fuzzy_results:
                print(f"Found {len(fuzzy_results)} matching course(s):")
                for result in fuzzy_results[:10]:  # Show first 10
                    print(f"  - {result.get('course_number')}: {result.get('course_name')}")
                if len(fuzzy_results) > 10:
                    print(f"  ... and {len(fuzzy_results) - 10} more")
                
                # Accumulate course codes
                for result in fuzzy_results:
                    code = result.get('course_number')
                    if code and code not in accumulated_course_codes:
                        accumulated_course_codes.append(code)
                        all_fuzzy_results.append(result)
            else:
                print("  No matches found")
        
        # Inject ALL accumulated course codes
        if accumulated_course_codes:
            semantic['course_codes'] = accumulated_course_codes
            print(f"\n✅ Injected all course codes: {accumulated_course_codes}")
        
        # Re-generate query with all fuzzy results
        query_request = process_semantic_query(semantic)
        print_subheader("Query Request (After Fuzzy Injection)")
        print_json(query_request)
    else:
        # No fuzzy search needed
        query_request = process_semantic_query(semantic)
        print("→ No fuzzy search needed, proceeding with direct query")
    
    # ============================================================
    # STAGE 5: SQL QUERY GENERATION
    # ============================================================
    print_header("STAGE 5: SQL QUERY GENERATION", "=")
    
    subqueries = query_request.get("subqueries", [])
    
    if not subqueries:
        print("⚠️  No subqueries generated (chitchat or invalid query)")
    else:
        print(f"Generated {len(subqueries)} subquer{'y' if len(subqueries) == 1 else 'ies'}:\n")
        
        for i, subq in enumerate(subqueries):
            print_subheader(f"Subquery {i}")
            print_kv("Intent", subq.get("intent"))
            print_kv("Course Code", subq.get("course_code_used"))
            print_kv("Instructor", subq.get("instructor_used"))
            print_kv("Weekdays", subq.get("weekdays_used"))
            print_kv("Requested Attrs", subq.get("requested_attributes"))
            
            if subq.get("sql_string"):
                print("\nSQL Query:")
                print(f"  {subq['sql_string']}")
                print(f"\nSQL Parameters:")
                print(f"  {subq.get('sql_params', [])}")
            else:
                print("\n→ No SQL query (chitchat intent)")
    
    # ============================================================
    # STAGE 6: DATABASE EXECUTION
    # ============================================================
    print_header("STAGE 6: DATABASE EXECUTION", "=")
    
    print("Calling external DB service...")
    db_rows = call_external_db_service(query_request)
    
    print_subheader("Raw DB Results")
    if isinstance(db_rows, list):
        print(f"Received {len(db_rows)} result set(s)")
        
        for i, result_set in enumerate(db_rows):
            if isinstance(result_set, list):
                print(f"\nResult set {i}: {len(result_set)} row(s)")
                if show_full_results:
                    for row in result_set[:5]:  # Show first 5
                        print_json(row)
                    if len(result_set) > 5:
                        print(f"  ... and {len(result_set) - 5} more rows")
                else:
                    print(f"  (Use show_full_results=True to see all rows)")
            else:
                print(f"\nResult set {i}: {result_set}")
    else:
        print(f"Unexpected result type: {type(db_rows)}")
        print_json(db_rows)
    
    # Inject results back
    db_result = inject_db_results(query_request, db_rows)
    
    print_subheader("Structured DB Result")
    subresults = db_result.get("subresults", [])
    print(f"Subresults: {len(subresults)}")
    
    for i, subres in enumerate(subresults):
        rows = subres.get("rows", [])
        print(f"  Subresult {i}: {len(rows)} row(s)")
    
    # ============================================================
    # STAGE 7: CONTEXT UPDATE
    # ============================================================
    print_header("STAGE 7: CONTEXT UPDATE", "=")
    
    print_subheader("Before Update")
    print_kv("Active Course", ctx.active_course)
    print_kv("Active Instructor", ctx.active_instructor)
    print_kv("Active Weekdays", ctx.active_weekdays)
    
    ctx.update(semantic, db_result, user_input)
    
    print_subheader("After Update")
    print_kv("Active Course", ctx.active_course)
    print_kv("Active Instructor", ctx.active_instructor)
    print_kv("Active Weekdays", ctx.active_weekdays)
    print_kv("Turn Count", ctx.turn_count)
    print_kv("Known Facts", list(ctx.known_facts.keys())[:5] if ctx.known_facts else [])
    
    # ============================================================
    # STAGE 8: RAG PROMPT CONSTRUCTION
    # ============================================================
    print_header("STAGE 8: RAG PROMPT CONSTRUCTION", "=")
    
    db_text = format_db_results_for_rag(db_result)
    
    print_kv("DB Context Length", f"{len(db_text)} characters")
    
    if show_rag_prompt:
        print_subheader("Formatted DB Context for LLM")
        preview_length = 1500
        preview = db_text[:preview_length]
        print(preview)
        if len(db_text) > preview_length:
            print(f"\n... (truncated, total length: {len(db_text)} chars)")
    else:
        print("→ RAG prompt hidden (use show_rag_prompt=True to view)")
    
    # ============================================================
    # STAGE 9: LLM RESPONSE GENERATION
    # ============================================================
    print_header("STAGE 9: LLM RESPONSE GENERATION", "=")
    
    print("Calling LLM with RAG context...")
    
    try:
        answer = rag_answer_with_db(user_input, ctx, semantic, db_result)
        
        print_subheader("Final Answer")
        print(answer)
        
    except Exception as e:
        answer = f"Error generating answer: {str(e)}"
        print_subheader("Error")
        print(answer)
        import traceback
        traceback.print_exc()
    
    # ============================================================
    # SUMMARY
    # ============================================================
    print_header("DEBUG SUMMARY", "=")
    print_kv("Intent", semantic.get("primary_intent"))
    print_kv("Entities Found", {
        "courses": len(semantic.get("course_codes", [])),
        "instructors": len(semantic.get("instructor_names", [])),
        "weekdays": len(semantic.get("weekdays", []))
    })
    print_kv("Fuzzy Search Used", needs_fuzzy)
    print_kv("Queries Executed", len(subqueries))
    print_kv("Total DB Rows", sum(len(subres.get("rows", [])) for subres in db_result.get("subresults", [])))
    print_kv("Context Updated", ctx.turn_count)
    print("\n" + "=" * 100 + "\n")
    
    return answer


# ============================================================
# MULTI-TURN DEBUGGING
# ============================================================

def debug_conversation(queries: List[str], show_rag_prompt: bool = False) -> None:
    """
    Debug a multi-turn conversation.
    
    Args:
        queries: List of user queries to process in sequence
        show_rag_prompt: Whether to show RAG prompts
    """
    ctx = ConversationContext()
    
    for i, query in enumerate(queries):
        print_header(f"TURN {i + 1} / {len(queries)}", "#")
        print(f"User: {query}\n")
        
        answer = debug_pipeline(
            query,
            context=ctx,
            show_rag_prompt=show_rag_prompt,
            show_full_results=False
        )
        
        print(f"\nBot: {answer}\n")
        print("#" * 100)


# ============================================================
# CLI INTERFACE
# ============================================================

def main():
    """Command-line interface for debugging."""
    
    if len(sys.argv) < 2:
        print("Usage: python debug.py <query>")
        print("   or: python debug.py --conversation")
        print("\nExamples:")
        print("  python debug.py 'who teaches differential equations?'")
        print("  python debug.py 'what about data structures?'")
        print("  python debug.py --conversation  # Interactive mode")
        sys.exit(1)
    
    if sys.argv[1] == "--conversation":
        # Interactive multi-turn mode
        print("=" * 100)
        print("INTERACTIVE DEBUG MODE")
        print("=" * 100)
        print("Type your queries. Commands:")
        print("  - 'quit' or 'exit' to stop")
        print("  - 'reset' to reset context")
        print("  - 'context' to view context")
        print("\n")
        
        ctx = ConversationContext()
        
        while True:
            try:
                query = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting.")
                break
            
            if not query:
                continue
            
            if query.lower() in {"quit", "exit", "bye"}:
                break
            
            if query.lower() == "reset":
                ctx.reset()
                print("Context reset.\n")
                continue
            
            if query.lower() == "context":
                print(f"Context: {ctx.compress()}")
                print(f"Turn count: {ctx.turn_count}\n")
                continue
            
            debug_pipeline(query, context=ctx, show_rag_prompt=True)
    
    else:
        # Single query mode
        query = " ".join(sys.argv[1:])
        debug_pipeline(query, show_rag_prompt=True, show_full_results=True)


if __name__ == "__main__":
    main()