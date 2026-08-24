from pathlib import Path
import sqlite3


ORGANIZATIONS_DATABASE_FILE = (
    Path(__file__).resolve().parent / "organizations.db"
)


class OrganizationsDatabase:
    """Отдельное соединение для территорий и адресатов."""

    _connections: dict[Path, sqlite3.Connection] = {}

    @classmethod
    def connection(
        cls,
        database_file: Path | None = None,
    ) -> sqlite3.Connection:
        path = (database_file or ORGANIZATIONS_DATABASE_FILE).resolve()

        if path not in cls._connections:
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            cls._connections[path] = connection

        return cls._connections[path]

    @classmethod
    def close(cls, database_file: Path | None = None) -> None:
        if database_file is None:
            for connection in cls._connections.values():
                connection.close()
            cls._connections.clear()
            return

        path = database_file.resolve()
        connection = cls._connections.pop(path, None)
        if connection is not None:
            connection.close()
