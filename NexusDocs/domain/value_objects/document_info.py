from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True, frozen=True)
class DocumentInfo:
    """
    Сведения об исходящем документе.
    """

    outgoing_number: str
    outgoing_date: date
    vpg: int = 60

    def to_dict(self) -> dict:
        """
        Преобразовать сведения о документе в словарь.
        """

        return {
            "outgoing_number": self.outgoing_number,
            "outgoing_date": self.outgoing_date.isoformat(),
            "vpg": self.vpg,
        }