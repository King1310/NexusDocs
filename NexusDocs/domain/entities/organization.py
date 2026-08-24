from __future__ import annotations

from dataclasses import dataclass

from domain.enums.organization_type import OrganizationType


@dataclass(slots=True, frozen=True)
class Organization:
    """Проверенный адресат и его реквизиты для шапки запроса."""

    id: int | None
    organization_type: OrganizationType
    recipient: str
    postal_address: str
    phones: tuple[str, ...] = ()
    email: str = ""
    fax: str = ""
    source_url: str = ""
    verification_status: str = "unverified"
    verified_at: str = ""
    verification_note: str = ""

    @property
    def header(self) -> str:
        parts = [self.recipient.strip(), self.postal_address.strip()]

        if self.phones:
            parts.append("тел.: " + ",\n".join(self.phones))
        if self.fax:
            parts.append(f"факс: {self.fax}")
        if self.email:
            parts.append(f"эл. почта: {self.email}")

        return "\n\n".join(part for part in parts if part)
