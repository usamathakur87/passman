import sqlite3

def create_connection():
    try:
        conn = sqlite3.connect("password_manager.db")
        conn.execute("PRAGMA foreign_keys = 1;")
        return conn
    except sqlite3.Error as e:
        print(f"Error creating DB connection: {e}")
    return None

def create_tables():
    conn = create_connection()
    if not conn:
        return
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS suppliers (
        supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_name TEXT NOT NULL,
        office_id TEXT,
        user_id TEXT,
        password TEXT NOT NULL,
        url TEXT,
        date_created TEXT DEFAULT CURRENT_TIMESTAMP,
        last_reset TEXT,
        owner_user_id INTEGER NOT NULL,
        FOREIGN KEY (owner_user_id) REFERENCES users(user_id)
    );
    """)

    conn.commit()
    conn.close()
