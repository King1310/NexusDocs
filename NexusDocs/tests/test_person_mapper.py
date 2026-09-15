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


def test_person_mapper_loads_legacy_record_without_extension_fields():
    person = PersonFactory.create()
    record = PersonMapper.to_record(person)
    for field in (
        "military_deployment",
        "service_basis",
        "registration_date",
        "circumstances",
    ):
        record.pop(field)

    restored = PersonMapper.from_record(record)

    assert restored.military.military_deployment == ""
    assert restored.military.service_basis == ""
    assert restored.soch_case.registration_date is None
    assert restored.soch_case.circumstances == ""
