from pathlib import Path
import sqlite3

from database.organizations_db import OrganizationsDatabase


class OrganizationDatabaseManager:
    """SQL-операции над отдельной базой организаций."""

    def __init__(self, database_file: Path | None = None):
        self.connection = OrganizationsDatabase.connection(database_file)

    def execute(self, query: str, parameters=()) -> sqlite3.Cursor:
        cursor = self.connection.cursor()
        cursor.execute(query, parameters)
        self.connection.commit()
        return cursor

    def fetch_one(self, query: str, parameters=()) -> sqlite3.Row | None:
        cursor = self.connection.cursor()
        cursor.execute(query, parameters)
        return cursor.fetchone()

    def fetch_all(self, query: str, parameters=()) -> list[sqlite3.Row]:
        cursor = self.connection.cursor()
        cursor.execute(query, parameters)
        return cursor.fetchall()
