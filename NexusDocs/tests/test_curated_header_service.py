from domain.enums.organization_type import OrganizationType
from domain.value_objects.address import Address
from services.curated_header_service import CuratedHeaderService
from services.free_organization_search_service import FreeOrganizationSearchService


def test_ramensky_user_templates_return_nine_complete_headers():
    address = Address(
        region="Московская область",
        district="Раменский район",
        locality="п. Электроизолятор",
        city="",
        street="",
        house="24",
        apartment="31",
    )

    headers = CuratedHeaderService.resolve(address, tuple(OrganizationType))

    assert tuple(headers) == tuple(OrganizationType)
    assert all(item.postal_address[:6].isdigit() for item in headers.values())
    assert all(item.phones for item in headers.values())
    assert headers[OrganizationType.NARCOLOGY].recipient == (
        "Главному врачу\n"
        "ГБУЗ Московской области\n"
        "«Раменская больница»"
    )
    assert headers[OrganizationType.ADMINISTRATION].recipient == (
        "Главе\nРаменского муниципального округа"
    )
    assert headers[OrganizationType.TFOMS].postal_address == (
        "140000, Московская область, г. Люберцы, ул. Звуковая, д. 4"
    )
    assert headers[OrganizationType.ELECTION_COMMISSION].email == (
        "tikramenskoe@mail.ru"
    )


def test_free_search_uses_ramensky_templates_without_querying_the_web(monkeypatch):
    address = Address(
        region="Московская",
        district="Раменский",
        locality="Электроизолятор",
        city="",
        street="",
        house="24",
        apartment="31",
    )
    service = FreeOrganizationSearchService()

    def fail_if_called():
        raise AssertionError("Интернет не должен заменять утверждённый эталон")

    monkeypatch.setattr(service, "_default_backend", fail_if_called)
    outcome = service.search(address, tuple(OrganizationType))

    assert not outcome.unresolved_types
    assert len(outcome.organizations) == 9
    assert all(
        item.verification_status == "user_verified"
        for item in outcome.organizations
    )
