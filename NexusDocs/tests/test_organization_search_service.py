from types import SimpleNamespace

from domain.enums.organization_type import OrganizationType
from domain.value_objects.address import Address
from services.organization_search_service import (
    OrganizationCandidate,
    OrganizationSearchResponse,
    OrganizationSearchService,
)


class FakeResponses:
    def __init__(self, parsed):
        self.parsed = parsed
        self.arguments = None

    def parse(self, **kwargs):
        self.arguments = kwargs
        return SimpleNamespace(output_parsed=self.parsed)


def test_web_search_returns_unverified_candidates_in_requested_order():
    parsed = OrganizationSearchResponse(
        organizations=[
            OrganizationCandidate(
                organization_type=OrganizationType.HOSPITAL,
                recipient="Главному врачу тестовой больницы",
                postal_address="140100, Московская область",
                phones=["+7 (496) 000-00-00"],
                source_url="https://official.example.test/hospital",
                verification_note="Адрес и телефон подтверждены.",
            ),
            OrganizationCandidate(
                organization_type=OrganizationType.MILITARY_COMMISSARIAT,
                recipient="Военному комиссару",
                postal_address="140100, Московская область",
                source_url="https://official.example.test/voenkomat",
            ),
        ]
    )
    responses = FakeResponses(parsed)
    client = SimpleNamespace(responses=responses)
    service = OrganizationSearchService(client=client)

    result = service.search(
        Address(
            region="Московская область",
            district="Раменский район",
            city="",
            locality="п. Электроизолятор",
            street="",
            house="24",
            apartment="31",
        ),
        (
            OrganizationType.MILITARY_COMMISSARIAT,
            OrganizationType.HOSPITAL,
        ),
    )

    assert [item.organization_type for item in result] == [
        OrganizationType.MILITARY_COMMISSARIAT,
        OrganizationType.HOSPITAL,
    ]
    assert all(item.verification_status == "unverified" for item in result)
    assert result[1].verification_note == "Адрес и телефон подтверждены."
    assert responses.arguments["tools"] == [{"type": "web_search"}]
    assert responses.arguments["text_format"] is OrganizationSearchResponse


def test_web_search_requires_api_key_without_injected_client():
    service = OrganizationSearchService(api_key="")

    try:
        service.search(
            Address("Регион", "", "", "", "", "1"),
            (OrganizationType.TFOMS,),
        )
    except ValueError as error:
        assert "API-ключ" in str(error)
    else:
        raise AssertionError("Поиск должен требовать API-ключ")
