from domain.entities.organization import Organization
from domain.enums.organization_type import OrganizationType
from services.generation_service import GenerationService


def _header(
    organization_type: OrganizationType,
    recipient: str,
    address: str,
    phone: str,
    email: str = "",
) -> str:
    return GenerationService._simple_recipient_header(
        Organization(
            id=None,
            organization_type=organization_type,
            recipient=recipient,
            postal_address=address,
            phones=(phone,),
            email=email,
            verification_status="user_verified",
        )
    )


def test_nine_dynamic_headers_follow_user_examples_exactly():
    examples = {
        OrganizationType.MILITARY_COMMISSARIAT: (
            _header(
                OrganizationType.MILITARY_COMMISSARIAT,
                "Военному комиссару\nВоенного комиссариата\n"
                "Раменского муниципального округа и городских округов "
                "Жуковский и Бронницы Московской области",
                "140100, Московская область, г. Раменское, ул. Гурьева, д. 21",
                "+7 (496) 463-38-48",
                "voenkommo_ramenskoe@mil.ru",
            ),
            "Военному комиссару\nВоенного комиссариата\n"
            "Раменского муниципального округа и городских округов Жуковский "
            "и Бронницы Московской области\n\n"
            "140100, Московская область, г. Раменское, ул. Гурьева, д. 21\n"
            "тел.: +7 (496) 463-38-48\n"
            "эл. почта: voenkommo_ramenskoe@mil.ru",
        ),
        OrganizationType.MILITARY_COMMANDANT: (
            _header(
                OrganizationType.MILITARY_COMMANDANT,
                "Военному коменданту\nВоенной комендатуры\nПодольского гарнизона",
                "142100, Московская область, г. Подольск, ул. Парковая, д. 56",
                "+7 (496) 755-63-30",
            ),
            "Военному коменданту\nВоенной комендатуры\nПодольского гарнизона\n\n"
            "142100, Московская область, г. Подольск, ул. Парковая, д. 56\n"
            "тел.: +7 (496) 755-63-30",
        ),
        OrganizationType.NARCOLOGY: (
            _header(
                OrganizationType.NARCOLOGY,
                "Главному врачу\nГБУЗ Московской области «Раменская больница»",
                "140105, Московская область, г. Раменское, ул. Мира, д. 12/1",
                "+7 (496) 463-54-21",
                "kanc@ramcrb.ru",
            ),
            "Главному врачу\nГБУЗ Московской области «Раменская больница»\n\n"
            "140105, Московская область, г. Раменское, ул. Мира, д. 12/1\n"
            "тел.: +7 (496) 463-54-21\nэл. почта: kanc@ramcrb.ru",
        ),
        OrganizationType.PSYCHIATRY: (
            _header(
                OrganizationType.PSYCHIATRY,
                "Главному врачу\nГБУЗ Московской области «Раменская больница»",
                "140100, Московская область, г. Раменское, ул. Мира, д. 12/1",
                "+7 (498) 602-00-61",
                "kanc@ramcrb.ru",
            ),
            "Главному врачу\nГБУЗ Московской области «Раменская больница»\n\n"
            "140100, Московская область, г. Раменское, ул. Мира, д. 12/1\n"
            "тел.: +7 (498) 602-00-61\nэл. почта: kanc@ramcrb.ru",
        ),
        OrganizationType.HOSPITAL: (
            _header(
                OrganizationType.HOSPITAL,
                "Главному врачу\nГБУЗ Московской области «Раменская больница»",
                "140100, Московская область, г. Раменское, ул. Махова, д. 14",
                "+7 (496) 463-30-21",
                "kanc@ramcrb.ru",
            ),
            "Главному врачу\nГБУЗ Московской области «Раменская больница»\n\n"
            "140100, Московская область, г. Раменское, ул. Махова, д. 14\n"
            "тел.: +7 (496) 463-30-21\nэл. почта: kanc@ramcrb.ru",
        ),
        OrganizationType.TFOMS: (
            _header(
                OrganizationType.TFOMS,
                "Директору\nТерриториального фонда\n"
                "обязательного медицинского страхования\nМосковской области",
                "140000, Московская область, г. Люберцы, ул. Звуковая, д. 4",
                "+7 (495) 587-98-97",
                "Lub26_oms@mofoms.ru",
            ),
            "Директору\nТерриториального фонда\n"
            "обязательного медицинского страхования\nМосковской области\n\n"
            "140000, Московская область, г. Люберцы, ул. Звуковая, д. 4\n"
            "тел.: +7 (495) 587-98-97\nэл. почта: Lub26_oms@mofoms.ru",
        ),
        OrganizationType.ADMINISTRATION: (
            _header(
                OrganizationType.ADMINISTRATION,
                "Главе\nРаменского муниципального округа",
                "140100, Московская область, г. Раменское, "
                "Комсомольская площадь, д. 2",
                "+7 (496) 473-91-01",
                "ram_glava@mosreg.ru",
            ),
            "Главе\nРаменского муниципального округа\n\n"
            "140100, Московская область, г. Раменское, Комсомольская площадь, д. 2\n"
            "тел.: +7 (496) 473-91-01\nэл. почта: ram_glava@mosreg.ru",
        ),
        OrganizationType.CONTRACT_SERVICE_POINT: (
            _header(
                OrganizationType.CONTRACT_SERVICE_POINT,
                "Начальнику\nПункта отбора\nна военную службу по контракту\n"
                "Московской области",
                "143900, Московская область, г. Балашиха, "
                "Восточное шоссе, владение 2",
                "+7 (495) 990-77-77",
            ),
            "Начальнику\nПункта отбора\nна военную службу по контракту\n"
            "Московской области\n\n"
            "143900, Московская область, г. Балашиха, Восточное шоссе, владение 2\n"
            "тел.: +7 (495) 990-77-77",
        ),
        OrganizationType.ELECTION_COMMISSION: (
            _header(
                OrganizationType.ELECTION_COMMISSION,
                "Председателю\nТерриториальной избирательной комиссии\n"
                "Раменского городского округа",
                "140100, Московская область, г. Раменское, "
                "Комсомольская площадь, д. 2, каб. 116",
                "8 (496) 463-67-03",
                "tikramenskoe@mail.ru",
            ),
            "Председателю\nТерриториальной избирательной комиссии\n"
            "Раменского городского округа\n\n"
            "140100, Московская область, г. Раменское, "
            "Комсомольская площадь, д. 2, каб. 116\n"
            "тел.: 8 (496) 463-67-03\nэл. почта: tikramenskoe@mail.ru",
        ),
    }

    assert all(actual == expected for actual, expected in examples.values())
