from database.repositories.person_repository import PersonRepository
from domain.value_objects.fullname import FullName
from services.person_service import PersonService
from ui.form_data import PersonFormData

from tests.factories.person_factory import PersonFactory
from tests.test_database import reset_database


def test_save_and_load_person():
    """
    Проверяет полный цикл:
    Person -> SQLite -> Person
    """

    reset_database()

    repo = PersonRepository()

    person = PersonFactory.create()

    repo.save(person)

    loaded = repo.get_by_id(person.id)

    assert loaded is not None
    assert loaded == person


def test_repository_crud_and_search():
    reset_database()
    repo = PersonRepository()

    first = PersonFactory.create(person_id=1)
    second = PersonFactory.create(person_id=2)
    second = replace(
        second,
        full_name=FullName(
            last_name="Петров",
            first_name="Пётр",
            middle_name="Петрович",
        ),
    )

    repo.save(first)
    repo.save(second)

    assert repo.count() == 2
    assert repo.get_next_id() == 3
    assert [person.id for person in repo.get_all()] == [1, 2]
    assert [person.id for person in repo.search_by_last_name("Петр")] == [2]

    edited_form = PersonFormData.from_person(first)
    edited_form.full_name = FullName(
        last_name="Сидоров",
        first_name="Сидор",
        middle_name="Сидорович",
    )
    updated = PersonService(repo).update(1, edited_form)

    assert repo.get_by_id(1) == updated

    repo.delete(2)

    assert repo.count() == 1
    assert repo.get_by_id(2) is None
from dataclasses import replace
