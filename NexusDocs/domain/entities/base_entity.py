from __future__ import annotations

from dataclasses import dataclass

from domain.exceptions.person_error import PersonError


@dataclass(slots=True)
class BaseEntity:
    """
    Базовая сущность предметной области.

    Каждая сущность имеет уникальный идентификатор.
    """

    id: int

    def __post_init__(self) -> None:
        if self.id <= 0:
            raise PersonError(
                "ID должен быть больше нуля."
            )