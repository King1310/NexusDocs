from __future__ import annotations

from dataclasses import dataclass
import re

from database.repositories.territory_repository import TerritoryRepository
from domain.entities.organization import Organization
from domain.enums.organization_type import OrganizationType
from domain.value_objects.address import Address


@dataclass(slots=True, frozen=True)
class HeaderResolution:
    organizations: tuple[Organization, ...]
    missing_types: tuple[OrganizationType, ...]

    @property
    def is_complete(self) -> bool:
        return not self.missing_types

    @property
    def unverified_organizations(self) -> tuple[Organization, ...]:
        trusted_statuses = {
            "official",
            "verified",
            "user_verified",
            "auto_found",
        }
        return tuple(
            organization
            for organization in self.organizations
            if organization.verification_status not in trusted_statuses
            or (
                organization.verification_status == "auto_found"
                and not self._auto_found_is_protocol_complete(organization)
            )
        )

    @staticmethod
    def _auto_found_is_protocol_complete(organization: Organization) -> bool:
        if not re.search(r"(?<!\d)\d{6}(?!\d)", organization.postal_address):
            return False
        if not organization.phones:
            return False
        email_optional = {
            OrganizationType.MILITARY_COMMISSARIAT,
            OrganizationType.MILITARY_COMMANDANT,
            OrganizationType.CONTRACT_SERVICE_POINT,
        }
        if organization.organization_type not in email_optional and not organization.email:
            return False
        return True

    @property
    def is_ready_for_generation(self) -> bool:
        return self.is_complete and not self.unverified_organizations


class TerritoryService:
    """Подбирает девять шапок в фиксированном бизнес-порядке."""

    def __init__(self, repository: TerritoryRepository):
        self.repository = repository

    def resolve_headers(self, address: Address) -> HeaderResolution:
        resolved = self.repository.resolve(address)
        organizations = tuple(
            resolved[organization_type]
            for organization_type in OrganizationType
            if organization_type in resolved
        )
        missing_types = tuple(
            organization_type
            for organization_type in OrganizationType
            if organization_type not in resolved
        )
        return HeaderResolution(organizations, missing_types)
