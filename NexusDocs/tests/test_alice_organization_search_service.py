from dataclasses import replace
import re

import pytest

from domain.enums.organization_type import OrganizationType
from domain.value_objects.address import Address
from services.alice_organization_search_service import (
    AliceOrganizationSearchService,
    AliceResponseError,
)
from services.generation_service import GenerationService


def _address() -> Address:
    return Address(
        region="Республика Карелия",
        district="Костомукшский городской округ",
        city="г. Костомукша",
        locality="",
        street="ул. Советская",
        house="12",
        apartment="45",
    )


def _alice_answer() -> str:
    return """Служебный текст страницы
[[NEXUSDOCS_BEGIN]]
1)
Военному комиссару
Военного комиссариата
Костомукшского городского округа Республики Карелия

186930, Республика Карелия, г. Костомукша, ул. Антикайнена, д. 1
тел.: +7 (81459) 5-11-11

2)
Военному коменданту
Военной комендатуры
Петрозаводского гарнизона

185001, Республика Карелия, г. Петрозаводск, ул. Военная, д. 2
тел.: +7 (8142) 55-22-11

3)
Главному врачу
ГБУЗ Республики Карелия
«Межрайонная больница № 1»
Поликлиника
Наркологический кабинет

186930, Республика Карелия,
г. Костомукша, ул. Советская, д. 12
тел.: +7 (81459) 5-15-57,
+7 (981) 408-03-08
эл. почта: kospol078@mail.ru

4)
Главному врачу
ГБУЗ Республики Карелия «Республиканская психиатрическая больница»

185000, Республика Карелия, г. Петрозаводск, ул. Мира, д. 4
тел.: +7 (8142) 44-44-44
эл. почта: psy@example.ru

5)
Главному врачу
ГБУЗ Республики Карелия «Межрайонная больница № 1»

186930, Республика Карелия, г. Костомукша, ул. Советская, д. 12
тел.: +7 (81459) 5-10-10
эл. почта: hospital@example.ru

6)
Директору
Территориального фонда
обязательного медицинского страхования
Республики Карелия

185000, Республика Карелия, г. Петрозаводск, ул. Ленина, д. 10
тел.: +7 (8142) 33-33-33
эл. почта: tfoms@example.ru

7)
Главе
Костомукшского городского округа

186930, Республика Карелия, г. Костомукша, ул. Строителей, д. 5
тел.: +7 (81459) 5-20-20
эл. почта: admin@example.ru

8)
Начальнику
Пункта отбора
на военную службу по контракту
Республики Карелия

185000, Республика Карелия, г. Петрозаводск, ул. Военная, д. 8
тел.: +7 (8142) 55-55-55

9)
Председателю
Территориальной избирательной комиссии
Костомукшского городского округа

186930, Республика Карелия, г. Костомукша, ул. Строителей, д. 5
тел.: +7 (81459) 5-30-30
эл. почта: tik@example.ru
[[NEXUSDOCS_END]]
Подвал страницы"""


def _tagged_answer() -> str:
    legacy = AliceOrganizationSearchService.parse_response(_alice_answer())
    chunks = ["[[NEXUSDOCS_BEGIN]]"]
    for number, organization in enumerate(legacy.organizations, start=1):
        chunks.extend(
            (
                f"[[NEXUSDOCS_HEADER_{number}]]",
                "[[NEXUSDOCS_RECIPIENT]]" + organization.recipient,
                "[[NEXUSDOCS_ADDRESS]]" + organization.postal_address,
                "[[NEXUSDOCS_PHONE]]" + ", ".join(organization.phones),
                "[[NEXUSDOCS_EMAIL]]" + organization.email,
            )
        )
    chunks.append("[[NEXUSDOCS_END]]")
    return "\n".join(chunks)


def test_prompt_uses_address_without_apartment_and_demands_nine_headers():
    request = AliceOrganizationSearchService.build_request(_address())

    assert "д. 12" in request.public_address
    assert "45" not in request.public_address
    assert "Адрес регистрации человека" in request.prompt
    assert "НЕ адрес организаций" in request.prompt
    assert "территориально отвечают за этот адрес" in request.prompt
    assert "официальным источникам" in request.prompt
    assert "собственные официальные реквизиты" in request.prompt
    assert "ФИО людей не пиши" in request.prompt
    assert "Для 3, 4, 5, 6, 7 и 9 почта обязательна" in request.prompt
    assert "Электронную почту обязательно ИЩИ для всех девяти" in request.prompt
    assert "не пропускай поиск почты" in request.prompt
    assert "пусто только для 1, 2 и 8" in request.prompt
    assert "ГБУЗ, ГАУЗ, ГКБ, ЦРБ, ЦГБ, КОБ, ОКБ" in request.prompt
    assert "Телефон обязателен во всех девяти шапках" in request.prompt
    assert "Нужно ровно 9 шапок" in request.prompt
    assert "[[NEXUSDOCS_BEGIN]]" in request.prompt
    assert "[[NEXUSDOCS_END]]" in request.prompt
    assert "Не используй Markdown-нумерацию" in request.prompt
    assert "[[NEXUSDOCS_HEADER_1]]" in request.prompt
    assert "[[NEXUSDOCS_RECIPIENT]]" in request.prompt
    assert "[[NEXUSDOCS_ADDRESS]]" in request.prompt
    assert "[[NEXUSDOCS_PHONE]]" in request.prompt
    assert "[[NEXUSDOCS_EMAIL]]" in request.prompt


def test_completed_marker_ignores_invisible_web_characters():
    text = "ответ\n[[NEXUSDOCS_\u2060END]]\n"

    assert AliceOrganizationSearchService.has_completed_answer(text)


def test_contacts_accept_alice_clipboard_typography():
    contact_text = (
        "тел.: +7\u202f(496)\u202f542‑05‑51, +7 (496) 542−16−16\n"
        "эл. почта: spcgb\\@mail . ru"
    )

    assert AliceOrganizationSearchService._phones(contact_text) == (
        "+7 (496) 542-05-51",
        "+7 (496) 542-16-16",
    )
    normalized_email = AliceOrganizationSearchService._normalized_email_text(
        contact_text
    )
    assert "spcgb@mail.ru" in normalized_email


def test_google_inline_recipient_is_split_into_template_lines():
    value = "Главному врачу, ГБУЗ «Городская больница»"

    assert AliceOrganizationSearchService._normalize_recipient_layout(value) == (
        "Главному врачу\nГБУЗ «Городская больница»"
    )

    flattened = "Главному врачу ГБУЗ «Городская больница»"
    assert AliceOrganizationSearchService._normalize_recipient_layout(
        flattened,
        OrganizationType.HOSPITAL,
    ) == "Главному врачу\nГБУЗ «Городская больница»"

    assert AliceOrganizationSearchService._normalize_recipient_layout(
        "Директору\nГБУЗ «Наркологический диспансер»",
        OrganizationType.NARCOLOGY,
    ) == "Главному врачу\nГБУЗ «Наркологический диспансер»"


def test_google_military_recipient_drops_repeated_organization_prefix():
    commissariat = (
        "Военному комиссару\n"
        "Военного комиссариата\n"
        "Военный комиссариат города Миасс Челябинской области"
    )
    commandant = (
        "Военному коменданту\n"
        "Военной комендатуры\n"
        "Военная комендатура гарнизона 1 разряда г. Челябинск"
    )

    assert AliceOrganizationSearchService._normalize_recipient_layout(
        commissariat,
        OrganizationType.MILITARY_COMMISSARIAT,
    ) == (
        "Военному комиссару\n"
        "Военного комиссариата\n"
        "города Миасс Челябинской области"
    )
    assert AliceOrganizationSearchService._normalize_recipient_layout(
        commandant,
        OrganizationType.MILITARY_COMMANDANT,
    ) == (
        "Военному коменданту\n"
        "Военной комендатуры\n"
        "гарнизона 1 разряда г. Челябинск"
    )


def test_parser_builds_all_nine_organizations_in_protocol_order():
    outcome = AliceOrganizationSearchService.parse_response(_alice_answer())

    assert len(outcome.organizations) == 9
    assert outcome.unresolved_types == ()
    assert tuple(item.organization_type for item in outcome.organizations) == tuple(
        OrganizationType
    )
    narcology = outcome.organizations[2]
    assert narcology.recipient.endswith("Наркологический кабинет")
    assert narcology.postal_address == (
        "186930, Республика Карелия, г. Костомукша, "
        "ул. Советская, д. 12"
    )
    assert narcology.phones == (
        "+7 (81459) 5-15-57",
        "+7 (981) 408-03-08",
    )
    assert narcology.email == "kospol078@mail.ru"
    rendered = GenerationService._simple_recipient_header(narcology)
    assert "Поликлиника\nНаркологический кабинет" in rendered


def test_parser_accepts_tagged_protocol_even_when_alice_flattens_everything():
    flattened = " ".join(_tagged_answer().splitlines())

    outcome = AliceOrganizationSearchService.parse_response(flattened)

    assert len(outcome.organizations) == 9
    assert outcome.unresolved_types == ()
    assert outcome.organizations[2].recipient.startswith("Главному врачу")
    assert outcome.organizations[2].phones == (
        "+7 (81459) 5-15-57",
        "+7 (981) 408-03-08",
    )
    assert outcome.organizations[8].email == "tik@example.ru"
    assert all(
        item.source_url == "https://www.google.com/search?udm=50"
        for item in outcome.organizations
    )


def test_tagged_blocks_can_be_accumulated_from_virtualized_fragments():
    tagged = _tagged_answer()
    marker = "[[NEXUSDOCS_HEADER_"
    fragments = []
    for start_number, end_number in ((1, 4), (4, 7), (7, 10)):
        start = tagged.index(f"{marker}{start_number}]]")
        if end_number == 10:
            end = tagged.index("[[NEXUSDOCS_END]]")
        else:
            end = tagged.index(f"{marker}{end_number}]]")
        fragments.append(tagged[start:end])

    collected: dict[int, str] = {}
    for fragment in fragments:
        collected.update(
            AliceOrganizationSearchService.extract_complete_tagged_blocks(fragment)
        )

    assembled = AliceOrganizationSearchService.assemble_tagged_blocks(collected)
    outcome = AliceOrganizationSearchService.parse_response(assembled)
    assert len(outcome.organizations) == 9
    assert outcome.organizations[8].email == "tik@example.ru"


def test_tagged_collector_ignores_request_placeholders():
    request = AliceOrganizationSearchService.build_request(_address())

    collected = AliceOrganizationSearchService.extract_complete_tagged_blocks(
        request.prompt
    )

    assert collected == {}


def test_parser_prefers_explicit_text_header_markers():
    marked_response = re.sub(
        r"(?m)^([1-9])\)$",
        lambda match: f"[[NEXUSDOCS_HEADER_{match.group(1)}]]",
        _alice_answer(),
    )

    outcome = AliceOrganizationSearchService.parse_response(marked_response)

    assert len(outcome.organizations) == 9
    assert outcome.organizations[5].organization_type is OrganizationType.TFOMS


def test_address_validation_rejects_copying_subject_address_to_organizations():
    outcome = AliceOrganizationSearchService.parse_response(_alice_answer())
    subject_address = (
        AliceOrganizationSearchService.public_registration_address(_address())
    )
    copied = tuple(
        replace(organization, postal_address=subject_address)
        if index < 4
        else organization
        for index, organization in enumerate(outcome.organizations)
    )
    broken_outcome = type(outcome)(copied, outcome.unresolved_types)

    with pytest.raises(AliceResponseError, match="скопировал адрес субъекта"):
        AliceOrganizationSearchService.validate_outcome_for_address(
            broken_outcome,
            _address(),
        )


def test_parser_ignores_unrelated_numbering_inside_alice_answer():
    response = _alice_answer().replace(
        "2)\nВоенному коменданту",
        "1. дополнительный телефон указан ниже\n\n2)\nВоенному коменданту",
    )

    outcome = AliceOrganizationSearchService.parse_response(response)

    assert len(outcome.organizations) == 9
    assert outcome.organizations[1].organization_type is (
        OrganizationType.MILITARY_COMMANDANT
    )


def test_parser_accepts_browser_page_when_alice_omits_opening_marker():
    answer_without_begin = _alice_answer().replace(
        "[[NEXUSDOCS_BEGIN]]\n",
        "",
        1,
    )
    browser_page = (
        "Текст отправленного запроса [[NEXUSDOCS_BEGIN]] и "
        "[[NEXUSDOCS_END]]\n"
        + answer_without_begin
    )

    outcome = AliceOrganizationSearchService.parse_response(browser_page)

    assert len(outcome.organizations) == 9


def test_parser_splits_html_list_text_when_css_numbers_are_missing():
    response_without_visible_numbers = re.sub(
        r"(?m)^\s*[1-9]\)\s*\n",
        "",
        _alice_answer(),
    )

    outcome = AliceOrganizationSearchService.parse_response(
        response_without_visible_numbers
    )

    assert len(outcome.organizations) == 9
    assert outcome.organizations[0].recipient.startswith("Военному комиссару")
    assert outcome.organizations[8].recipient.startswith("Председателю")


def test_parser_uses_postal_groups_when_css_numbers_and_expected_titles_are_missing():
    response = re.sub(
        r"(?m)^\s*[1-9]\)\s*\n",
        "",
        _alice_answer(),
    )
    response = response.replace("Главному врачу", "Руководителю", 3)

    outcome = AliceOrganizationSearchService.parse_response(response)

    assert len(outcome.organizations) == 9
    assert outcome.organizations[2].postal_address.startswith("186930")
    assert outcome.organizations[8].email == "tik@example.ru"


def test_parser_accepts_alice_flattened_contact_lines_and_inline_end_marker():
    response = re.sub(
        r"(?m)^\s*[1-9]\)\s*\n",
        "",
        _alice_answer(),
    )
    response = re.sub(
        r"\n(?=(?:тел\.?|эл\.?\s*почта)\s*:)",
        " ",
        response,
        flags=re.IGNORECASE,
    )
    response = response.replace("\n[[NEXUSDOCS_END]]", " [[NEXUSDOCS_END]]")

    outcome = AliceOrganizationSearchService.parse_response(response)

    assert len(outcome.organizations) == 9
    assert outcome.organizations[6].phones == ("+7 (81459) 5-20-20",)
    assert outcome.organizations[8].email == "tik@example.ru"
    assert AliceOrganizationSearchService.has_completed_answer(response)


def test_parser_uses_last_complete_recipient_sequence_on_unmarked_chat_page():
    request = AliceOrganizationSearchService.build_request(_address())
    plain_answer = re.sub(
        r"(?m)^\s*[1-9]\)\s*\n",
        "",
        _alice_answer()
        .replace("[[NEXUSDOCS_BEGIN]]", "")
        .replace("[[NEXUSDOCS_END]]", ""),
    )
    chat_page = request.prompt + "\n\n" + plain_answer

    outcome = AliceOrganizationSearchService.parse_response(chat_page)

    assert len(outcome.organizations) == 9
    assert outcome.organizations[0].postal_address.startswith("186930")
    assert outcome.organizations[8].email == "tik@example.ru"


def test_parser_marks_missing_required_email_for_review():
    response = _alice_answer().replace(
        "эл. почта: psy@example.ru",
        "",
    )

    outcome = AliceOrganizationSearchService.parse_response(response)

    assert outcome.unresolved_types == (OrganizationType.PSYCHIATRY,)
    assert outcome.organizations[3].verification_status == "needs_review"


def test_address_parser_rejects_missing_required_contacts():
    response = _alice_answer().replace(
        "тел.: +7 (81459) 5-15-57,\n+7 (981) 408-03-08",
        "",
        1,
    )

    with pytest.raises(AliceResponseError, match="обязательные контакты"):
        AliceOrganizationSearchService.parse_response_for_address(
            response,
            _address(),
        )


def test_parser_waits_for_complete_marked_answer():
    with pytest.raises(AliceResponseError, match="ещё не завершён"):
        AliceOrganizationSearchService.parse_response(
            "[[NEXUSDOCS_BEGIN]]\n1)\nЧерновик"
        )


def test_parser_rejects_missing_section():
    response = re.sub(
        r"(?s)9\)\n.*?\[\[NEXUSDOCS_END\]\]",
        "[[NEXUSDOCS_END]]",
        _alice_answer(),
    )

    with pytest.raises(AliceResponseError, match="девять отдельных"):
        AliceOrganizationSearchService.parse_response(response)
