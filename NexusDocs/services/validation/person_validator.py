from services.validation.validation_result import ValidationResult
from domain.entities.person import Person


class PersonValidator:

    def validate(self, person: Person) -> ValidationResult:

        result = ValidationResult()

        if not person.full_name.last_name:
            result.add(
                "last_name",
                "Введите фамилию."
            )

        if not person.full_name.first_name:
            result.add(
                "first_name",
                "Введите имя."
            )

        if not person.full_name.middle_name:
            result.add(
                "middle_name",
                "Введите отчество."
            )

        if person.passport is None and (
                person.military is None
                or not person.military.personal_number
        ):
            result.add(
                "passport",
                "Укажите паспортные данные либо личный номер."
            )

        return result