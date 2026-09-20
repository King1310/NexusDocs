from __future__ import annotations

from domain.entities.person import Person
from database.repositories.person_repository import PersonRepository
from ui.form_data import PersonFormData


class PersonService:
    """
    Сервис создания, сохранения и редактирования Person.
    """

    def __init__(
        self,
        repository: PersonRepository,
    ):
        self.repository = repository

    def create(
        self,
        form_data: PersonFormData,
    ) -> Person:
        """
        Создать Person из PersonFormData.
        """

        self._validate_form_data(
            form_data
        )

        person = Person(
            id=self.repository.get_next_id(),
            investigator=form_data.investigator,

            full_name=form_data.full_name,

            passport=form_data.passport,

            birth=form_data.birth,

            registration_address=(
                form_data.registration_address
            ),

            military=form_data.military,

            soch_case=form_data.soch_case,

            document_info=form_data.document_info,
        )

        return person

    def save(
        self,
        form_data: PersonFormData,
    ) -> Person:
        """
        Создать Person и сохранить его в БД.
        """

        person = self.create(
            form_data
        )

        self.repository.save(
            person
        )

        return person

    def update(
        self,
        person_id: int,
        form_data: PersonFormData,
    ) -> Person:
        """
        Обновить существующего Person.
        """

        self._validate_form_data(
            form_data
        )

        person = Person(
            id=person_id,
            investigator=form_data.investigator,

            full_name=form_data.full_name,

            passport=form_data.passport,

            birth=form_data.birth,

            registration_address=(
                form_data.registration_address
            ),

            military=form_data.military,

            soch_case=form_data.soch_case,

            document_info=form_data.document_info,
        )

        self.repository.update(
            person
        )

        return person

    @staticmethod
    def _validate_form_data(
        form_data: PersonFormData,
    ) -> None:
        """
        Проверить, что все обязательные данные заполнены.
        """

        required_fields = {
            "ФИО": form_data.full_name,
            "рождение": form_data.birth,
            "адрес регистрации": (
                form_data.registration_address
            ),
            "военные сведения": (
                form_data.military
            ),
            "сведения о СОЧ": (
                form_data.soch_case
            ),
            "сведения о документе": (
                form_data.document_info
            ),
        }

        missing_fields = [
            name
            for name, value
            in required_fields.items()
            if value is None
        ]

        if missing_fields:
            fields = ", ".join(
                missing_fields
            )

            raise ValueError(
                "Не заполнены обязательные данные: "
                f"{fields}"
            )
