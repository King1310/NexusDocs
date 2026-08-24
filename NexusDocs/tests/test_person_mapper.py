from tests.factories.person_factory import PersonFactory

from mappers.person_mapper import PersonMapper


def test_person_mapper():
    """
    Проверяет преобразование Person
    в словарь и обратно.
    """

    person = PersonFactory.create()

    record = PersonMapper.to_record(person)

    restored = PersonMapper.from_record(record)

    assert restored == person