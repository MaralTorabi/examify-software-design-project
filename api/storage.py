"""Local SQLite storage for the standalone sprint prototype.

Each exam is stored with its frozen question pool and answer history. Write
transactions serialize changes so a retried request cannot count twice.
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class PrototypeStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def transaction(self, *, write: bool = False):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            connection.row_factory = sqlite3.Row
            if write:
                connection.execute("BEGIN IMMEDIATE")
            with connection:
                yield connection
        finally:
            connection.close()

    def init_db(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS prototype_users (
                    id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS prototype_documents (
                    id TEXT PRIMARY KEY, data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS prototype_exams (
                    id TEXT PRIMARY KEY, data TEXT NOT NULL
                );
            """)

    def ready(self) -> bool:
        if not self.path.is_file():
            return False
        try:
            with self.transaction() as connection:
                connection.execute("SELECT 1 FROM prototype_users LIMIT 1")
        except sqlite3.Error:
            return False
        return True


def read_document(connection, document_id):
    row = connection.execute(
        "SELECT data FROM prototype_documents WHERE id = ?", (str(document_id),)
    ).fetchone()
    return json.loads(row["data"]) if row else None


def save_document(connection, document):
    connection.execute(
        """INSERT INTO prototype_documents(id, data) VALUES (?, ?)
           ON CONFLICT(id) DO UPDATE SET data = excluded.data""",
        (document["document_id"], json.dumps(document, ensure_ascii=False)),
    )


def read_exam(connection, session_id):
    row = connection.execute(
        "SELECT data FROM prototype_exams WHERE id = ?", (str(session_id),)
    ).fetchone()
    return json.loads(row["data"]) if row else None


def save_exam(connection, exam):
    connection.execute(
        """INSERT INTO prototype_exams(id, data) VALUES (?, ?)
           ON CONFLICT(id) DO UPDATE SET data = excluded.data""",
        (exam["session_id"], json.dumps(exam, ensure_ascii=False)),
    )
