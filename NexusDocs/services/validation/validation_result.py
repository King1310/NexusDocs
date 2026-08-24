from dataclasses import dataclass, field

from services.validation.validation_error import ValidationError


@dataclass(slots=True)
class ValidationResult:
    """
    Результат проверки.
    """

    errors: list[ValidationError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add(self, field: str, message: str):
        self.errors.append(
            ValidationError(field, message)
        )