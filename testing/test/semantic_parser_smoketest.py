# semantic_parser_smoketest.py
# Quick stress test for build_semantic_parse()

from semantic_parser import build_semantic_parse

def summarize(parsed):
    return {
        "primary_intent": str(parsed.get("primary_intent")),
        "primary_conf": round(float(parsed.get("primary_confidence", 0)), 3),
        "is_multi_query": parsed.get("is_multi_query"),
        "course_codes": parsed.get("course_codes"),
        "instructor_names": parsed.get("instructor_names"),
        "weekdays": parsed.get("weekdays"),
        "requested_attributes": parsed.get("requested_attributes"),
        "subqueries": [
            {
                "intent": str(sq.get("intent")),
                "conf": round(float(sq.get("confidence", 0)), 3),
                "text": sq.get("text"),
                "course_codes": sq.get("course_codes"),
                "instructor_names": sq.get("instructor_names"),
                "weekdays": sq.get("weekdays"),
                "attrs": sq.get("requested_attributes"),
                "multi_course": sq.get("multi_course"),
            }
            for sq in parsed.get("subqueries", [])
        ],
    }

TEST_QUERIES = [
    # ---------- instructor_lookup ----------
    "who teaches cs 575",
    "who teaches cs575",
    "who teaches met cs 575",
    "who teaches cs 535",
    "who is the instructor for met cs 579",
    "who is my professor for cs 232",
    "who teaches cas ma 226",
    "who teaches ma 226",
    "who teaches ma226",
    "who teaches differential equations",
    "who teaches linear algebra",
    "who teaches programming with java",
    "who is teaching cs 232 this semester",
    "who teaches the evening cs 232 class",
    "who is the professor for operating systems",
    "who is the professor for met cs 575",
    "which instructor teaches cs 579",
    "which professor is assigned to cs 232",
    "who teaches the linear algebra c3 section",
    "who teaches section c3 of linear algebra",
    "what classes does goh teach",
    "what classes does shahossini teach",
    "what classes does nourai teach",
    "what classes does lee teach",
    "what classes does moore teach",
    "what classes does chung teach",
    "what does goh teach here",
    "what does shahossini teach here",
    "what does nourai teach here",
    "what does lee teach here",

    # multi-course instructor
    "who teaches cs 232 and cs 342",
    "who teaches cs232 and cs342",
    "who teaches cs 232, cs 342, and cs 579",
    "who teaches met cs 232 and met cs 342 at bu",
    "which professor teaches cs 232 and which teaches cs 342",

    # ---------- schedule_query (when) ----------
    "when does cs 575 meet",
    "when does met cs 575 meet",
    "what time does cs 575 meet",
    "what time does met cs 575 start",
    "what time is cs 575",
    "when is cs 535 class",
    "when is cs 579 class",
    "when is met cs 232 lecture",
    "when do we meet for cs 342",
    "what days and times does cs 575 meet",
    "what days and times does met cs 535 meet",
    "what days does ma 226 meet",
    "on which days does ma 226 meet",
    "when does differential equations meet",
    "when does linear algebra meet",
    "when is programming with java",
    "what time is data structures with java",
    "when is computer networks",
    "when is database management",
    "what day/time is differential equations c3",

    # schedule + weekday filters
    "what classes do I have on monday",
    "what classes do I have on tuesday",
    "what classes do I have on wednesday",
    "what classes do I have on thursday",
    "what classes do I have on friday",
    "what classes are on mon",
    "which classes are on wed",
    "show my thursday classes",
    "which classes meet on tuesday and thursday",
    "which classes meet on tuesday",
    "which classes meet on tr",
    "which classes meet on mwf",

    # ---------- location (where) ----------
    "where is cs 575 held",
    "where is cs 575 located",
    "where is met cs 575 located",
    "where is cs 575",
    "where is met cs 579",
    "where is met cs 535 class",
    "where is cs 232",
    "where does cs 575 meet",
    "in which room is differential equations",
    "where is linear algebra c3",
    "where is linear algebra held",
    "what building is cs 579 in",
    "what room is programming with java",
    "where is database management taught",
    "where is computer networks taught",

    # ---------- multi-intent combos ----------
    "who teaches cs 575 and when does it meet",
    "who teaches cs 575 and where is it located",
    "who teaches cs 575 and what time is it",
    "who teaches cs 232 and when is the class",
    "who teaches cs 232 and cs 342 and when do they meet",
    "what classes does goh teach and when are they",
    "what classes does moore teach and what days do they meet",
    "who teaches differential equations and when does it meet",
    "who teaches linear algebra and where is it held",
    "who teaches programming with java and when does it meet",

    # ---------- exam_query ----------
    "when is the final exam for cs 575",
    "when is the final exam for met cs 575",
    "when is the midterm for cs 575",
    "when is the exam for cs 575",
    "what time is the cs 575 final",
    "when is the differential equations final",
    "when is the linear algebra final",
    "when is the exam for cs 232",
    "when is the exam for cs 342",
    "when is the exam for cs 535",
    "when is the exam for database management",
    "when is the exam for computer architecture",
    "when is my next exam",
    "do I have any exams this week",
    "when is the cs final",

    # ---------- assignment_query ----------
    "what assignments do I have for cs 575",
    "what homework is due for cs 575",
    "what homework is due in cs 232",
    "what assignments are due this week",
    "which assignments are due before friday",
    "do I have any homework due tomorrow",
    "what is due tonight",
    "list all assignments for cs 575",
    "show me my upcoming assignments",
    "are there any projects for cs 575",

    # ---------- event_query ----------
    "what events are happening on campus today",
    "are there any cs events this week",
    "are there any compsci events on friday",
    "what events are scheduled for this weekend",
    "are there any club meetings tonight",
    "what academic events are there today",
    "list all events on friday",
    "are there any seminars this week",
    "is there a math lecture tomorrow",
    "is there a cs talk today",

    # ---------- alert_query ----------
    "show me the latest campus alerts",
    "show me the latest safety alerts",
    "have there been any police alerts today",
    "have there been any alerts this week",
    "are there any emergency alerts right now",
    "any crime alerts near campus",
    "any security alerts near bu",
    "what is the latest bu police alert",
    "were there any alerts last night",
    "show recent safety notifications",

    # ---------- weather ----------
    "how is the weather in boston",
    "what is the weather like today",
    "will it rain today",
    "do I need an umbrella",
    "is it going to snow tomorrow",
    "what is the forecast for this week",
    "what is the temperature outside",
    "will it be windy this afternoon",
    "is it going to be cold tonight",
    "what is the weather like on campus",

    # ---------- course_info ----------
    "what is cs 575 about",
    "what is met cs 575 about",
    "what is the cs 575 course about",
    "what do we learn in cs 575",
    "what is computer networks about",
    "what is cs 579 about",
    "tell me about database management",
    "tell me about programming with java",
    "tell me about data structures with java",
    "what is differential equations",
    "what is linear algebra",
    "what is computer architecture",
    "what topics are covered in cs 575",
    "what does cs 575 cover",
    "is cs 575 hard",

    # ---------- schedule_query with title-only ----------
    "when does computer networks meet",
    "when does database management meet",
    "when does programming with java meet",
    "when does data structures with java meet",
    "when does differential equations meet",
    "when does linear algebra meet",
    "what time is computer architecture",
    "what time is database management",
    "what time is programming with java",
    "what time is data structures with java",

    # ---------- instructor_lookup with title-only ----------
    "who teaches computer networks",
    "who teaches database management",
    "who teaches programming with java",
    "who teaches data structures with java",
    "who teaches differential equations",
    "who teaches linear algebra",
    "who teaches computer architecture",
    "who teaches the operating systems course",
    "who teaches the networking class",
    "who is the professor for database management",

    # ---------- chitchat ----------
    "hi",
    "hello",
    "hey",
    "yo",
    "sup",
    "good morning",
    "good evening",
    "how are you",
    "thanks",
    "thank you",
    "you are awesome",
    "you are very helpful",
    "lol",
    "lmao",
    "i am bored",
    "talk to me",
    "tell me something interesting",
    "just testing you",
    "ok bye",

    # ---------- tricky / edge mixtures ----------
    "can you tell me who teaches cs 575 and if it's a hard course",
    "can you tell me when cs 575 meets and what room it is in",
    "i forgot who teaches cs 575 and when the class starts",
    "what day is cs 575 and who is the professor",
    "which days does cs 575 meet and where is it",
    "what does goh teach and when does it meet",
    "show me all classes taught by goh and what days they meet",
    "what classes does shahossini teach and what time are they",
    "who teaches cs 232 and cs 342 and where do they meet",
    "when is my next class with goh",
    "when is my next cs class",
    "where is my next class",
    "where is my cs class today",
    "what classes do I have today",
    "what classes do I have tomorrow",
    "who is my professor for my first class tomorrow",
    "what is the room for my earliest class tomorrow",
    "which classes meet in cas 320",
    "which classes meet in cas 229",
    "which classes meet in cas 116",
]

def short(q): return q[:60] + ("..." if len(q) > 60 else "")

def main():
    print("\n" + "="*110)
    print(f"{'QUERY':50} | {'INTENT':15} | {'ATTRS':20} | {'SUBQUERIES'}")
    print("="*110)

    for q in TEST_QUERIES:
        parsed = build_semantic_parse(q)

        primary_intent = str(parsed["primary_intent"])
        attrs = parsed["requested_attributes"]

        # build small summaries per subquery
        subs = []
        for sq in parsed["subqueries"]:
            subs.append({
                "intent": str(sq["intent"]),
                "attrs": sq["requested_attributes"],
                "course_codes": sq["course_codes"],
                "instructors": sq["instructor_names"],
                "weekdays": sq["weekdays"],
                "multi_course": sq["multi_course"],
            })

        print(f"{short(q):50} | {primary_intent:15} | {str(attrs):20} | {subs}")

    print("="*110)

if __name__ == "__main__":
    main()