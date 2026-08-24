from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from domain.value_objects.address import Address


@dataclass(slots=True, frozen=True)
class Birth:
    """
    Дата и место рождения.
    """

    birth_date: date
    place: Address

    def to_dict(self) -> dict:
        """
        Преобразовать сведения о рождении в словарь.
        """

        return {
            "birth_date": self.birth_date.isoformat(),
            **self.place.to_dict("birth"),
        }