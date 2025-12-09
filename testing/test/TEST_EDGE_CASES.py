# test_chatbot.py
# ============================================================
# Comprehensive test suite for chatbot with pass/fail tracking
# ============================================================

import sys
from typing import List, Tuple, Optional
from semantic_parser import build_semantic_parse
from db_layer import run_semantic_db_layer
from chatalogue import format_db_results_for_rag, ConversationContext, rag_answer_with_db

# Test format: (query, expected_substrings, description)
TEST_CASES: List[Tuple[str, List[str], str]] = [
    # ==================== INSTRUCTOR QUERIES ====================
    ("Who teaches MA 226?", ["Goh", "Moore", "Chung"], "Multi-instructor course"),
    ("Who teaches CS 575?", ["Nourai"], "Single instructor"),
    ("Who teaches MA 226 B3?", ["Moore", "B3"], "Specific section instructor"),
    ("What does Goh teach?", ["MA 226"], "Instructor's courses"),
    ("What does Nourai teach?", ["CS 575"], "Instructor's courses - single"),
    ("What about Chung?", ["MA 226", "Chung"], "Chitchat with instructor name"),
    ("What about Nourai?", ["CS 575", "Nourai"], "Chitchat with instructor name"),
    ("Chung's classes", ["MA 226", "Chung"], "Possessive instructor"),
    ("Chung's section", ["MA 226", "Chung"], "Possessive with section"),
    ("Tell me about professor Goh", ["MA 226", "Goh"], "With title"),
    
    # ==================== COURSE LOCATION ====================
    ("Where is CS 575?", ["CAS 208"], "Course location"),
    ("Where is MA 226?", ["LSE"], "Multi-location course"),
    ("Where is MA 226 B3?", ["CAS 229"], "Specific section location"),
    ("CS 575 location", ["CAS 208"], "Location without question"),
    ("Location of MA 226", ["LSE", "other"], "Location alternate phrasing"),
    
    # ==================== COURSE TIME ====================
    ("When does CS 575 meet?", ["6:00 pm", "8:45 pm"], "Course time"),
    ("When does MA 226 meet?", ["meets"], "Multi-section time"),
    ("When does MA 226 B3 meet?", ["3:35 pm", "4:25 pm"], "Specific section time"),
    ("CS 575 time", ["6:00 pm"], "Time without question"),
    ("What time is MA 226?", ["meets"], "Time alternate phrasing"),
    
    # ==================== COURSE CODES - FORMATS ====================
    ("Tell me about METCS575", ["CS 575"], "No-space format"),
    ("Tell me about CASMA226", ["MA 226"], "No-space with school"),
    ("Info on CS575", ["CS 575"], "Dept-only format"),
    ("What is MET CS 575", ["CS 575"], "Standard format"),
    ("Tell me about CS 575", ["CS 575"], "Dept space format"),
    
    # ==================== MULTI-COURSE QUERIES ====================
    ("Who teaches CS 575 and MA 226?", ["Nourai", "Goh"], "Multiple courses"),
    ("Where are CS 575 and MA 226?", ["CAS 208", "LSE"], "Multiple locations"),
    
    # ==================== WEEKDAY QUERIES ====================
    ("What classes meet on Monday?", ["Monday"], "Monday classes"),
    ("Classes on Tuesday", ["Tuesday"], "Tuesday classes"),
    ("Classes on Wednesday", ["Wednesday"], "Wednesday classes"),
    ("Classes on Thursday", ["Thursday"], "Thursday classes"),
    ("Classes on Friday", ["Friday"], "Friday classes"),
    ("Classes on Tuesday and Thursday", ["Tuesday"], "Multiple days"),
    ("Monday Wednesday Friday classes", ["Friday"], "MWF pattern"),
    ("Weekend classes", ["Weekend", "no"], "No weekend classes"),
    
    # ==================== CONTEXT & PRONOUNS ====================
    # Note: These need to be tested in sequence
    
    # ==================== GREETINGS ====================
    ("Hi", ["hi"], "Greeting response"),
    ("Hello", ["hi"], "Greeting response"),
    ("Hey", ["hi"], "Greeting response"),
    
    # ==================== EDGE CASES ====================
    ("", ["Hi!"], "Empty query"),
    ("xyz123", [ "no"], "Invalid course"),
    ("Who teaches XYZ 999?", ["no"], "Non-existent course"),
    ("What does Smith teach?", ["Smith"], "Non-existent instructor"),
    
    # ==================== CASE INSENSITIVE ====================
    ("WHO TEACHES CS 575?", ["Nourai"], "All caps"),
    ("where is cs 575?", ["CAS 208"], "All lowercase"),
    ("WhErE iS cS 575?", ["CAS 208"], "Mixed case"),
    
    # ==================== TYPOS ====================
    ("Wher is CS 575?", ["CAS 208"], "Typo in 'where'"),
    ("Who teches CS 575?", ["Nourai"], "Typo in 'teaches'"),
]

# Context-dependent test sequences
CONTEXT_TEST_SEQUENCES = [
    [
        ("Who teaches CS 575?", ["Nourai"], "Initial query"),
        ("Where is it?", ["CAS 208"], "Pronoun - location"),
        ("When does it meet?", ["6:00 pm"], "Pronoun - time"),
    ],
    [
        ("Tell me about MA 226", ["MA 226"], "Initial query"),
        ("Who teaches it?", ["Goh", "Moore", "Chung"], "Pronoun - instructor"),
        ("Where is section B3?", ["CAS 229"], "Section with context"),
    ],
    [
        ("Where is MA 242?", ["CAS 211"], "Initial query"),
        ("Who teaches it?", ["Kon", "Fried", "Weinstein"], "Context maintained"),
        ("What about C4?", ["Weinstein", "LSE B01"], "Section reference"),
    ],
]


# ============================================================
# TEST RUNNER
# ============================================================

def run_single_test(query: str, expected: List[str], description: str, context: Optional[ConversationContext] = None) -> Tuple[bool, str]:
    """Run a single test case and return (passed, answer)."""
    try:
        if context is None:
            context = ConversationContext()
        
        # 1) Parse
        semantic = build_semantic_parse(query)
        
        # 2) Resolve pronouns
        semantic = context.resolve_pronouns(semantic, query)
        
        # 3) Query DB
        db_result = run_semantic_db_layer(semantic)
        
        # 4) Update context
        context.update(semantic, db_result)
        
        # 5) Generate answer
        answer = rag_answer_with_db(query, context, semantic, db_result)
        
        # 6) Check if all expected substrings are in answer
        answer_lower = answer.lower()
        passed = all(exp.lower() in answer_lower for exp in expected)
        
        return passed, answer
        
    except Exception as e:
        return False, f"ERROR: {str(e)}"


def run_all_tests():
    """Run all test cases and print results."""
    
    print("=" * 120)
    print("CHATBOT COMPREHENSIVE TEST SUITE")
    print("=" * 120)
    print()
    
    total = 0
    passed = 0
    failed_tests = []
    
    # ==================== INDIVIDUAL TESTS ====================
    print("=" * 120)
    print("INDIVIDUAL TEST CASES")
    print("=" * 120)
    
    for query, expected, description in TEST_CASES:
        total += 1
        test_passed, answer = run_single_test(query, expected, description)
        
        status = "✅ PASS" if test_passed else "❌ FAIL"
        
        if test_passed:
            passed += 1
        else:
            failed_tests.append((description, query, expected, answer))
        
        print(f"{status} | {description:40} | {query[:50]:50}")
        if not test_passed:
            print(f"      Expected: {expected}")
            print(f"      Got: {answer[:100]}")
            print()
    
    # ==================== CONTEXT TESTS ====================
    print("\n" + "=" * 120)
    print("CONTEXT-DEPENDENT TEST SEQUENCES")
    print("=" * 120)
    
    for seq_idx, sequence in enumerate(CONTEXT_TEST_SEQUENCES):
        print(f"\nSequence {seq_idx + 1}:")
        context = ConversationContext()
        
        for query, expected, description in sequence:
            total += 1
            test_passed, answer = run_single_test(query, expected, description, context)
            
            status = "✅ PASS" if test_passed else "❌ FAIL"
            
            if test_passed:
                passed += 1
            else:
                failed_tests.append((f"Seq{seq_idx+1}: {description}", query, expected, answer))
            
            print(f"  {status} | {description:35} | {query[:45]:45}")
            if not test_passed:
                print(f"        Expected: {expected}")
                print(f"        Got: {answer[:90]}")
    
    # ==================== SUMMARY ====================
    print("\n" + "=" * 120)
    print(f"TEST SUMMARY: {passed}/{total} passed ({passed/total*100:.1f}%)")
    print("=" * 120)
    
    if failed_tests:
        print("\n" + "=" * 120)
        print(f"FAILED TESTS ({len(failed_tests)}):")
        print("=" * 120)
        
        for description, query, expected, answer in failed_tests:
            print(f"\n❌ {description}")
            print(f"   Query: {query}")
            print(f"   Expected: {expected}")
            print(f"   Got: {answer[:150]}")
    else:
        print("\n🎉 ALL TESTS PASSED! 🎉")
    
    print()
    return passed == total


# ============================================================
# INTERACTIVE TEST MODE
# ============================================================

def interactive_test():
    """Run tests interactively - see output for each test."""
    
    print("=" * 120)
    print("INTERACTIVE TEST MODE")
    print("=" * 120)
    print("Press Enter after each test to continue, or 'q' to quit\n")
    
    context = ConversationContext()
    
    for query, expected, description in TEST_CASES:
        print(f"\n{'='*120}")
        print(f"TEST: {description}")
        print(f"Query: {query}")
        print(f"Expected to contain: {expected}")
        print(f"{'='*120}")
        
        test_passed, answer = run_single_test(query, expected, description)
        
        status = "✅ PASS" if test_passed else "❌ FAIL"
        print(f"\n{status}")
        print(f"Answer: {answer}")
        
        user_input = input("\nPress Enter to continue (or 'q' to quit): ")
        if user_input.lower() == 'q':
            break


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import os
    
    # Check if OpenAI key is set
    if not os.environ.get("OPENAI_API_KEY"):
        print("WARNING: OPENAI_API_KEY not set. RAG features will not work.")
        print()
    
    if len(sys.argv) > 1 and sys.argv[1] == "interactive":
        interactive_test()
    else:
        success = run_all_tests()
        sys.exit(0 if success else 1)