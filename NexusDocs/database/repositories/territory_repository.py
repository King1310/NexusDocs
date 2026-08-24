from __future__ import annotations

import json
from pathlib import Path
import re

from database.organization_database_manager import OrganizationDatabaseManager
from database.organizations_schema import create_organizations_tables
from domain.entities.organization import Organization
from domain.entities.territory import Territory
from domain.enums.organization_type import OrganizationType
from domain.value_objects.address import Address


_LOCATION_WORDS = re.compile(
    r"\b(обл|область|р-н|район|муниципальный|городской|округ|"
    r"г|город|п|поселок|посёлок|с|село|д|деревня|ул|улица)\b"
)


def normalize_location(value: str) -> str:
    """Свести распространённые варианты записи территории к одному виду."""

    normalized = value.casefold().replace("ё", "е")
    normalized = re.sub(r"[.,()]", " ", normalized)
    normalized = _LOCATION_WORDS.sub(" ", normalized)
    return " ".join(normalized.split())


class TerritoryRepository:
    """Хранение территорий и привязанных к ним девяти адресатов."""

    def __init__(self, database_file: Path | None = None):
        create_organizations_tables(database_file)
        self.db = OrganizationDatabaseManager(database_file)

    def save_territory(self, territory: Territory) -> int:
        values = tuple(
            normalize_location(value)
            for value in (
                territory.region,
                territory.district,
                territory.city,
                territory.locality,
                territory.street,
            )
        )
        self.db.execute(
            """
            INSERT OR IGNORE INTO territories
            (region, district, city, locality, street)
            VALUES (?, ?, ?, ?, ?)
            """,
            values,
        )
        row = self.db.fetch_one(
            """
            SELECT id FROM territories
            WHERE region = ? AND district = ? AND city = ?
              AND locality = ? AND street = ?
            """,
            values,
        )
        return row["id"]

    def save_organization(self, organization: Organization) -> int:
        cursor = self.db.execute(
            """
            INSERT INTO organizations
            (
                organization_type, recipient, postal_address, phones,
                email, fax, source_url, verification_status, verified_at,
                verification_note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                organization.organization_type.name,
                organization.recipient,
                organization.postal_address,
                json.dumps(organization.phones, ensure_ascii=False),
                organization.email,
                organization.fax,
                organization.source_url,
                organization.verification_status,
                organization.verified_at,
                organization.verification_note,
            ),
        )
        return cursor.lastrowid

    def find_territory_id(self, territory: Territory) -> int | None:
        values = tuple(
            normalize_location(value)
            for value in (
                territory.region,
                territory.district,
                territory.city,
                territory.locality,
                territory.street,
            )
        )
        row = self.db.fetch_one(
            """
            SELECT id FROM territories
            WHERE region = ? AND district = ? AND city = ?
              AND locality = ? AND street = ?
            """,
            values,
        )
        return row["id"] if row is not None else None

    def get_bound_organizations(
        self,
        territory: Territory,
    ) -> dict[OrganizationType, Organization]:
        territory_id = self.find_territory_id(territory)
        if territory_id is None:
            return {}

        rows = self.db.fetch_all(
            """
            SELECT o.*
            FROM territory_organizations AS link
            JOIN organizations AS o ON o.id = link.organization_id
            WHERE link.territory_id = ?
            """,
            (territory_id,),
        )
        return {
            OrganizationType[row["organization_type"]]:
            self._organization_from_row(row)
            for row in rows
        }

    def save_header_set(
        self,
        territory: Territory,
        organizations: list[Organization],
    ) -> int:
        """Сохранить или обновить заполненные шапки одной территории."""

        territory_id = self.save_territory(territory)
        for organization in organizations:
            row = self.db.fetch_one(
                """
                SELECT organization_id
                FROM territory_organizations
                WHERE territory_id = ? AND organization_type = ?
                """,
                (territory_id, organization.organization_type.name),
            )
            if row is None:
                organization_id = self.save_organization(organization)
            else:
                organization_id = row["organization_id"]
                self.db.execute(
                    """
                    UPDATE organizations
                    SET recipient = ?, postal_address = ?, phones = ?,
                        email = ?, fax = ?, source_url = ?,
                        verification_status = ?, verified_at = ?,
                        verification_note = ?
                    WHERE id = ?
                    """,
                    (
                        organization.recipient,
                        organization.postal_address,
                        json.dumps(organization.phones, ensure_ascii=False),
                        organization.email,
                        organization.fax,
                        organization.source_url,
                        organization.verification_status,
                        organization.verified_at,
                        organization.verification_note,
                        organization_id,
                    ),
                )
            self.bind(
                territory_id,
                organization.organization_type,
                organization_id,
            )
        return territory_id

    def bind(
        self,
        territory_id: int,
        organization_type: OrganizationType,
        organization_id: int,
    ) -> None:
        self.db.execute(
            """
            INSERT INTO territory_organizations
            (territory_id, organization_type, organization_id)
            VALUES (?, ?, ?)
            ON CONFLICT(territory_id, organization_type)
            DO UPDATE SET organization_id = excluded.organization_id
            """,
            (territory_id, organization_type.name, organization_id),
        )

    def resolve(self, address: Address) -> dict[OrganizationType, Organization]:
        target = {
            "region": normalize_location(address.region),
            "district": normalize_location(address.district),
            "city": normalize_location(address.city),
            "locality": normalize_location(address.locality),
            "street": normalize_location(address.street),
        }
        rows = self.db.fetch_all(
            """
            SELECT
                t.region, t.district, t.city, t.locality, t.street,
                o.*
            FROM territory_organizations AS link
            JOIN territories AS t ON t.id = link.territory_id
            JOIN organizations AS o ON o.id = link.organization_id
            """
        )

        selected: dict[OrganizationType, tuple[int, Organization]] = {}

        for row in rows:
            if any(
                row[field] and row[field] != target[field]
                for field in target
            ):
                continue

            specificity = sum(bool(row[field]) for field in target)
            organization_type = OrganizationType[row["organization_type"]]
            organization = Organization(
                id=row["id"],
                organization_type=organization_type,
                recipient=row["recipient"],
                postal_address=row["postal_address"],
                phones=tuple(json.loads(row["phones"])),
                email=row["email"],
                fax=row["fax"],
                source_url=row["source_url"],
                verification_status=row["verification_status"],
                verified_at=row["verified_at"],
                verification_note=row["verification_note"],
            )

            current = selected.get(organization_type)
            if current is None or specificity > current[0]:
                selected[organization_type] = (specificity, organization)

        return {
            organization_type: item[1]
            for organization_type, item in selected.items()
        }

    @staticmethod
    def _organization_from_row(row) -> Organization:
        return Organization(
            id=row["id"],
            organization_type=OrganizationType[row["organization_type"]],
            recipient=row["recipient"],
            postal_address=row["postal_address"],
            phones=tuple(json.loads(row["phones"])),
            email=row["email"],
            fax=row["fax"],
            source_url=row["source_url"],
            verification_status=row["verification_status"],
            verified_at=row["verified_at"],
            verification_note=row["verification_note"],
        )
