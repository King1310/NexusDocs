from __future__ import annotations

from dataclasses import dataclass

from domain.entities.person import Person
from domain.value_objects.address import Address
from domain.value_objects.birth import Birth
from domain.value_objects.document_info import DocumentInfo
from domain.value_objects.fullname import FullName
from domain.value_objects.military import Military
from domain.value_objects.passport import Passport
from domain.value_objects.soch_case import SochCase
from domain.value_objects.investigator import Investigator, TSOMARTOV


@dataclass
class PersonFormData:
    """
    Данные, собираемые во время создания или редактирования Person.
    """

    full_name: FullName | None = None

    passport: Passport | None = None

    birth: Birth | None = None

    registration_address: Address | None = None

    military: Military | None = None

    soch_case: SochCase | None = None

    document_info: DocumentInfo | None = None
    investigator: Investigator = TSOMARTOV

    @classmethod
    def from_person(
        cls,
        person: Person,
    ) -> "PersonFormData":
        """
        Создать данные формы из существующего Person.
        Используется при редактировании человека.
        """

        return cls(
            full_name=person.full_name,
            passport=person.passport,
            birth=person.birth,
            registration_address=person.registration_address,
            military=person.military,
            soch_case=person.soch_case,
            document_info=person.document_info,
            investigator=person.investigator,
        )
