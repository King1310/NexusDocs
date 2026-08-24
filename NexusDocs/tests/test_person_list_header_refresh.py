from domain.entities.organization import Organization
from domain.enums.organization_type import OrganizationType
from services.territory_service import HeaderResolution
from ui.person.person_list_window import PersonListWindow


def _organization(organization_type: OrganizationType) -> Organization:
    return Organization(
        id=None,
        organization_type=organization_type,
        recipient=organization_type.value,
        postal_address="Адрес",
        source_url="https://example.test",
        verification_status="official",
    )


def test_force_refresh_searches_all_headers_even_when_cache_is_complete():
    resolution = HeaderResolution(
        organizations=tuple(_organization(item) for item in OrganizationType),
        missing_types=(),
    )

    assert PersonListWindow._header_search_targets(resolution) == []
    assert PersonListWindow._header_search_targets(
        resolution,
        force_refresh=True,
    ) == list(OrganizationType)


def test_regular_search_only_targets_missing_and_unverified_headers():
    official = _organization(OrganizationType.MILITARY_COMMISSARIAT)
    unverified = Organization(
        id=None,
        organization_type=OrganizationType.PSYCHIATRY,
        recipient="Психиатрия",
        postal_address="Адрес",
        verification_status="needs_review",
    )
    resolution = HeaderResolution(
        organizations=(official, unverified),
        missing_types=(OrganizationType.NARCOLOGY,),
    )

    assert PersonListWindow._header_search_targets(resolution) == [
        OrganizationType.NARCOLOGY,
        OrganizationType.PSYCHIATRY,
    ]
