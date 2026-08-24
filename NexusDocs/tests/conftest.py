import pytest

import database.db as database_module
import tests.test_database as test_database_module
from database.db import Database
from database.organizations_db import OrganizationsDatabase


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    """Не позволять тестам читать или удалять рабочую базу приложения."""

    Database.close()
    database_file = tmp_path / "nexusdocs-test.db"

    monkeypatch.setattr(
        database_module,
        "DATABASE_FILE",
        database_file,
    )
    monkeypatch.setattr(
        test_database_module,
        "DATABASE_FILE",
        database_file,
    )

    yield database_file

    Database.close()
    OrganizationsDatabase.close()
