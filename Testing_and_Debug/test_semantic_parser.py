# test_semantic_parser.py
# ============================================================
# Test harness for the new semantic parser
# ============================================================

from semantic_parser import (
    load_course_index,
    parse_semantic
)

from intent_classifier import get_intent_classifier

course_index = load_course_index("courses_metcs.sqlite")
clf = get_intent_classifier()

def test_query(q: str):
    print("------------------------------------------------------------")
    print("You:", q)

    # 1) Intent from ML layer
    intent_result = clf.classify_intent(q)

    primary_intent = intent_result["primary_intent"]
    primary_conf = intent_result["confidence"]

    # 2) Semantic parse
    parse = parse_semantic(
        user_text=q,
        primary_intent=primary_intent,
        primary_confidence=primary_conf,
        course_index=course_index
    )

    print("\n[INTENT RESULT]")
    print(intent_result)

    print("\n[SEMANTIC PARSE]")
    print(parse)

    print("------------------------------------------------------------\n")


if __name__ == "__main__":
    while True:
        msg = input("You: ")
        if msg.strip().lower() in ["quit", "exit"]:
            break
        test_query(msg)

