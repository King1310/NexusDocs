from __future__ import annotations

from datetime import date

from domain.entities.person import Person
from domain.value_objects.address import Address
from domain.value_objects.birth import Birth
from domain.value_objects.document_info import DocumentInfo
from domain.value_objects.fullname import FullName
from domain.value_objects.military import Military
from domain.value_objects.passport import Passport
from domain.value_objects.soch_case import SochCase


class PersonMapper:
    """
    Преобразование Person <-> запись базы данных.
    """

    @staticmethod
    def to_record(person: Person) -> dict:
        """
        Преобразовать Person в словарь для SQLite.
        """

        record = {
            "id": person.id,
        }

        record.update(
            person.full_name.to_dict()
        )

        # Паспорт
        if person.passport is not None:
            record.update(
                person.passport.to_dict()
            )
        else:
            record.update(
                {
                    "passport_series": None,
                    "passport_number": None,
                    "passport_issued_by": None,
                    "passport_issue_date": None,
                }
            )

        # Рождение
        record.update(
            person.birth.to_dict()
        )

        # Адрес регистрации
        record.update(
            person.registration_address.to_dict(
                "registration"
            )
        )

        # Военные сведения
        record.update(
            person.military.to_dict()
        )

        # Сведения о СОЧ
        record.update(
            person.soch_case.to_dict()
        )

        # Документ
        record.update(
            person.document_info.to_dict()
        )

        return record

    @staticmethod
    def from_record(data: dict) -> Person:
        """
        Построить Person из записи базы данных.
        """

        passport = None

        if (
            data["passport_series"]
            and data["passport_number"]
        ):
            passport = Passport(
                series=data["passport_series"],
                number=data["passport_number"],
                issued_by=data["passport_issued_by"],
                issue_date=date.fromisoformat(
                    data["passport_issue_date"]
                ),
            )

        return Person(
            id=data["id"],

            full_name=FullName(
                last_name=data["last_name"],
                first_name=data["first_name"],
                middle_name=data["middle_name"],
            ),

            passport=passport,

            birth=Birth(
                birth_date=date.fromisoformat(
                    data["birth_date"]
                ),
                place=Address(
                    region=data["birth_region"],
                    district=data["birth_district"],
                    city=data["birth_city"],
                    locality=data["birth_locality"],
                    street=data["birth_street"],
                    house=data["birth_house"],
                    apartment=data["birth_apartment"],
                ),
            ),

            registration_address=Address(
                region=data["registration_region"],
                district=data["registration_district"],
                city=data["registration_city"],
                locality=data["registration_locality"],
                street=data["registration_street"],
                house=data["registration_house"],
                apartment=data["registration_apartment"],
            ),

            military=Military(
                military_unit=data["military_unit"],
                rank=data["rank"],
                position=data["position"],
                military_id=data["military_id"],
            ),

            soch_case=SochCase(
                soch_date=date.fromisoformat(
                    data["soch_date"]
                ),
                soch_place=data["soch_place"],
                duration=data["duration"],
                case_type=data["case_type"],
                case_number=data["case_number"],
                procedural_control=data["procedural_control"],
                article=data["article"],
            ),

            document_info=DocumentInfo(
                outgoing_number=data["outgoing_number"],
                outgoing_date=date.fromisoformat(
                    data["outgoing_date"]
                ),
                vpg=data["vpg"],
            ),
        )