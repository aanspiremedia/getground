import sqlite3
import os

db_path = 'sql_app.db'
if not os.path.exists(db_path):
    print(f"Error: {db_path} not found.")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # 1. Update ground_pricing
    cursor.execute("UPDATE ground_pricing SET category = UPPER(category)")
    print(f"Updated ground_pricing: {cursor.rowcount} rows")

    # 2. Update bookings
    cursor.execute("UPDATE bookings SET category = UPPER(category)")
    print(f"Updated bookings: {cursor.rowcount} rows")

    conn.commit()
    print("Successfully synchronized Enum values to uppercase.")
except Exception as e:
    print(f"Error: {e}")
    conn.rollback()
finally:
    conn.close()
