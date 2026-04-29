import sqlite3

def get_schema():
    conn = sqlite3.connect("sales.db")
    cursor = conn.cursor()

    # get all tables
    cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='table'
        AND name NOT LIKE 'sqlite_%'
    """)
    tables = [row[0] for row in cursor.fetchall()]

    schema = {}

    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = cursor.fetchall()

        schema[table] = [
            {
                "name": col[1],
                "type": col[2]
            }
            for col in cols
        ]

    conn.close()
    return schema