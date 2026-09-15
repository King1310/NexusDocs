from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Military:
    """
    Воинские сведения.
    """

    military_unit: str
    rank: str
    position: str
    military_id: str
    military_deployment: str = ""
    service_basis: str = ""

    def to_dict(self) -> dict:
        """
        Преобразовать воинские сведения в словарь.
        """

        return {
            "military_unit": self.military_unit,
            "rank": self.rank,
            "position": self.position,
            "military_id": self.military_id,
            "military_deployment": self.military_deployment,
            "service_basis": self.service_basis,
        }
