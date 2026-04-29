import sqlite3

def run_query(sql):
    conn = sqlite3.connect("sales.db")
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()
    cursor.execute(sql)

    rows = cursor.fetchall()

    result = [dict(row) for row in rows]

    conn.close()

    return result