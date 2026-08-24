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


class PersonFactory:
    """
    Фабрика тестовых объектов Person.
    """

    @staticmethod
    def create(
        person_id: int = 1,
    ) -> Person:

        return Person(
            id=person_id,

            full_name=FullName(
                last_name="Иванов",
                first_name="Иван",
                middle_name="Иванович",
            ),

            passport=Passport(
                series="1234",
                number="123456",
                issued_by="ОВД России",
                issue_date=date(2018, 5, 20),
            ),

            birth=Birth(
                birth_date=date(1999, 8, 15),
                place=Address(
                    region="Московская область",
                    district="",
                    city="Балашиха",
                    locality="",
                    street="Советская",
                    house="10",
                ),
            ),

            registration_address=Address(
                region="Московская область",
                district="",
                city="Балашиха",
                locality="",
                street="Ленина",
                house="15",
                apartment="20",
            ),

            military=Military(
                military_unit="12345",
                rank="рядовой",
                position="стрелок",
                military_id="АБ1234567",
            ),

            soch_case=SochCase(
                soch_date=date(2026, 7, 20),
                soch_place="Балашиха",
                duration="15 суток",
                case_type="УД",
                case_number="123/2026",
                procedural_control="Военная прокуратура",
                article="337 УК РФ",
            ),

            document_info=DocumentInfo(
                outgoing_number="123/1",
                outgoing_date=date.today(),
                vpg=60,
            ),
        )
