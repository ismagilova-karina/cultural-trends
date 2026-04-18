import sqlite3
from contextlib import closing
from datetime import datetime

DB_NAME = "database.db"


def create_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables():
    with closing(create_connection()) as conn, conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            url TEXT
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            category TEXT,
            text TEXT,
            source_id INTEGER,
            topic TEXT,
            sentiment TEXT,
            url TEXT,
            parsed_at TEXT,
            FOREIGN KEY (source_id) REFERENCES sources(id)
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER,
            text TEXT,
            author TEXT,
            date TEXT,
            rating INTEGER,
            sentiment TEXT,
            topic TEXT,
            FOREIGN KEY (event_id) REFERENCES events(id)
        )
        """)

        # Добавляем колонку rating если её нет
        cursor.execute("PRAGMA table_info(comments)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'rating' not in columns:
            cursor.execute("ALTER TABLE comments ADD COLUMN rating INTEGER")


def add_source(name, url=None):
    with closing(create_connection()) as conn, conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO sources (name, url) VALUES (?, ?)", (name, url))
        return cursor.lastrowid


def add_event(title, category=None, text=None, source_id=None,
              date=None, topic=None, sentiment=None, url=None):
    parsed_at = datetime.now().isoformat()

    with closing(create_connection()) as conn, conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO events (
                title, 
                category, 
                text, 
                source_id, 
                topic, 
                sentiment, 
                url, 
                parsed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (title, category, text, source_id, topic, sentiment, url, parsed_at))
        return cursor.lastrowid


def add_comment(event_id, text, author=None, date=None, rating=None, sentiment=None, topic=None):
    with closing(create_connection()) as conn, conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO comments (event_id, text, author, date, rating, sentiment, topic)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (event_id, text, author, date, rating, sentiment, topic))
        return cursor.lastrowid

def get_events():
    with closing(create_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events")
        return cursor.fetchall()


def get_comments(event_id=None):
    with closing(create_connection()) as conn:
        cursor = conn.cursor()
        if event_id:
            cursor.execute("SELECT * FROM comments WHERE event_id=?", (event_id,))
        else:
            cursor.execute("SELECT * FROM comments")
        return cursor.fetchall()