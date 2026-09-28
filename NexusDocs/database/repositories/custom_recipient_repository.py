from __future__ import annotations

import json
from pathlib import Path

from database.organization_database_manager import OrganizationDatabaseManager
from database.organizations_schema import create_organizations_tables
from domain.entities.custom_recipient import (
    CustomRecipient,
    normalize_lookup_name,
)


class CustomRecipientRepository:
    """Справочник адресатов для уникальных запросов."""

    def __init__(self, database_file: Path | None = None):
        create_organizations_tables(database_file)
        self.db = OrganizationDatabaseManager(database_file)

    def save(self, recipient: CustomRecipient) -> int:
        """Сохранить нового адресата без замены тёзки."""

        cursor = self.db.execute(
            """
            INSERT INTO custom_recipients
            (
                template_slug, lookup_name, lookup_name_normalized,
                recipient, postal_address, phones, email, source_url,
                verification_status, verified_at, verification_note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._values(recipient),
        )
        return cursor.lastrowid

    def upsert(self, recipient: CustomRecipient) -> int:
        """Создать адресата или обновить его в своей категории."""

        if recipient.id is not None and self.get(recipient.id) is not None:
            self.db.execute(
                """
                UPDATE custom_recipients
                SET template_slug = ?, lookup_name = ?,
                    lookup_name_normalized = ?, recipient = ?,
                    postal_address = ?, phones = ?, email = ?,
                    source_url = ?, verification_status = ?,
                    verified_at = ?, verification_note = ?
                WHERE id = ?
                """,
                (*self._values(recipient), recipient.id),
            )
            return recipient.id

        self.db.execute(
            """
            INSERT INTO custom_recipients
            (
                template_slug, lookup_name, lookup_name_normalized,
                recipient, postal_address, phones, email, source_url,
                verification_status, verified_at, verification_note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(template_slug, lookup_name_normalized)
            DO UPDATE SET
                lookup_name = excluded.lookup_name,
                recipient = excluded.recipient,
                postal_address = excluded.postal_address,
                phones = excluded.phones,
                email = excluded.email,
                source_url = excluded.source_url,
                verification_status = excluded.verification_status,
                verified_at = excluded.verified_at,
                verification_note = excluded.verification_note
            """,
            self._values(recipient),
        )
        stored = self.find_by_lookup_name(
            recipient.template_slug,
            recipient.lookup_name,
        )
        if stored is None:
            raise RuntimeError("Не удалось сохранить адресата.")
        return stored.id

    def get(self, recipient_id: int) -> CustomRecipient | None:
        row = self.db.fetch_one(
            "SELECT * FROM custom_recipients WHERE id = ?",
            (recipient_id,),
        )
        return self._from_row(row) if row is not None else None

    def list(self, template_slug: str) -> list[CustomRecipient]:
        rows = self.db.fetch_all(
            """
            SELECT * FROM custom_recipients
            WHERE template_slug = ?
            ORDER BY lookup_name_normalized, id
            """,
            (template_slug.strip(),),
        )
        return [self._from_row(row) for row in rows]

    def search(
        self,
        template_slug: str,
        query: str,
    ) -> list[CustomRecipient]:
        normalized = normalize_lookup_name(query)
        if not normalized:
            return self.list(template_slug)

        tokens = normalized.split()
        conditions = " AND ".join(
            "lookup_name_normalized LIKE ? ESCAPE '\\'"
            for _ in tokens
        )
        escaped_tokens = tuple(
            f"%{self._escape_like(token)}%"
            for token in tokens
        )
        rows = self.db.fetch_all(
            f"""
            SELECT * FROM custom_recipients
            WHERE template_slug = ? AND {conditions}
            ORDER BY
                CASE
                    WHEN lookup_name_normalized = ? THEN 0
                    WHEN lookup_name_normalized LIKE ? ESCAPE '\\' THEN 1
                    ELSE 2
                END,
                lookup_name_normalized,
                id
            """,
            (
                template_slug.strip(),
                *escaped_tokens,
                normalized,
                f"{self._escape_like(normalized)}%",
            ),
        )
        return [self._from_row(row) for row in rows]

    def find_by_lookup_name(
        self,
        template_slug: str,
        lookup_name: str,
    ) -> CustomRecipient | None:
        row = self.db.fetch_one(
            """
            SELECT * FROM custom_recipients
            WHERE template_slug = ? AND lookup_name_normalized = ?
            """,
            (
                template_slug.strip(),
                normalize_lookup_name(lookup_name),
            ),
        )
        return self._from_row(row) if row is not None else None

    @staticmethod
    def _values(recipient: CustomRecipient) -> tuple[str, ...]:
        return (
            recipient.template_slug,
            recipient.lookup_name,
            recipient.normalized_lookup_name,
            recipient.recipient,
            recipient.postal_address,
            json.dumps(recipient.phones, ensure_ascii=False),
            recipient.email,
            recipient.source_url,
            recipient.verification_status,
            recipient.verified_at,
            recipient.verification_note,
        )

    @staticmethod
    def _from_row(row) -> CustomRecipient:
        return CustomRecipient(
            id=row["id"],
            template_slug=row["template_slug"],
            lookup_name=row["lookup_name"],
            recipient=row["recipient"],
            postal_address=row["postal_address"],
            phones=tuple(json.loads(row["phones"])),
            email=row["email"],
            source_url=row["source_url"],
            verification_status=row["verification_status"],
            verified_at=row["verified_at"],
            verification_note=row["verification_note"],
        )

    @staticmethod
    def _escape_like(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
