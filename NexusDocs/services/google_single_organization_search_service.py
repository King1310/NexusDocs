from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from domain.enums.organization_type import OrganizationType
from services.request_catalog import RequestTemplate


_BEGIN_MARKER = "[[NEXUSDOCS_BEGIN]]"
_END_MARKER = "[[NEXUSDOCS_END]]"
_HEADER_MARKER = "[[NEXUSDOCS_HEADER]]"
_FIELD_NAMES = ("RECIPIENT", "ADDRESS", "PHONE", "EMAIL")
_FIELD_MARKER_PATTERN = re.compile(
    r"\[\[\s*NEXUSDOCS\s*_\s*(RECIPIENT|ADDRESS|PHONE|EMAIL)\s*\]\]",
    re.IGNORECASE,
)
_POSTAL_INDEX_PATTERN = re.compile(r"(?<!\d)\d{6}(?!\d)")
_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+7|8)[\s\-(]*(?:\d[\s\-()]*?){9,10}(?!\d)"
)
_EMAIL_PATTERN = re.compile(
    r"(?<![\w.-])[\w.+-]+@[\w.-]+\.[A-Za-zА-Яа-я]{2,}(?![\w.-])"
)


class GoogleSingleOrganizationResponseError(ValueError):
    """Google AI did not return one safely readable organization header."""


@dataclass(slots=True, frozen=True)
class GoogleSingleOrganizationSearchRequest:
    prompt: str
    template_number: int
    template_slug: str
    template_title: str
    organization_type: OrganizationType | None
    organization_name: str
    location_hint: str = ""


@dataclass(slots=True, frozen=True)
class GoogleSingleOrganizationHeader:
    """One header found for a user-selected organization."""

    template_number: int
    template_slug: str
    lookup_name: str
    recipient: str
    postal_address: str
    phones: tuple[str, ...] = ()
    email: str = ""
    source_url: str = "https://www.google.com/search?udm=50"
    verification_status: str = "auto_found"
    verification_note: str = ""

    @property
    def header(self) -> str:
        parts = [self.recipient.strip(), self.postal_address.strip()]
        if self.phones:
            parts.append("тел.: " + ",\n".join(self.phones))
        if self.email:
            parts.append(f"эл. почта: {self.email}")
        return "\n\n".join(part for part in parts if part)


class GoogleSingleOrganizationSearchService:
    """Build and parse a Google AI request for one named organization.

    This protocol is intentionally separate from the territory-based search
    for nine standard headers.  The organization name is the search target;
    an optional city or region is only a disambiguation hint.
    """

    BEGIN_MARKER = _BEGIN_MARKER
    END_MARKER = _END_MARKER
    HEADER_MARKER = _HEADER_MARKER

    @classmethod
    def build_request(
        cls,
        template: RequestTemplate,
        organization_name: str,
        location_hint: str = "",
    ) -> GoogleSingleOrganizationSearchRequest:
        name = " ".join(str(organization_name).split()).strip()
        if not name:
            raise ValueError("Укажите название организации для поиска.")
        location = " ".join(str(location_hint).split()).strip(" ,")
        location_instruction = (
            f'Для уточнения поиска используй город или регион: "{location}". '
            "Это только подсказка для различения одноимённых организаций, "
            "не считай её адресом организации."
            if location
            else (
                "Город или регион не указан. Не придумывай территориальную "
                "привязку: установи её по официальным данным организации."
            )
        )
        category = template.organization_type.value if template.organization_type else template.title
        prompt = f'''Найди реквизиты одной конкретной организации: "{name}".

Категория будущего документа: "{category}". {location_instruction}

Название выше — поисковый запрос, а не готовая шапка и не адрес. Найди именно эту организацию, проверь сведения прежде всего по её официальному сайту, официальному сайту учредителя или государственному порталу. Не подменяй её другой организацией, которая лишь относится к той же территории.

Верни одну готовую шапку: первая строка — обращение к руководителю без ФИО, со следующей строки — полное официальное название организации; затем собственный полный почтовый адрес организации с шестизначным индексом; один или максимум два опубликованных телефона; электронная почта, если она опубликована. ФИО любых людей не указывай. Не придумывай отсутствующие реквизиты. Не пиши пояснения, предупреждения, степень уверенности, статус и ссылки.

Ответ только в таком машинном формате, метки напиши буквально:
[[NEXUSDOCS_BEGIN]]
[[NEXUSDOCS_HEADER]]
[[NEXUSDOCS_RECIPIENT]]обращение к руководителю без ФИО, затем с новой строки полное название организации
[[NEXUSDOCS_ADDRESS]]полный собственный адрес организации с шестизначным индексом
[[NEXUSDOCS_PHONE]]один или максимум два опубликованных телефона
[[NEXUSDOCS_EMAIL]]опубликованная электронная почта или пустое поле
[[NEXUSDOCS_END]]

Никакого текста до, после или между полями не добавляй.'''
        return GoogleSingleOrganizationSearchRequest(
            prompt=prompt,
            template_number=template.number,
            template_slug=template.slug,
            template_title=template.title,
            organization_type=template.organization_type,
            organization_name=name,
            location_hint=location,
        )

    @classmethod
    def parse_response(
        cls,
        response_text: str,
        request: GoogleSingleOrganizationSearchRequest,
    ) -> GoogleSingleOrganizationHeader:
        text = cls._clean_text(response_text)
        if _BEGIN_MARKER in text and not cls._has_end_after_last_field(text):
            raise GoogleSingleOrganizationResponseError(
                "Ответ Google AI ещё не завершён."
            )

        candidates = cls._field_groups(text)
        if not candidates:
            raise GoogleSingleOrganizationResponseError(
                "Google AI должен вернуть одну шапку в полях "
                "RECIPIENT, ADDRESS, PHONE, EMAIL."
            )

        last_error: GoogleSingleOrganizationResponseError | None = None
        for values in reversed(candidates):
            try:
                return cls._build_header(values, request)
            except GoogleSingleOrganizationResponseError as error:
                last_error = error
        if last_error is not None:
            raise last_error
        raise GoogleSingleOrganizationResponseError(
            "В ответе Google AI не найдена готовая шапка."
        )

    @classmethod
    def has_completed_answer(cls, value: str) -> bool:
        """Return true only for a completed, parseable real answer.

        Google may expose the echoed prompt in the same page.  The example in
        that prompt has the same markers but no real postal index or phone, so
        it is deliberately not treated as a completed answer.
        """

        text = cls._clean_text(value)
        if not cls._has_end_after_last_field(text):
            return False
        for values in reversed(cls._field_groups(text)):
            if (
                values["RECIPIENT"].strip()
                and _POSTAL_INDEX_PATTERN.search(values["ADDRESS"])
            ):
                return True
        return False

    @classmethod
    def _build_header(
        cls,
        values: dict[str, str],
        request: GoogleSingleOrganizationSearchRequest,
    ) -> GoogleSingleOrganizationHeader:
        recipient_lines = [
            cls._clean_line(line)
            for line in values["RECIPIENT"].splitlines()
            if cls._clean_line(line)
        ]
        recipient = "\n".join(recipient_lines)
        recipient = cls._normalize_recipient_layout(
            recipient,
            request.organization_type,
        )
        postal_address = " ".join(values["ADDRESS"].split()).strip(" ,;.")
        phones = cls._phones(values["PHONE"])
        email_text = cls._normalized_email_text(values["EMAIL"])
        email_match = _EMAIL_PATTERN.search(email_text)
        email = email_match.group(0) if email_match else ""

        if not recipient:
            raise GoogleSingleOrganizationResponseError(
                "Google AI не указал адресата и название организации."
            )
        if not _POSTAL_INDEX_PATTERN.search(postal_address):
            raise GoogleSingleOrganizationResponseError(
                "Google AI не указал полный почтовый адрес с индексом."
            )

        missing = []
        if not phones:
            missing.append("телефон")
        if not email:
            missing.append("электронная почта")
        status = "needs_review" if missing else "auto_found"
        note = (
            "Найдена указанная организация; вручную проверьте: "
            + ", ".join(missing)
            + "."
            if missing
            else "Шапка конкретной организации найдена Google AI Mode."
        )
        return GoogleSingleOrganizationHeader(
            template_number=request.template_number,
            template_slug=request.template_slug,
            lookup_name=request.organization_name,
            recipient=recipient,
            postal_address=postal_address,
            phones=phones,
            email=email,
            verification_status=status,
            verification_note=note,
        )

    @classmethod
    def _field_groups(cls, text: str) -> list[dict[str, str]]:
        matches = list(_FIELD_MARKER_PATTERN.finditer(text))
        groups: list[dict[str, str]] = []
        for index in range(0, len(matches) - len(_FIELD_NAMES) + 1):
            window = matches[index:index + len(_FIELD_NAMES)]
            names = tuple(match.group(1).upper() for match in window)
            if names != _FIELD_NAMES:
                continue
            values: dict[str, str] = {}
            for offset, match in enumerate(window):
                next_match = (
                    window[offset + 1]
                    if offset + 1 < len(window)
                    else None
                )
                end = next_match.start() if next_match is not None else len(text)
                if next_match is None:
                    closing = text.find(_END_MARKER, match.end())
                    next_recipient = _FIELD_MARKER_PATTERN.search(text, match.end())
                    boundaries = [
                        position
                        for position in (
                            closing,
                            next_recipient.start() if next_recipient else -1,
                        )
                        if position >= 0
                    ]
                    if boundaries:
                        end = min(boundaries)
                values[match.group(1).upper()] = text[match.end():end].strip()
            groups.append(values)
        return groups

    @staticmethod
    def _has_end_after_last_field(text: str) -> bool:
        fields = list(_FIELD_MARKER_PATTERN.finditer(text))
        if not fields:
            return False
        return text.find(_END_MARKER, fields[-1].end()) >= 0

    @staticmethod
    def _clean_text(value: str) -> str:
        normalized: list[str] = []
        for character in str(value):
            category = unicodedata.category(character)
            if category == "Cf":
                continue
            if category == "Zs":
                normalized.append(" ")
            elif category == "Pd" or character == "−":
                normalized.append("-")
            elif character == "＋":
                normalized.append("+")
            else:
                normalized.append(character)
        text = "".join(normalized).replace("\r\n", "\n").replace("\r", "\n")
        markers = {
            "BEGIN": _BEGIN_MARKER,
            "END": _END_MARKER,
            "HEADER": _HEADER_MARKER,
            **{
                name: f"[[NEXUSDOCS_{name}]]"
                for name in _FIELD_NAMES
            },
        }
        for name, canonical in markers.items():
            text = re.sub(
                rf"\[\[\s*NEXUSDOCS\s*_\s*{name}\s*\]\]",
                canonical,
                text,
                flags=re.IGNORECASE,
            )
        return text

    @staticmethod
    def _clean_line(value: str) -> str:
        value = value.strip()
        value = re.sub(r"^\s*(?:[-*•]\s+)", "", value)
        value = value.replace("**", "").replace("__", "").replace("`", "")
        return " ".join(value.split()).strip()

    @classmethod
    def _normalize_recipient_layout(
        cls,
        value: str,
        organization_type: OrganizationType | None,
    ) -> str:
        formatted = value.strip()
        if not formatted:
            return ""
        if "\n" not in formatted and "," in formatted:
            first, remainder = (part.strip() for part in formatted.split(",", 1))
            if remainder and cls._looks_like_salutation(first):
                formatted = f"{first}\n{remainder}"
        required_salutation = {
            OrganizationType.MILITARY_COMMISSARIAT: "Военному комиссару",
            OrganizationType.MILITARY_COMMANDANT: "Военному коменданту",
            OrganizationType.NARCOLOGY: "Главному врачу",
            OrganizationType.PSYCHIATRY: "Главному врачу",
            OrganizationType.HOSPITAL: "Главному врачу",
            OrganizationType.TFOMS: "Директору",
            OrganizationType.ADMINISTRATION: "Главе",
            OrganizationType.CONTRACT_SERVICE_POINT: "Начальнику",
            OrganizationType.ELECTION_COMMISSION: "Председателю",
        }.get(organization_type)
        if required_salutation is None:
            return formatted
        if "\n" not in formatted:
            normalized = formatted.casefold().replace("ё", "е")
            salutation = required_salutation.casefold().replace("ё", "е")
            if normalized.startswith(salutation + " "):
                formatted = (
                    required_salutation
                    + "\n"
                    + formatted[len(required_salutation):].strip(" ,")
                )
        lines = [line.strip() for line in formatted.splitlines() if line.strip()]
        if len(lines) >= 2:
            lines[0] = required_salutation
            return "\n".join(lines)
        return formatted

    @staticmethod
    def _looks_like_salutation(value: str) -> bool:
        normalized = value.casefold().replace("ё", "е")
        endings = (
            "командиру",
            "руководителю",
            "начальнику",
            "директору",
            "председателю",
            "главе",
            "главному врачу",
            "военному комиссару",
            "военному коменданту",
            "заведующему",
            "заведующей",
        )
        return any(normalized.endswith(ending) for ending in endings)

    @classmethod
    def _phones(cls, value: str) -> tuple[str, ...]:
        phones: list[str] = []
        normalized = cls._clean_text(value)
        matches = list(_PHONE_PATTERN.finditer(normalized))
        if not matches:
            matches = list(
                re.finditer(
                    r"(?<!\d)(?:\+\s*7|8)(?:[^\d\n]*\d){10}(?!\d)",
                    normalized,
                )
            )
        for match in matches:
            phone = " ".join(match.group(0).split()).strip(" ,;.")
            if phone not in phones:
                phones.append(phone)
        return tuple(phones[:2])

    @classmethod
    def _normalized_email_text(cls, value: str) -> str:
        text = cls._clean_text(value)
        text = text.replace("\\@", "@").replace("\\.", ".")
        text = re.sub(r"\s*@\s*", "@", text)
        return re.sub(r"(?<=\w)\s*\.\s*(?=\w)", ".", text)


__all__ = (
    "GoogleSingleOrganizationHeader",
    "GoogleSingleOrganizationResponseError",
    "GoogleSingleOrganizationSearchRequest",
    "GoogleSingleOrganizationSearchService",
)
