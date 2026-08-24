from database.db import Database
from database.db import DATABASE_FILE
from database.schema import create_tables


def reset_database() -> None:
    """
    Полностью пересоздать тестовую базу данных.
    """

    Database.close()

    if DATABASE_FILE.exists():
        DATABASE_FILE.unlink()

    create_tables()