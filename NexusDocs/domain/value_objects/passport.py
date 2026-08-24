from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from domain.exceptions.validation_error import ValidationError


@dataclass(slots=True, frozen=True)
class Passport:
    """
    Паспорт гражданина РФ.
    """

    series: str
    number: str
    issued_by: str
    issue_date: date

    def __post_init__(self) -> None:
        if len(self.series) != 4:
            raise ValidationError(
                "Серия паспорта должна содержать 4 цифры."
            )

        if len(self.number) != 6:
            raise ValidationError(
                "Номер паспорта должен содержать 6 цифр."
            )

    def to_dict(self) -> dict:
        """
        Преобразовать паспорт в словарь.
        """

        return {
            "passport_series": self.series,
            "passport_number": self.number,
            "passport_issued_by": self.issued_by,
            "passport_issue_date": self.issue_date.isoformat(),
        }