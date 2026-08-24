from database.database_manager import DatabaseManager


class BaseRepository:
    """
    Базовый класс всех Repository.
    """

    TABLE_NAME = ""

    def __init__(self):
        self.db = DatabaseManager()

    def exists(self, entity_id: int) -> bool:
        row = self.db.fetch_one(
            f"""
            SELECT id
            FROM {self.TABLE_NAME}
            WHERE id = ?
            """,
            (entity_id,),
        )

        return row is not None

    def delete(self, entity_id: int) -> None:
        self.db.execute(
            f"""
            DELETE
            FROM {self.TABLE_NAME}
            WHERE id = ?
            """,
            (entity_id,),
        )

    def count(self) -> int:
        row = self.db.fetch_one(
            f"""
            SELECT COUNT(*) AS total
            FROM {self.TABLE_NAME}
            """
        )

        return row["total"]

    def get_next_id(self) -> int:
        """Получить следующий свободный числовой идентификатор."""

        row = self.db.fetch_one(
            f"""
            SELECT COALESCE(MAX(id), 0) + 1 AS next_id
            FROM {self.TABLE_NAME}
            """
        )

        return row["next_id"]
