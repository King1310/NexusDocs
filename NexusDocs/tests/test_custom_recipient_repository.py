import sqlite3

import pytest

from database.repositories.custom_recipient_repository import (
    CustomRecipientRepository,
)
from domain.entities.custom_recipient import CustomRecipient


def _recipient(
    *,
    template_slug: str = "military_unit",
    lookup_name: str = "425 ВКГ",
    recipient: str = "Командиру 425 военного клинического госпиталя",
    phones: tuple[str, ...] = (
        "+7 (000) 111-22-33",
        "+7 (000) 444-55-66",
    ),
) -> CustomRecipient:
    return CustomRecipient(
        id=None,
        template_slug=template_slug,
        lookup_name=lookup_name,
        recipient=recipient,
        postal_address="123456, г. Москва, ул. Примерная, д. 1",
        phones=phones,
        email="hospital@example.test",
        source_url="https://example.test/hospital",
        verification_status="user_verified",
        verified_at="2026-09-21",
        verification_note="Проверено вручную.",
    )


def test_save_and_get_preserve_all_recipient_fields(tmp_path):
    repository = CustomRecipientRepository(tmp_path / "organizations.db")

    recipient_id = repository.save(_recipient())
    stored = repository.get(recipient_id)

    assert stored is not None
    assert stored.id == recipient_id
    assert stored.lookup_name == "425 ВКГ"
    assert stored.phones == (
        "+7 (000) 111-22-33",
        "+7 (000) 444-55-66",
    )
    assert stored.email == "hospital@example.test"
    assert stored.source_url == "https://example.test/hospital"
    assert stored.verification_status == "user_verified"
    assert stored.verified_at == "2026-09-21"
    assert stored.verification_note == "Проверено вручную."


def test_directory_is_scoped_by_template_slug(tmp_path):
    repository = CustomRecipientRepository(tmp_path / "organizations.db")
    repository.save(_recipient(template_slug="military_unit"))
    repository.save(_recipient(template_slug="hospital"))

    assert len(repository.list("military_unit")) == 1
    assert len(repository.list("hospital")) == 1
    assert repository.list("zags") == []


def test_search_normalizes_case_yo_and_punctuation(tmp_path):
    repository = CustomRecipientRepository(tmp_path / "organizations.db")
    repository.save(
        _recipient(
            lookup_name="Межрайонная больница «Берёзка», № 2",
        )
    )
    repository.save(_recipient(lookup_name="425 ВКГ"))

    result = repository.search(
        "military_unit",
        "  БЕРЕЗКА-2 ",
    )

    assert [item.lookup_name for item in result] == [
        "Межрайонная больница «Берёзка», № 2"
    ]


def test_upsert_updates_same_normalized_name_without_duplicate(tmp_path):
    repository = CustomRecipientRepository(tmp_path / "organizations.db")
    first_id = repository.upsert(_recipient(lookup_name="425 ВКГ"))

    replacement = _recipient(
        lookup_name="  425-вкг ",
        recipient="Новый адресат",
        phones=("+7 (000) 999-88-77",),
    )
    second_id = repository.upsert(replacement)

    assert second_id == first_id
    assert len(repository.list("military_unit")) == 1
    stored = repository.get(first_id)
    assert stored is not None
    assert stored.lookup_name == "425-вкг"
    assert stored.recipient == "Новый адресат"
    assert stored.phones == ("+7 (000) 999-88-77",)


def test_same_lookup_name_can_exist_in_different_categories(tmp_path):
    repository = CustomRecipientRepository(tmp_path / "organizations.db")

    first_id = repository.save(_recipient(template_slug="hospital"))
    second_id = repository.save(_recipient(template_slug="military_unit"))

    assert first_id != second_id


def test_save_rejects_duplicate_normalized_name_in_same_category(tmp_path):
    repository = CustomRecipientRepository(tmp_path / "organizations.db")
    repository.save(_recipient(lookup_name="425 ВКГ"))

    with pytest.raises(sqlite3.IntegrityError):
        repository.save(_recipient(lookup_name="425-вкг"))


def test_custom_recipient_rejects_more_than_two_phones():
    with pytest.raises(ValueError, match="не более двух"):
        _recipient(phones=("1", "2", "3"))


def test_custom_directory_does_not_create_territory_links(tmp_path):
    repository = CustomRecipientRepository(tmp_path / "organizations.db")
    repository.save(_recipient())

    links = repository.db.fetch_all("SELECT * FROM territory_organizations")
    territorial = repository.db.fetch_all("SELECT * FROM organizations")

    assert links == []
    assert territorial == []
