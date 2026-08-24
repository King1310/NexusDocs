from domain.entities.person import Person
from mappers.person_mapper import PersonMapper

from database.repositories.base_repository import BaseRepository


class PersonRepository(BaseRepository):
    """
    Репозиторий Person.
    """

    TABLE_NAME = "persons"

    def exists(
        self,
        person_id: int,
    ) -> bool:
        row = self.db.fetch_one(
            f"""
            SELECT id
            FROM {self.TABLE_NAME}
            WHERE id = ?
            """,
            (person_id,),
        )

        return row is not None

    def get_all(self) -> list[Person]:
        """
        Получить всех людей из базы.
        """

        rows = self.db.fetch_all(
            f"""
            SELECT *
            FROM {self.TABLE_NAME}
            ORDER BY last_name, first_name, middle_name
            """
        )

        return [
            PersonMapper.from_record(
                dict(row)
            )
            for row in rows
        ]

    def search_by_last_name(
        self,
        last_name: str,
    ) -> list[Person]:
        """
        Найти людей по фамилии.
        """

        rows = self.db.fetch_all(
            f"""
            SELECT *
            FROM {self.TABLE_NAME}
            WHERE last_name LIKE ?
            ORDER BY last_name, first_name, middle_name
            """,
            (f"%{last_name}%",),
        )

        return [
            PersonMapper.from_record(
                dict(row)
            )
            for row in rows
        ]

    def save(
        self,
        person: Person,
    ) -> None:
        """
        Сохранить нового человека.
        """

        data = PersonMapper.to_record(
            person
        )

        columns = ", ".join(
            data.keys()
        )

        placeholders = ", ".join(
            f":{key}"
            for key in data.keys()
        )

        self.db.execute(
            f"""
            INSERT INTO {self.TABLE_NAME}
            ({columns})
            VALUES
            ({placeholders})
            """,
            data,
        )

    def update(
        self,
        person: Person,
    ) -> None:
        """
        Обновить существующего человека.
        """

        data = PersonMapper.to_record(
            person
        )

        person_id = data.pop(
            "id"
        )

        assignments = ", ".join(
            f"{key} = :{key}"
            for key in data.keys()
        )

        data["id"] = person_id

        self.db.execute(
            f"""
            UPDATE {self.TABLE_NAME}
            SET {assignments}
            WHERE id = :id
            """,
            data,
        )

    def get_by_id(
        self,
        person_id: int,
    ) -> Person | None:
        """
        Получить человека по ID.
        """

        row = self.db.fetch_one(
            f"""
            SELECT *
            FROM {self.TABLE_NAME}
            WHERE id = ?
            """,
            (person_id,),
        )

        if row is None:
            return None

        return PersonMapper.from_record(
            dict(row)
        )

    def delete(
        self,
        person_id: int,
    ) -> None:
        """
        Удалить человека.
        """

        self.db.execute(
            f"""
            DELETE
            FROM {self.TABLE_NAME}
            WHERE id = ?
            """,
            (person_id,),
        )
