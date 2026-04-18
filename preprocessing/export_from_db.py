import sqlite3
import pandas as pd
import os


def export_from_db(db_path='../data_collection/database.db'):
    os.makedirs('csv_data', exist_ok=True)

    conn = sqlite3.connect(db_path)
    events_df = pd.read_sql_query("""
        SELECT id, title, category, text, source_id, url, parsed_at
        FROM events
    """, conn)
    events_df.to_csv('csv_data/events.csv', index=False)
    print(f"Экспортировано событий: {len(events_df)}")

    comments_df = pd.read_sql_query("""
        SELECT id, event_id, text, author, date
        FROM comments
    """, conn)
    comments_df.to_csv('csv_data/comments.csv', index=False)
    print(f"Экспортировано комментариев: {len(comments_df)}")

    sources_df = pd.read_sql_query("SELECT * FROM sources", conn)
    sources_df.to_csv('csv_data/sources.csv', index=False)
    print(f"Экспортировано источников: {len(sources_df)}")
    conn.close()
    return events_df, comments_df


if __name__ == "__main__":
    export_from_db()