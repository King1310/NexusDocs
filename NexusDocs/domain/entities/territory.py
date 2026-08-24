from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Territory:
    """Территория, для которой действует набор организаций."""

    id: int | None
    region: str
    district: str = ""
    city: str = ""
    locality: str = ""
    street: str = ""

    @property
    def specificity(self) -> int:
        return sum(
            bool(value)
            for value in (
                self.region,
                self.district,
                self.city,
                self.locality,
                self.street,
            )
        )
