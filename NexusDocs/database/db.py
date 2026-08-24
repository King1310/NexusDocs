from pathlib import Path
import sqlite3

# Корень проекта
ROOT_DIR = Path(__file__).resolve().parent.parent

# Папка базы данных
DATABASE_DIR = ROOT_DIR / "database"

# Файл базы
DATABASE_FILE = DATABASE_DIR / "nexusdocs.db"


class Database:
    """
    Единая точка подключения к SQLite.
    """

    _connection: sqlite3.Connection | None = None

    @classmethod
    def connection(cls) -> sqlite3.Connection:
        """
        Получить соединение с базой данных.
        """

        if cls._connection is None:
            DATABASE_DIR.mkdir(exist_ok=True)

            cls._connection = sqlite3.connect(DATABASE_FILE)

            cls._connection.row_factory = sqlite3.Row

            cls._connection.execute(
                "PRAGMA foreign_keys = ON;"
            )

        return cls._connection

    @classmethod
    def close(cls) -> None:
        """
        Закрыть соединение с базой данных.
        """

        if cls._connection is not None:
            cls._connection.close()
            cls._connection = None