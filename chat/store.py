"""Conversation history in MariaDB (table viikko5chat.messages, see db/schema.sql)."""

import os

import pymysql


class StoreError(Exception):
    """Raised when the database cannot be read or written."""


class MariaDBStore:
    def __init__(self, host, user, password, database):
        self.host = host
        self.user = user
        self.password = password
        self.database = database

    @classmethod
    def from_env(cls):
        return cls(
            host=os.environ.get("DB_HOST", "localhost"),
            user=os.environ.get("DB_USER", ""),
            password=os.environ.get("DB_PASSWORD", ""),
            database=os.environ.get("DB_NAME", "viikko5chat"),
        )

    def _connect(self):
        return pymysql.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database,
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=5,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def get_messages(self, session_id, limit=200):
        """Return the newest `limit` messages of one session, oldest first."""
        sql = (
            "SELECT role, content FROM ("
            " SELECT id, role, content FROM messages"
            " WHERE session_id = %s ORDER BY id DESC LIMIT %s"
            ") AS latest ORDER BY id"
        )
        try:
            conn = self._connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(sql, (session_id, int(limit)))
                    rows = cur.fetchall()
            finally:
                conn.close()
        except pymysql.MySQLError as exc:
            raise StoreError(str(exc)) from exc
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def add_messages(self, session_id, messages):
        sql = "INSERT INTO messages (session_id, role, content) VALUES (%s, %s, %s)"
        rows = [(session_id, m["role"], m["content"]) for m in messages]
        try:
            conn = self._connect()
            try:
                with conn.cursor() as cur:
                    cur.executemany(sql, rows)
            finally:
                conn.close()
        except pymysql.MySQLError as exc:
            raise StoreError(str(exc)) from exc
