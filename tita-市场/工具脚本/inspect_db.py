
import sqlite3

DB_FILE = 'tita_logs.db'

def inspect_schema():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("select sql from sqlite_master where type='table' and name='daily_logs'")
    result = c.fetchone()
    if result:
        print(result[0])
    else:
        print("Table daily_logs not found.")
    conn.close()

if __name__ == "__main__":
    inspect_schema()
