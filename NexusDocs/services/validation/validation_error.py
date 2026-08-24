from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ValidationError:
    """
    Ошибка валидации.
    """

    field: str

    message: str