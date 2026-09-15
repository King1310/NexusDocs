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


def test_create_tables_adds_extension_columns_to_legacy_database(
    isolated_database,
):
    Database.close()
    isolated_database.unlink(missing_ok=True)

    connection = Database.connection()
    connection.execute("CREATE TABLE persons (id INTEGER PRIMARY KEY)")
    connection.commit()

    create_tables()

    columns = {
        row[1]
        for row in Database.connection().execute("PRAGMA table_info(persons)")
    }
    assert {
        "military_deployment",
        "service_basis",
        "registration_date",
        "circumstances",
    } <= columns
