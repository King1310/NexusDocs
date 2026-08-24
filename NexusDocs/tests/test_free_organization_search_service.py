from domain.enums.organization_type import OrganizationType
from domain.value_objects.address import Address
from services.free_organization_search_service import (
    FreeOrganizationSearchService,
)


class FakeBackend:
    RESULTS = {
        "военный комиссариат": {
            "title": "Военные комиссариаты Краснодарского края",
            "href": "https://krasnodar.ru/content/2576/",
            "body": (
                "Военный комиссариат Красноармейского района. Почтовый адрес: "
                "353807, Краснодарский край, Красноармейский район, "
                "ст. Полтавская, ул. Садовая, д. 77 тел.: +7 (86165) 3-22-65"
            ),
        },
        "военная комендатура": {
            "title": "Военная комендатура Краснодарского гарнизона",
            "href": "https://example.test/komendatura",
            "body": (
                "Адрес: 350049, г. Краснодар, ул. Рылеева, д. 356 "
                "тел.: +7 (861) 268-58-56"
            ),
        },
        "наркологический диспансер": {
            "title": (
                "Контакты - Государственное бюджетное учреждение "
                "здравоохранения «Наркологический диспансер» министерства "
                "здравоохранения Краснодарского края"
            ),
            "href": "https://narko23.ru/contacts/",
            "body": (
                "Красноармейский филиал. 353800, Краснодарский край, "
                "Красноармейский район, ст. Полтавская, ул. Ковтюха, д. 2 "
                "тел.: +7 (86165) 4-20-13 email: poltav@narco23.ru"
            ),
        },
        "психиатрическое отделение": None,
        "ЦРБ ЦГБ": {
            "title": "ГБУЗ «Красноармейская ЦРБ» - Контакты",
            "href": "https://krasncrb.ru/contacts/",
            "body": (
                "353800, Краснодарский край, Красноармейский район, "
                "ст. Полтавская, ул. Просвещения, д. 59, корп. 3 "
                "тел.: +7 (86165) 3-37-65 email: priem@krasncrb.ru"
            ),
        },
        "ТФОМС": {
            "title": "Контакты - ТФОМС КК",
            "href": "https://kubanoms.ru/contact.html",
            "body": (
                "Территориальный фонд обязательного медицинского страхования "
                "Краснодарского края. Адрес: 350020, Краснодарский край, "
                "г. Краснодар, ул. Красная, д. 178 тел.: +7 (861) 215-24-62 "
                "email: tfomskk@kubanoms.ru"
            ),
        },
        "администрация": {
            "title": "Официальный сайт - Администрация Октябрьского сельского поселения",
            "href": "https://oktpos.ru/contacts/",
            "body": (
                "Глава Октябрьского сельского поселения "
                "Иванов Иван Иванович. "
                "353814, Краснодарский край, Красноармейский район, "
                "п. Октябрьский, ул. Мира, д. 10 тел.: +7 (86165) 9-10-01 "
                "email: oktpos@mail.ru"
            ),
        },
        "пункт отбора": {
            "title": "Пункт отбора на военную службу по контракту, г. Краснодар",
            "href": "https://example.test/contract",
            "body": (
                "Адрес: 350005, Краснодарский край, г. Краснодар, "
                "ул. Ярославская, д. 130 тел.: +7 (861) 258-35-40"
            ),
        },
        "ТИК": {
            "title": "ТИК Красноармейская",
            "href": "https://portal-izbirkom-kk.ru/ik/tik-krasnoarmeyskaya",
            "body": (
                "Территориальная избирательная комиссия Красноармейская. "
                "Адрес: 353800, Краснодарский край, Красноармейский район, "
                "ст. Полтавская, "
                "ул. Красная, д. 122 тел.: 8 (86165) 4-11-47 "
                "email: t19@ikkk.ru"
            ),
        },
    }

    def text(self, query, **_kwargs):
        for marker, result in self.RESULTS.items():
            if marker.casefold() in query.casefold():
                return [] if result is None else [result]
        return []


def _address() -> Address:
    return Address(
        region="Краснодарский край",
        district="Красноармейский район",
        city="",
        locality="п. Рисоопытный",
        street="ул. Комсомольская",
        house="16",
        apartment="9",
    )


def _ramensky_address() -> Address:
    return Address(
        region="Московская область",
        district="Раменский район",
        city="",
        locality="п. Электроизолятор",
        street="",
        house="24",
        apartment="31",
    )


def test_free_search_builds_all_nine_headers_from_public_territory():
    service = FreeOrganizationSearchService(backend=FakeBackend())

    outcome = service.search(_address(), tuple(OrganizationType))

    assert outcome.unresolved_types == (OrganizationType.PSYCHIATRY,)
    assert len(outcome.organizations) == 9
    by_type = {item.organization_type: item for item in outcome.organizations}
    assert by_type[OrganizationType.MILITARY_COMMISSARIAT].recipient == (
        "Военному комиссару\n"
        "Военного комиссариата\n"
        "Красноармейского района Краснодарского края"
    )
    assert by_type[OrganizationType.MILITARY_COMMANDANT].recipient == (
        "Военному коменданту\n"
        "Военной комендатуры\n"
        "Краснодарского гарнизона"
    )
    assert by_type[OrganizationType.HOSPITAL].postal_address.startswith("353800")
    assert by_type[OrganizationType.TFOMS].email == "tfomskk@kubanoms.ru"
    assert by_type[OrganizationType.TFOMS].recipient == (
        "Директору\n"
        "Территориального фонда\n"
        "обязательного медицинского страхования\n"
        "Краснодарского края"
    )
    assert "ТИК" not in by_type[OrganizationType.ELECTION_COMMISSION].recipient
    assert "Территориальной избирательной комиссии" in (
        by_type[OrganizationType.ELECTION_COMMISSION].recipient
    )
    assert by_type[OrganizationType.ELECTION_COMMISSION].recipient.endswith(
        "Красноармейская"
    )
    assert by_type[OrganizationType.ADMINISTRATION].recipient == (
        "Главе\nОктябрьского сельского поселения"
    )
    assert by_type[OrganizationType.NARCOLOGY].recipient.startswith("Главному врачу\n")
    assert by_type[OrganizationType.PSYCHIATRY].source_url == (
        by_type[OrganizationType.NARCOLOGY].source_url
    )
    assert by_type[OrganizationType.PSYCHIATRY].verification_status == (
        "needs_review"
    )
    assert all(
        item.verification_status == "auto_found"
        for item in outcome.organizations
        if item.organization_type is not OrganizationType.PSYCHIATRY
    )


def test_free_search_queries_do_not_contain_private_address_parts():
    backend = FakeBackend()
    captured: list[str] = []
    original = backend.text

    def capture(query, **kwargs):
        captured.append(query)
        return original(query, **kwargs)

    backend.text = capture
    FreeOrganizationSearchService(backend=backend).search(
        _address(),
        tuple(OrganizationType),
    )

    combined = " ".join(captured)
    assert "Соколов" not in combined
    assert "Комсомольская" not in combined
    assert "16" not in combined
    assert "9" not in combined


def test_free_search_rejects_wrong_region_candidate_and_uses_blank_review_header():
    class WrongRegionBackend:
        def text(self, _query, **_kwargs):
            return [
                {
                    "title": "ТИК Красноармейская",
                    "href": "https://example.test/wrong-region",
                    "body": (
                        "Территориальная избирательная комиссия. Адрес: "
                        "429620, Чувашская Республика, с. Красноармейское, "
                        "ул. Ленина, д. 35"
                    ),
                }
            ]

    outcome = FreeOrganizationSearchService(
        backend=WrongRegionBackend()
    ).search(_address(), (OrganizationType.ELECTION_COMMISSION,))

    assert len(outcome.organizations) == 1
    assert outcome.organizations[0].verification_status == "needs_review"
    assert outcome.organizations[0].postal_address == ""
    assert "ТИК" not in outcome.organizations[0].recipient
    assert outcome.unresolved_types == (
        OrganizationType.ELECTION_COMMISSION,
    )


def test_free_search_always_returns_review_placeholder_when_nothing_found():
    class EmptyBackend:
        def text(self, _query, **_kwargs):
            return []

    outcome = FreeOrganizationSearchService(backend=EmptyBackend()).search(
        _address(),
        (OrganizationType.HOSPITAL,),
    )

    assert len(outcome.organizations) == 1
    hospital = outcome.organizations[0]
    assert hospital.organization_type is OrganizationType.HOSPITAL
    assert hospital.verification_status == "needs_review"
    assert hospital.email == ""
    assert hospital.postal_address == ""
    assert "ТРЕБУЕТ ПРОВЕРКИ" not in hospital.header
    assert outcome.unresolved_types == (OrganizationType.HOSPITAL,)


def test_combined_psychoneurological_unit_resolves_psychiatry_and_narcology():
    class CombinedMedicalBackend:
        def text(self, query, **_kwargs):
            if not any(
                marker in query.casefold()
                for marker in (
                    "нарколог",
                    "психиатр",
                    "психоневролог",
                )
            ):
                return []
            return [
                {
                    "title": (
                        "ГБУЗ МО «Раменская больница» — "
                        "психоневрологическое диспансерное отделение"
                    ),
                    "href": "https://ramenskaya.example/department",
                    "body": (
                        "Психиатрическая и наркологическая помощь. "
                        "Адрес: 140100, Московская область, г. Раменское, "
                        "ул. Мира, д. 12/1 тел.: +7 (496) 463-54-21 "
                        "email: info@ramenskaya.example"
                    ),
                }
            ]

    outcome = FreeOrganizationSearchService(
        backend=CombinedMedicalBackend()
    ).search(
        _ramensky_address(),
        (OrganizationType.NARCOLOGY, OrganizationType.PSYCHIATRY),
    )

    assert not outcome.unresolved_types
    assert len(outcome.organizations) == 2
    by_type = {item.organization_type: item for item in outcome.organizations}
    assert all(
        item.verification_status == "auto_found"
        for item in outcome.organizations
    )
    assert by_type[OrganizationType.NARCOLOGY].postal_address.endswith("12/1")
    assert by_type[OrganizationType.PSYCHIATRY].postal_address.endswith("12/1")
    assert by_type[OrganizationType.PSYCHIATRY].recipient == (
        "Главному врачу\nГБУЗ МО «Раменская больница»"
    )
    assert by_type[OrganizationType.NARCOLOGY].recipient == (
        "Главному врачу\nГБУЗ МО «Раменская больница»"
    )


def test_contact_lists_are_limited_to_two_phones():
    phones = FreeOrganizationSearchService._phones(
        [
            "тел.: +7 (495) 111-11-11, +7 (495) 222-22-22, "
            "+7 (495) 333-33-33"
        ]
    )

    assert phones == (
        "+7 (495) 111-11-11",
        "+7 (495) 222-22-22",
    )


def test_region_only_is_not_accepted_as_a_postal_address():
    class RegionOnlyBackend:
        def text(self, _query, **_kwargs):
            return [
                {
                    "title": "Контакты - ТФОМС МО",
                    "href": "https://example.test/tfoms",
                    "body": "Адрес: Московская область тел.: +7 (495) 111-11-11",
                }
            ]

    outcome = FreeOrganizationSearchService(
        backend=RegionOnlyBackend()
    ).search(_ramensky_address(), (OrganizationType.TFOMS,))

    assert outcome.organizations[0].postal_address == ""
    assert outcome.organizations[0].verification_status == "needs_review"


def test_street_and_house_without_postal_index_require_review():
    class NoIndexBackend:
        def text(self, _query, **_kwargs):
            return [{
                "title": "ГБУЗ «Раменская больница»",
                "href": "https://ramcrb.example/contacts",
                "body": (
                    "Адрес: Московская область, г. Раменское, "
                    "ул. Махова, д. 14 тел.: +7 (496) 463-30-21 "
                    "email: kanc@ramcrb.ru"
                ),
            }]

    outcome = FreeOrganizationSearchService(
        backend=NoIndexBackend()
    ).search(_ramensky_address(), (OrganizationType.HOSPITAL,))

    assert outcome.organizations[0].postal_address == (
        "Московская область, г. Раменское, ул. Махова, д. 14"
    )
    assert outcome.organizations[0].verification_status == "needs_review"
    assert "почтовый индекс" in outcome.organizations[0].verification_note


def test_wrong_district_medical_page_is_skipped_even_if_locality_name_matches():
    class WrongThenCorrectBackend:
        def text(self, _query, **_kwargs):
            return [
                {
                    "title": "Главному врачу",
                    "href": "https://gkbru.ru/dmtr/otdelenie-ramenskij-pb5",
                    "body": (
                        'ГБУЗ МО "Психиатрическая больница №5". '
                        "Адрес: Московская область, Дмитровский городской округ, "
                        "пос. Раменский, ул. Больничная, д. 6. "
                        "Электронная почта: mopb5@mail.ru. "
                        "Головная организация: ГБУЗ МО «ПБ №5» "
                        "тел.: +7 (496) 218-00-14"
                    ),
                },
                {
                    "title": (
                        "Психиатрическое отделение — "
                        "ГБУЗ МО «Раменская больница»"
                    ),
                    "href": "https://ramcrb.example/psychiatry",
                    "body": (
                        "Адрес: 140100, Московская область, "
                        "Раменский городской округ, г. Раменское, "
                        "ул. Мира, д. 12/1 тел.: +7 (498) 602-00-61 "
                        "email: kanc@ramcrb.ru"
                    ),
                },
            ]

    outcome = FreeOrganizationSearchService(
        backend=WrongThenCorrectBackend()
    ).search(_ramensky_address(), (OrganizationType.PSYCHIATRY,))

    psychiatry = outcome.organizations[0]
    assert psychiatry.source_url == "https://ramcrb.example/psychiatry"
    assert psychiatry.postal_address.startswith("140100")
    assert "Дмитровск" not in psychiatry.recipient


def test_no_index_medical_address_does_not_leak_into_recipient():
    class ScreenshotBackend:
        def text(self, _query, **_kwargs):
            return [{
                "title": "Главному врачу",
                "href": "https://example.test/ramensky-psychiatry",
                "body": (
                    'ГБУЗ МО "Раменская психиатрическая больница". '
                    "Адрес: Московская область, Раменский городской округ, "
                    "г. Раменское, ул. Мира, д. 12/1. "
                    "Электронная почта: kanc@example.test. "
                    "Головная организация: ГБУЗ МО «Раменская больница» "
                    "тел.: +7 (496) 463-54-21"
                ),
            }]

    outcome = FreeOrganizationSearchService(
        backend=ScreenshotBackend()
    ).search(_ramensky_address(), (OrganizationType.PSYCHIATRY,))

    psychiatry = outcome.organizations[0]
    assert psychiatry.postal_address.endswith("д. 12/1")
    assert psychiatry.verification_status == "needs_review"
    assert "Адрес:" not in psychiatry.recipient
    assert "Электронная почта" not in psychiatry.recipient
    assert "Головная организация" not in psychiatry.recipient


def test_reviews_and_news_are_never_used_as_header_sources():
    service = FreeOrganizationSearchService(backend=FakeBackend())

    assert not service._source_is_usable(service._hit_from_result(
        {
            "title": "Психоневрологическое отделение: отзывы",
            "href": "https://pravda-klientov.ru/company/example",
            "body": "Отзывы посетителей",
        },
        _ramensky_address(),
        OrganizationType.PSYCHIATRY,
        0,
    ))
    assert not service._source_is_usable(service._hit_from_result(
        {
            "title": "Раменская ЦРБ напоминает о правилах гигиены",
            "href": "https://ramnews.ru/example",
            "body": "Новостная публикация",
        },
        _ramensky_address(),
        OrganizationType.HOSPITAL,
        0,
    ))


def test_required_phone_and_email_control_verification_status():
    class MissingContactsBackend:
        def text(self, query, **_kwargs):
            if "больниц" in query.casefold():
                return [{
                    "title": "ГБУЗ «Раменская больница»",
                    "href": "https://ramcrb.example/contacts",
                    "body": (
                        "Адрес: 140100, Московская область, г. Раменское, "
                        "ул. Махова, д. 14"
                    ),
                }]
            return []

    outcome = FreeOrganizationSearchService(
        backend=MissingContactsBackend()
    ).search(_ramensky_address(), (OrganizationType.HOSPITAL,))

    hospital = outcome.organizations[0]
    assert hospital.verification_status == "needs_review"
    assert "телефон" in hospital.verification_note
    assert "электронную почту" in hospital.verification_note


def test_email_is_optional_only_for_three_military_contact_headers():
    optional = FreeOrganizationSearchService._email_optional_types()

    assert optional == {
        OrganizationType.MILITARY_COMMISSARIAT,
        OrganizationType.MILITARY_COMMANDANT,
        OrganizationType.CONTRACT_SERVICE_POINT,
    }
