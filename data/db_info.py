import sqlite3, os, textwrap

def get_db_path():
    """Return absolute path to the SQLite DB file in the same folder."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "courses_metcs.sqlite") 
    #db_path = os.path.join(base_dir, "chatalogue.sqlite") # change name if needed
    return db_path

def print_table_data(cur, table, limit=1000):
    """Print table contents neatly."""
    cur.execute(f"SELECT * FROM {table} LIMIT {limit}")
    rows = cur.fetchall()
    if not rows:
        print("   (no data)\n")
        return
    col_names = [desc[0] for desc in cur.description]
    print("   Columns:", ", ".join(col_names))
    print("   Rows:")
    for row in rows:
        # Format long text columns neatly
        row_display = []
        for item in row:
            s = str(item)
            if len(s) > 60:
                s = s[:57] + "..."
            row_display.append(s)
        print("    •", " | ".join(row_display))
    if len(rows) == limit:
        print(f"   ... (showing first {limit} rows)")
    print()

def inspect_full(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    print(f"\n📂 Database: {db_path}\n")

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row[0] for row in cur.fetchall()]
    if not tables:
        print("❌ No user tables found.")
        return

    for table in tables:
        print(f"🧩 Table: {table}")
        cur.execute(f"PRAGMA table_info({table})")
        cols = cur.fetchall()
        for col in cols:
            cid, name, dtype, notnull, dflt, pk = col
            pk_tag = " [PK]" if pk else ""
            print(f"   - {name} ({dtype}){pk_tag}")
        print()
        print_table_data(cur, table)
        print("-" * 80)

    conn.close()

if __name__ == "__main__":
    db_path = get_db_path()
    if not os.path.exists(db_path):
        print("⚠️ No database file found at:", db_path)
    else:
        inspect_full(db_path)
