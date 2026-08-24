from datetime import date

from domain.entities.person import Person
from domain.enums.gender import Gender
from domain.value_objects.address import Address
from domain.value_objects.birth import BirthInfo
from domain.value_objects.contact import ContactInfo
from domain.value_objects.fullname import FullName
from domain.value_objects.investigation import InvestigationInfo
from domain.value_objects.military import MilitaryInfo
from domain.value_objects.passport import Passport


class PersonFactory:
    """
    Создаёт объект Person из словаря данных.
    """

    @staticmethod
    def create(data: dict) -> Person:
        full_name = FullName(
            last_name=data["last_name"],
            first_name=data["first_name"],
            middle_name=data["middle_name"],
        )

        passport = None
        if data.get("passport_series") and data.get("passport_number"):
            passport = Passport(
                series=data["passport_series"],
                number=data["passport_number"],
                issued_by=data.get("passport_issued_by", ""),
            )

        registration = Address(
            raw=data["registration_address"]
        )

        residence = Address(
            raw=data.get("residence_address", "")
        )

        birth = BirthInfo(
            birth_date=data["birth_date"],
            birth_place=data["birth_place"],
        )

        contact = ContactInfo(
            phone=data.get("phone", "")
        )

        military = MilitaryInfo(
            unit=data["unit"],
            position=data["position"],
            rank=data["rank"],
            personal_number=data.get("personal_number", ""),
            status=data["status"],
            contract_place=data.get("contract_place", ""),
            unit_location=data["unit_location"],
        )

        investigation = data.get("investigation")

        return Person(
            id=data["id"],
            full_name=full_name,
            gender=Gender.from_value(data["gender"]),
            citizenship=data.get("citizenship", "Российская Федерация"),
            nationality=data.get("nationality", ""),
            education=data.get("education", ""),
            family_status=data.get("family_status", ""),
            passport=passport,
            military=military,
            investigation=investigation,
            birth=birth,
            registration_address=registration,
            residence_address=residence,
            contact=contact,
            created_at=date.today(),
        )