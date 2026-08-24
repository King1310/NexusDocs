from __future__ import annotations

from domain.entities.organization import Organization
from domain.enums.organization_type import OrganizationType
from domain.value_objects.address import Address


class CuratedHeaderService:
    """User-approved header sets that must not be rebuilt from search snippets."""

    @classmethod
    def resolve(
        cls,
        address: Address,
        organization_types,
    ) -> dict[OrganizationType, Organization]:
        requested = set(organization_types)
        if not cls._is_ramensky(address):
            return {}
        return {
            organization.organization_type: organization
            for organization in cls._ramensky_headers()
            if organization.organization_type in requested
        }

    @staticmethod
    def _is_ramensky(address: Address) -> bool:
        region = address.region.casefold().replace("ё", "е")
        territory = " ".join(
            (address.district, address.city, address.locality)
        ).casefold().replace("ё", "е")
        return "московск" in region and (
            "раменск" in territory or "электроизолятор" in territory
        )

    @classmethod
    def _ramensky_headers(cls) -> tuple[Organization, ...]:
        return (
            cls._organization(
                OrganizationType.MILITARY_COMMISSARIAT,
                "Военному комиссару\n"
                "Военного комиссариата\n"
                "Раменского муниципального округа\n"
                "и городских округов Жуковский\n"
                "и Бронницы Московской области",
                "140100, Московская область, г. Раменское, "
                "ул. Гурьева, д. 21",
                ("+7 (496) 463-38-48",),
            ),
            cls._organization(
                OrganizationType.MILITARY_COMMANDANT,
                "Военному коменданту\n"
                "Военной комендатуры\n"
                "Подольского гарнизона",
                "142117, Московская область, г. Подольск, "
                "ул. Парковая, д. 56",
                ("+7 (496) 755-63-30",),
            ),
            cls._organization(
                OrganizationType.NARCOLOGY,
                cls._ramensky_hospital_recipient(),
                "140105, Московская область, г. Раменское, "
                "ул. Мира, д. 12/1",
                ("+7 (496) 463-54-21",),
                "kanc@ramcrb.ru",
            ),
            cls._organization(
                OrganizationType.PSYCHIATRY,
                cls._ramensky_hospital_recipient(),
                "140100, Московская область, г. Раменское, "
                "ул. Мира, д. 12/1",
                ("+7 (498) 602-00-61",),
                "kanc@ramcrb.ru",
            ),
            cls._organization(
                OrganizationType.HOSPITAL,
                cls._ramensky_hospital_recipient(),
                "140100, Московская область, г. Раменское, "
                "ул. Махова, д. 14",
                ("+7 (496) 463-30-21",),
                "kanc@ramcrb.ru",
            ),
            cls._organization(
                OrganizationType.TFOMS,
                "Директору\n"
                "Территориального фонда\n"
                "обязательного медицинского страхования\n"
                "Московской области",
                "140000, Московская область, г. Люберцы, "
                "ул. Звуковая, д. 4",
                ("+7 (495) 587-98-97",),
                "Lub26_oms@mofoms.ru",
            ),
            cls._organization(
                OrganizationType.ADMINISTRATION,
                "Главе\nРаменского муниципального округа",
                "140100, Московская область, г. Раменское, "
                "Комсомольская площадь, д. 2",
                ("+7 (496) 473-91-01",),
                "ram_glava@mosreg.ru",
            ),
            cls._organization(
                OrganizationType.CONTRACT_SERVICE_POINT,
                "Начальнику\n"
                "Пункта отбора\n"
                "на военную службу по контракту\n"
                "Московской области",
                "143900, Московская область, г. Балашиха, "
                "Восточное шоссе, владение 2",
                ("+7 (495) 990-77-77",),
            ),
            cls._organization(
                OrganizationType.ELECTION_COMMISSION,
                "Председателю\n"
                "Территориальной избирательной комиссии\n"
                "Раменского городского округа",
                "140100, Московская область, г. Раменское, "
                "Комсомольская площадь, д. 2, каб. 116",
                ("8 (496) 463-67-03",),
                "tikramenskoe@mail.ru",
            ),
        )

    @staticmethod
    def _ramensky_hospital_recipient() -> str:
        return (
            "Главному врачу\n"
            "ГБУЗ Московской области\n"
            "«Раменская больница»"
        )

    @staticmethod
    def _organization(
        organization_type: OrganizationType,
        recipient: str,
        postal_address: str,
        phones: tuple[str, ...],
        email: str = "",
    ) -> Organization:
        return Organization(
            id=None,
            organization_type=organization_type,
            recipient=recipient,
            postal_address=postal_address,
            phones=phones,
            email=email,
            source_url="",
            verification_status="user_verified",
            verified_at="19.08.2026",
            verification_note=(
                "Шапка собрана по утверждённому пользователем эталону."
            ),
        )
