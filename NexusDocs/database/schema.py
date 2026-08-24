from database.db import Database


def create_tables() -> None:
    """
    Создать все таблицы базы данных.
    """

    connection = Database.connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS persons
        (
            id INTEGER PRIMARY KEY,

            -- ФИО
            last_name TEXT NOT NULL,
            first_name TEXT NOT NULL,
            middle_name TEXT NOT NULL,

            -- Паспорт
            passport_series TEXT,
            passport_number TEXT,
            passport_issued_by TEXT,
            passport_issue_date TEXT,

            -- Рождение
            birth_date TEXT NOT NULL,

            birth_region TEXT,
            birth_district TEXT,
            birth_city TEXT,
            birth_locality TEXT,
            birth_street TEXT,
            birth_house TEXT,
            birth_apartment TEXT,

            -- Адрес регистрации
            registration_region TEXT,
            registration_district TEXT,
            registration_city TEXT,
            registration_locality TEXT,
            registration_street TEXT,
            registration_house TEXT,
            registration_apartment TEXT,

            -- Военные сведения
            military_unit TEXT NOT NULL,
            rank TEXT NOT NULL,
            position TEXT NOT NULL,
            military_id TEXT NOT NULL,

            -- Сведения о СОЧ
            soch_date TEXT NOT NULL,
            soch_place TEXT NOT NULL,
            duration TEXT NOT NULL,

            -- Тип дела: УД / МП
            case_type TEXT NOT NULL,

            -- Только для УД
            case_number TEXT,

            -- Процессуальный контроль
            procedural_control TEXT NOT NULL,

            -- Статья УК РФ
            article TEXT NOT NULL,

            -- Документ
            outgoing_number TEXT NOT NULL,
            outgoing_date TEXT NOT NULL,
            vpg INTEGER NOT NULL
        )
        """
    )

    connection.commit()