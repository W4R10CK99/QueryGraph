import sqlite3

# creates file sales.db automatically
conn = sqlite3.connect("database/sales.db")

cursor = conn.cursor()

# Create table
cursor.execute("""
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT,
    category TEXT,
    product TEXT,
    city TEXT,
    sales INTEGER,
    year INTEGER
)
""")

# Insert sample data
sample_data = [
    ("Jan", "electronics", "phone", "Delhi", 5000, 2025),
    ("Feb", "electronics", "laptop", "Delhi", 7200, 2025),
    ("Mar", "electronics", "tablet", "Mumbai", 4100, 2025),
    ("Jan", "clothing", "shirt", "Mumbai", 3000, 2025),
    ("Feb", "clothing", "jeans", "Delhi", 2800, 2025),
    ("Mar", "clothing", "jacket", "Delhi", 4500, 2025),
    ("Jan", "grocery", "rice", "Delhi", 2500, 2025),
    ("Feb", "grocery", "oil", "Mumbai", 3200, 2025),
    ("Mar", "grocery", "flour", "Delhi", 2900, 2025)
]

cursor.executemany("""
INSERT INTO sales (month, category, product, city, sales, year)
VALUES (?, ?, ?, ?, ?, ?)
""", sample_data)

conn.commit()
conn.close()

print("sales.db created successfully")