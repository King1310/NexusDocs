import pytest

from services.google_single_organization_search_service import (
    GoogleSingleOrganizationResponseError,
    GoogleSingleOrganizationSearchService,
)
from services.request_catalog import REQUEST_CATALOG


def _template(slug: str):
    return next(item for item in REQUEST_CATALOG if item.slug == slug)


def _request():
    return GoogleSingleOrganizationSearchService.build_request(
        _template("hospital"),
        "425 ВКГ",
        "Подольск, Московская область",
    )


def _answer(*, email: str = "hospital@example.ru") -> str:
    return f"""[[NEXUSDOCS_BEGIN]]
[[NEXUSDOCS_HEADER]]
[[NEXUSDOCS_RECIPIENT]]Главному врачу
ФГБУ «425 военный клинический госпиталь» Минобороны России
[[NEXUSDOCS_ADDRESS]]142110, Московская область, г. Подольск, ул. Госпитальная, д. 1
[[NEXUSDOCS_PHONE]]+7 (4967) 55-11-22, 8 (800) 100-20-30, +7 (495) 999-88-77
[[NEXUSDOCS_EMAIL]]{email}
[[NEXUSDOCS_END]]"""


def test_build_request_searches_named_organization_not_territory():
    request = _request()

    assert request.organization_name == "425 ВКГ"
    assert request.location_hint == "Подольск, Московская область"
    assert request.template_slug == "hospital"
    assert 'одной конкретной организации: "425 ВКГ"' in request.prompt
    assert "только подсказка для различения" in request.prompt
    assert "не считай её адресом организации" in request.prompt
    assert "Не подменяй её другой организацией" in request.prompt
    assert "полный почтовый адрес организации с шестизначным индексом" in request.prompt
    assert "один или максимум два опубликованных телефона" in request.prompt
    assert "электронная почта, если она опубликована" in request.prompt
    assert "ФИО любых людей не указывай" in request.prompt
    assert "Никакого текста до, после или между полями" in request.prompt
    assert "[[NEXUSDOCS_HEADER]]" in request.prompt


def test_build_request_requires_organization_name():
    with pytest.raises(ValueError, match="название организации"):
        GoogleSingleOrganizationSearchService.build_request(
            _template("hospital"),
            "   ",
        )


def test_parser_returns_one_structured_header_and_limits_phones():
    result = GoogleSingleOrganizationSearchService.parse_response(
        _answer(),
        _request(),
    )

    assert result.template_slug == "hospital"
    assert result.lookup_name == "425 ВКГ"
    assert result.recipient == (
        "Главному врачу\n"
        "ФГБУ «425 военный клинический госпиталь» Минобороны России"
    )
    assert result.postal_address == (
        "142110, Московская область, г. Подольск, "
        "ул. Госпитальная, д. 1"
    )
    assert result.phones == (
        "+7 (4967) 55-11-22",
        "8 (800) 100-20-30",
    )
    assert result.email == "hospital@example.ru"
    assert result.verification_status == "auto_found"
    assert result.header.endswith("эл. почта: hospital@example.ru")


def test_parser_allows_unpublished_email_but_marks_result_for_review():
    result = GoogleSingleOrganizationSearchService.parse_response(
        _answer(email=""),
        _request(),
    )

    assert result.email == ""
    assert result.verification_status == "needs_review"
    assert "электронная почта" in result.verification_note


def test_parser_ignores_echoed_prompt_protocol_and_uses_last_real_answer():
    request = _request()
    browser_page = request.prompt + "\n\nОтвет Google:\n" + _answer()

    result = GoogleSingleOrganizationSearchService.parse_response(
        browser_page,
        request,
    )

    assert result.postal_address.startswith("142110")
    assert result.phones[0] == "+7 (4967) 55-11-22"
    assert GoogleSingleOrganizationSearchService.has_completed_answer(
        browser_page
    )


def test_echoed_prompt_alone_is_not_a_completed_answer():
    request = _request()

    assert not GoogleSingleOrganizationSearchService.has_completed_answer(
        request.prompt
    )


def test_parser_accepts_flattened_markers_and_web_typography():
    response = " ".join(_answer().splitlines())
    response = response.replace(
        "[[NEXUSDOCS_END]]",
        "[[NEXUSDOCS_\u2060END]]",
    ).replace("55-11-22", "55‑11‑22")

    result = GoogleSingleOrganizationSearchService.parse_response(
        response,
        _request(),
    )

    assert result.recipient.startswith("Главному врачу\nФГБУ")
    assert result.phones[0] == "+7 (4967) 55-11-22"
    assert result.email == "hospital@example.ru"


def test_parser_rejects_header_without_postal_index():
    response = _answer().replace("142110, ", "")

    with pytest.raises(
        GoogleSingleOrganizationResponseError,
        match="почтовый адрес с индексом",
    ):
        GoogleSingleOrganizationSearchService.parse_response(
            response,
            _request(),
        )


def test_parser_waits_for_end_of_latest_answer_not_prompt_end_marker():
    request = _request()
    unfinished = request.prompt + "\n" + _answer().replace(
        "[[NEXUSDOCS_END]]",
        "",
    )

    with pytest.raises(
        GoogleSingleOrganizationResponseError,
        match="ещё не завершён",
    ):
        GoogleSingleOrganizationSearchService.parse_response(
            unfinished,
            request,
        )
