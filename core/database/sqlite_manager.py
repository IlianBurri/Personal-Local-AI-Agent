import sqlite3
from pathlib import Path


class SQLiteManager:

    def __init__(self, db_path=None):

        if db_path is None:

            data_dir = Path.home() / ".config" / "arca"
            data_dir.mkdir(
                parents=True,
                exist_ok=True
            )

            db_path = data_dir / "arca.db"

        self.db_path = str(db_path)

        self.conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False
        )

        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

        self.create_tables()

    def create_tables(self):

        cursor = self.conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(chat_id)
            REFERENCES chats(id)
            ON DELETE CASCADE
        )
        """)

        self.conn.commit()

    # ------------------------
    # Chats
    # ------------------------

    def create_chat(
        self,
        title="New Chat"
    ):

        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO chats(title)
            VALUES(?)
            """,
            (title,)
        )

        self.conn.commit()

        return cursor.lastrowid

    def get_chats(self):

        cursor = self.conn.cursor()

        cursor.execute("""
        SELECT *
        FROM chats
        ORDER BY id DESC
        """)

        return [
            dict(row)
            for row in cursor.fetchall()
        ]

    def delete_chat(
        self,
        chat_id
    ):

        cursor = self.conn.cursor()

        cursor.execute(
            """
            DELETE FROM chats
            WHERE id = ?
            """,
            (chat_id,)
        )

        self.conn.commit()

    def rename_chat(
        self,
        chat_id,
        title
    ):

        cursor = self.conn.cursor()

        cursor.execute(
            """
            UPDATE chats
            SET title = ?
            WHERE id = ?
            """,
            (
                title,
                chat_id
            )
        )

        self.conn.commit()

    # ------------------------
    # Messages
    # ------------------------

    def add_message(
        self,
        chat_id,
        role,
        content
    ):

        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO messages(
                chat_id,
                role,
                content
            )
            VALUES(?,?,?)
            """,
            (
                chat_id,
                role,
                content
            )
        )

        self.conn.commit()

    def get_messages(
        self,
        chat_id
    ):

        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT *
            FROM messages
            WHERE chat_id = ?
            ORDER BY id ASC
            """,
            (chat_id,)
        )

        return [
            dict(row)
            for row in cursor.fetchall()
        ]

    def close(self):
        self.conn.close()
