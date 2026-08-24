from urllib.parse import parse_qs, urlparse

from domain.enums.organization_type import OrganizationType
from domain.value_objects.address import Address
from services.browser_organization_search_service import (
    BrowserOrganizationSearchService,
)


def _address() -> Address:
    return Address(
        region="Московская область",
        district="Раменский округ",
        city="",
        locality="п. Электроизолятор",
        street="ул. Служебная",
        house="24",
        apartment="31",
    )


def test_search_never_sends_private_address_details():
    service = BrowserOrganizationSearchService()

    for organization_type in OrganizationType:
        query = service.query(_address(), organization_type)

        assert "Служебная" not in query
        assert "24" not in query
        assert "31" not in query


def test_search_urls_encode_the_same_query_for_both_engines():
    service = BrowserOrganizationSearchService()
    expected = service.query(_address(), OrganizationType.TFOMS)

    yandex = urlparse(
        service.url(_address(), OrganizationType.TFOMS, "yandex")
    )
    google = urlparse(
        service.url(_address(), OrganizationType.TFOMS, "google")
    )

    assert parse_qs(yandex.query)["text"] == [expected]
    assert parse_qs(google.query)["q"] == [expected]
