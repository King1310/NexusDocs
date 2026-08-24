import sqlite3

from database.db import Database


class DatabaseManager:
    """
    Высокоуровневая работа с SQLite.

    Repository никогда не работает с sqlite3 напрямую.
    """

    def __init__(self):
        self.connection = Database.connection()

    def execute(
        self,
        query: str,
        parameters=(),
    ) -> sqlite3.Cursor:

        cursor = self.connection.cursor()

        cursor.execute(query, parameters)

        self.connection.commit()

        return cursor

    def fetch_one(
        self,
        query: str,
        parameters=(),
    ) -> sqlite3.Row | None:

        cursor = self.connection.cursor()

        cursor.execute(query, parameters)

        return cursor.fetchone()

    def fetch_all(
        self,
        query: str,
        parameters=(),
    ) -> list[sqlite3.Row]:

        cursor = self.connection.cursor()

        cursor.execute(query, parameters)

        return cursor.fetchall()

    def last_insert_id(self) -> int:
        """
        ID последней добавленной записи.
        """

        cursor = self.connection.cursor()

        cursor.execute(
            "SELECT last_insert_rowid()"
        )

        return cursor.fetchone()[0]