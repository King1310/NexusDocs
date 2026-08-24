from domain.entities.organization import Organization
from domain.enums.organization_type import OrganizationType
from services.territory_service import HeaderResolution


def _organization(
    organization_type: OrganizationType,
    *,
    postal_address: str = "140100, Московская область, г. Раменское, ул. Мира, д. 1",
    phones: tuple[str, ...] = ("+7 (496) 000-00-00",),
    email: str = "office@example.ru",
    recipient: str = "Главному врачу\nГБУЗ «Раменская больница»",
) -> Organization:
    return Organization(
        id=1,
        organization_type=organization_type,
        recipient=recipient,
        postal_address=postal_address,
        phones=phones,
        email=email,
        verification_status="auto_found",
    )


def test_incomplete_cached_auto_headers_are_searched_again():
    missing_index = _organization(
        OrganizationType.HOSPITAL,
        postal_address="Московская область, г. Раменское, ул. Мира, д. 1",
    )
    missing_phone = _organization(OrganizationType.TFOMS, phones=())
    missing_email = _organization(OrganizationType.ELECTION_COMMISSION, email="")
    resolution = HeaderResolution(
        (missing_index, missing_phone, missing_email),
        (),
    )

    assert resolution.unverified_organizations == resolution.organizations
    assert not resolution.is_ready_for_generation


def test_email_is_not_required_for_three_protocol_exceptions():
    organizations = tuple(
        _organization(organization_type, email="")
        for organization_type in (
            OrganizationType.MILITARY_COMMISSARIAT,
            OrganizationType.MILITARY_COMMANDANT,
            OrganizationType.CONTRACT_SERVICE_POINT,
        )
    )
    resolution = HeaderResolution(organizations, ())

    assert not resolution.unverified_organizations
    assert resolution.is_ready_for_generation


def test_administration_header_without_head_is_ready():
    administration = _organization(
        OrganizationType.ADMINISTRATION,
        recipient="Главе\nРаменского муниципального округа",
    )
    resolution = HeaderResolution((administration,), ())

    assert not resolution.unverified_organizations
