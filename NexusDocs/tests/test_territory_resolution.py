from domain.entities.organization import Organization
from domain.entities.territory import Territory
from domain.enums.organization_type import OrganizationType
from domain.value_objects.address import Address
from database.repositories.territory_repository import TerritoryRepository
from services.territory_service import TerritoryService


def _organization(
    organization_type: OrganizationType,
    recipient: str,
) -> Organization:
    return Organization(
        id=None,
        organization_type=organization_type,
        recipient=recipient,
        postal_address="140100, Московская область, г. Раменское",
        phones=("+7 (496) 000-00-00",),
        email="example@example.ru",
        source_url="https://example.test/source",
        verification_status="test",
    )


def test_resolution_prefers_the_most_specific_territory(tmp_path):
    repository = TerritoryRepository(tmp_path / "organizations.db")

    region_id = repository.save_territory(
        Territory(id=None, region="Московская область")
    )
    district_id = repository.save_territory(
        Territory(
            id=None,
            region="Московская обл.",
            district="Раменский муниципальный округ",
        )
    )

    regional = _organization(
        OrganizationType.MILITARY_COMMISSARIAT,
        "Региональный адресат",
    )
    local = _organization(
        OrganizationType.MILITARY_COMMISSARIAT,
        "Местный адресат",
    )
    hospital = _organization(
        OrganizationType.HOSPITAL,
        "Главному врачу местной больницы",
    )

    repository.bind(
        region_id,
        regional.organization_type,
        repository.save_organization(regional),
    )
    repository.bind(
        district_id,
        local.organization_type,
        repository.save_organization(local),
    )
    repository.bind(
        district_id,
        hospital.organization_type,
        repository.save_organization(hospital),
    )

    result = TerritoryService(repository).resolve_headers(
        Address(
            region="Московская область",
            district="Раменский район",
            city="",
            locality="п. Электроизолятор",
            street="",
            house="24",
            apartment="31",
        )
    )

    assert result.organizations[0].recipient == "Местный адресат"
    assert result.organizations[1].organization_type is OrganizationType.HOSPITAL
    assert len(result.missing_types) == 7
    assert not result.is_complete
    assert not result.is_ready_for_generation


def test_header_uses_required_contact_labels():
    organization = _organization(
        OrganizationType.MILITARY_COMMANDANT,
        "Военному коменданту\nВоенной комендатуры Подольского гарнизона",
    )

    assert organization.header == (
        "Военному коменданту\n"
        "Военной комендатуры Подольского гарнизона\n\n"
        "140100, Московская область, г. Раменское\n\n"
        "тел.: +7 (496) 000-00-00\n\n"
        "эл. почта: example@example.ru"
    )


def test_header_set_can_be_loaded_and_updated(tmp_path):
    repository = TerritoryRepository(tmp_path / "organizations.db")
    territory = Territory(
        id=None,
        region="Московская область",
        district="Раменский муниципальный округ",
        locality="п. Электроизолятор",
    )
    original = Organization(
        id=None,
        organization_type=OrganizationType.MILITARY_COMMISSARIAT,
        recipient="Первоначальный адресат",
        postal_address="Первоначальный адрес",
        phones=("+7 (496) 000-00-00",),
        source_url="https://example.test/official",
        verification_status="official",
        verified_at="2026-08-16",
        verification_note="Подтверждено официальной страницей.",
    )

    repository.save_header_set(territory, [original])
    loaded = repository.get_bound_organizations(territory)

    assert loaded[OrganizationType.MILITARY_COMMISSARIAT].recipient == (
        "Первоначальный адресат"
    )
    assert loaded[OrganizationType.MILITARY_COMMISSARIAT].verified_at == (
        "2026-08-16"
    )
    assert loaded[OrganizationType.MILITARY_COMMISSARIAT].verification_note == (
        "Подтверждено официальной страницей."
    )

    updated = Organization(
        id=None,
        organization_type=OrganizationType.MILITARY_COMMISSARIAT,
        recipient="Исправленный адресат",
        postal_address="Исправленный адрес",
        verification_status="user_verified",
        verified_at="2026-08-17",
        verification_note="Проверено вручную.",
    )
    repository.save_header_set(territory, [updated])

    loaded = repository.get_bound_organizations(territory)
    organization = loaded[OrganizationType.MILITARY_COMMISSARIAT]
    assert organization.recipient == "Исправленный адресат"
    assert organization.verification_status == "user_verified"
    assert organization.verified_at == "2026-08-17"
    assert organization.verification_note == "Проверено вручную."
    assert len(repository.db.fetch_all("SELECT id FROM organizations")) == 1
