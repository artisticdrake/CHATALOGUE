# Add this debug version to test - save as debug_query.py

from semantic_parser import build_semantic_parse
from db_layer import run_semantic_db_layer
import json

# Test query
query = " What classes meet on MWF?" 
print("="*80)
print(f"DEBUG: {query}")
print("="*80)

# Step 1: Semantic parse
semantic = build_semantic_parse(query)
print("\n1. SEMANTIC PARSE OUTPUT:")
print(json.dumps(semantic, indent=2, default=str))

# Step 2: DB query
db_result = run_semantic_db_layer(semantic)
print("\n2. DB LAYER OUTPUT:")
print(json.dumps(db_result, indent=2, default=str))

# Step 3: Show what rows were returned
print("\n3. ROWS RETURNED:")
for i, sub in enumerate(db_result.get('subresults', [])):
    print(f"\nSubquery {i}:")
    print(f"  Intent: {sub.get('intent')}")
    print(f"  Course code used: {sub.get('course_code_used')}")
    print(f"  Instructor used: {sub.get('instructor_used')}")
    print(f"  Number of rows: {len(sub.get('rows', []))}")
    
    rows = sub.get('rows', [])
    if rows:
        print(f"  Rows:")
        for row in rows:
            print(f"    - {row.get('course_number')} {row.get('section')}: Instructor {row.get('instructor')}")
    else:
        print("  No rows returned!")

# Step 4: Check database directly
print("\n4. DIRECT DATABASE CHECK:")
import sqlite3
conn = sqlite3.connect('courses_metcs.sqlite')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Query all MA 226 sections
cur.execute("SELECT course_number, section, instructor FROM public_classes WHERE course_number LIKE '%MA 226%' ORDER BY section")
all_rows = cur.fetchall()
print(f"  Total MA 226 sections in DB: {len(all_rows)}")
print(f"  Instructors:")
instructors = {}
for row in all_rows:
    instr = row['instructor']
    if instr not in instructors:
        instructors[instr] = 0
    instructors[instr] += 1

for instr, count in instructors.items():
    print(f"    - {instr}: {count} sections")

conn.close()

print("\n" + "="*80)
print("DIAGNOSIS:")
print("Compare 'Number of rows' in step 3 with 'Total MA 226 sections' in step 4")
print("They should match (18 rows expected)")
print("="*80)
