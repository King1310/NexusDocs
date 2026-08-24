from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True, frozen=True)
class SochCase:
    """
    Сведения по делу о СОЧ.
    """

    soch_date: date
    soch_place: str
    duration: str
    case_type: str
    case_number: str | None
    procedural_control: str
    article: str

    def to_dict(self) -> dict:
        """
        Преобразовать сведения о СОЧ в словарь.
        """

        return {
            "soch_date": self.soch_date.isoformat(),
            "soch_place": self.soch_place,
            "duration": self.duration,
            "case_type": self.case_type,
            "case_number": self.case_number,
            "procedural_control": self.procedural_control,
            "article": self.article,
        }
