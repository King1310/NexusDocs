from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from domain.entities.organization import Organization
from domain.enums.organization_type import OrganizationType
from domain.value_objects.address import Address
from services.free_organization_search_service import FreeSearchOutcome


_BEGIN_MARKER = "[[NEXUSDOCS_BEGIN]]"
_END_MARKER = "[[NEXUSDOCS_END]]"
_SECTION_PATTERN = re.compile(
    r"(?m)^\s*(?:#{1,6}\s*)?(?:\*{0,2})?([1-9])\s*[).:]\s*"
)
_HEADER_MARKER_PATTERN = re.compile(
    r"(?m)^\s*\[\[NEXUSDOCS_HEADER_([1-9])\]\]\s*$"
)
_POSTAL_INDEX_PATTERN = re.compile(r"(?<!\d)\d{6}(?!\d)")
_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+7|8)[\s\-(]*(?:\d[\s\-()]*?){9,10}(?!\d)"
)
_EMAIL_PATTERN = re.compile(
    r"(?<![\w.-])[\w.+-]+@[\w.-]+\.[A-Za-zА-Яа-я]{2,}(?![\w.-])"
)
_RECIPIENT_STARTS = (
    re.compile(r"(?im)^\s*военному\s+комиссару\b.*$"),
    re.compile(r"(?im)^\s*военному\s+коменданту\b.*$"),
    re.compile(r"(?im)^\s*главному\s+врачу\b.*$"),
    re.compile(r"(?im)^\s*главному\s+врачу\b.*$"),
    re.compile(r"(?im)^\s*главному\s+врачу\b.*$"),
    re.compile(r"(?im)^\s*директору\b.*$"),
    re.compile(r"(?im)^\s*главе\b.*$"),
    re.compile(r"(?im)^\s*начальнику\b.*$"),
    re.compile(r"(?im)^\s*председателю\b.*$"),
)


class AliceResponseError(ValueError):
    """Alice returned text that cannot be safely split into nine headers."""


@dataclass(slots=True, frozen=True)
class AliceSearchRequest:
    prompt: str
    public_address: str


class AliceOrganizationSearchService:
    """Build a strict Alice AI request and parse its nine dry header blocks."""

    BEGIN_MARKER = _BEGIN_MARKER
    END_MARKER = _END_MARKER

    @classmethod
    def build_request(cls, address: Address) -> AliceSearchRequest:
        public_address = cls.public_registration_address(address)
        prompt = f'''Сделай шапки для организаций, относящихся к этому адресу: "{public_address}"

Важно: указанный адрес — это адрес регистрации субъекта, а не адрес организации. По нему нужно определить организации, которые отвечают за этот адрес и территориально обслуживают зарегистрированного по нему человека. Для каждой организации отдельно найди её собственные официальные реквизиты. Не подставляй адрес субъекта как адрес организации, если интернет-поиск не подтвердил реальное совпадение.

Вот пример готовой шапки:

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

ФИО руководителей и других людей указывать не нужно. Сделай строго по шаблону: кому и название организации, затем полный почтовый адрес с индексом, максимум два телефона и электронная почта. Для военного комиссариата, военной комендатуры и пункта отбора на военную службу по контракту электронную почту можно не указывать. Должности не сокращай. В названиях организаций используй только официальные общепринятые сокращения, чтобы шапки были компактными: например, ГБУЗ, ГАУЗ, ГКБ, ЦРБ, ЦГБ, КОБ, ОКБ. Не придумывай неофициальные сокращения. Не пиши пояснения, предупреждения, степень уверенности и ссылки.

ВАЖНО: для шапок 3, 4, 5, 6, 7 и 9 строка «эл. почта:» обязательна. Если электронная почта ещё не найдена, продолжай интернет-поиск и не завершай ответ. Нельзя пропускать электронную почту сразу во всех шапках. Без электронной почты допускаются только шапки 1, 2 и 8.

ВАЖНО: строка «тел.:» и хотя бы один реальный телефон обязательны во всех девяти шапках без исключений. Можно указать один или максимум два телефона. Если телефон организации ещё не найден, продолжай интернет-поиск и не завершай ответ.

Нужно ровно 9 шапок и строго в этом порядке:

1. в военный комиссариат;
2. в военную комендатуру;
3. в местный наркологический диспансер или кабинет;
4. в местную психиатрическую службу;
5. в центральную районную или главную больницу по этому адресу;
6. в территориальный фонд обязательного медицинского страхования;
7. главе администрации, отвечающей за указанный адрес, без ФИО главы;
8. в пункт отбора на военную службу по контракту;
9. председателю территориальной избирательной комиссии.

Перед строкой [[NEXUSDOCS_END]] обязательно проверь: в ответе должно быть девять строк «тел.:» и минимум шесть строк «эл. почта:» — в шапках 3, 4, 5, 6, 7 и 9.

Начни ответ отдельной строкой [[NEXUSDOCS_BEGIN]], закончи отдельной строкой [[NEXUSDOCS_END]]. Каждую шапку начинай отдельной строкой только с номера вида «1)», «2)» и так далее. После номера сразу с новой строки пиши саму шапку. Никакого текста до, после или между шапками не добавляй.'''
        return AliceSearchRequest(prompt=prompt, public_address=public_address)

    @staticmethod
    def public_registration_address(address: Address) -> str:
        """Return the jurisdiction address without a person's apartment."""

        parts = (
            address.region,
            address.district,
            address.city,
            address.locality,
            address.street,
            f"д. {address.house}" if address.house else "",
        )
        return ", ".join(part.strip() for part in parts if part.strip())

    @classmethod
    def parse_response(cls, response_text: str) -> FreeSearchOutcome:
        text = cls._answer_between_markers(response_text)
        marker_matches = list(_HEADER_MARKER_PATTERN.finditer(text))
        marker_numbers = [int(match.group(1)) for match in marker_matches]
        if marker_numbers == list(range(1, 10)):
            blocks = [
                text[
                    match.end():(
                        marker_matches[index + 1].start()
                        if index + 1 < len(marker_matches)
                        else len(text)
                    )
                ]
                for index, match in enumerate(marker_matches)
            ]
        else:
            blocks = cls._unnumbered_header_blocks(text)
            matches = cls._ordered_header_matches(text)
            if len(blocks) != 9 and len(matches) == 9:
                blocks = [
                    text[
                        match.end():(
                            matches[index + 1].start()
                            if index + 1 < len(matches)
                            else len(text)
                        )
                    ]
                    for index, match in enumerate(matches)
                ]
        if len(blocks) != 9:
            found = [
                int(match.group(1))
                for match in _SECTION_PATTERN.finditer(text)
            ]
            raise AliceResponseError(
                "Алиса должна вернуть девять отдельных шапок. "
                f"Распознаны разделители: {marker_numbers or 'нет'}, "
                f"номера: {found or 'нет'}."
            )

        organizations: list[Organization] = []
        unresolved: list[OrganizationType] = []
        types = tuple(OrganizationType)
        for index, block in enumerate(blocks):
            organization = cls._parse_header_block(types[index], block)
            organizations.append(organization)
            if organization.verification_status == "needs_review":
                unresolved.append(organization.organization_type)

        return FreeSearchOutcome(tuple(organizations), tuple(unresolved))

    @classmethod
    def parse_response_for_address(
        cls,
        response_text: str,
        subject_address: Address,
    ) -> FreeSearchOutcome:
        outcome = cls.parse_response(response_text)
        outcome = cls.validate_outcome_for_address(outcome, subject_address)
        return cls.validate_required_contacts(outcome)

    @classmethod
    def validate_required_contacts(
        cls,
        outcome: FreeSearchOutcome,
    ) -> FreeSearchOutcome:
        """Reject an Alice set that would otherwise open the manual editor."""

        problems: list[str] = []
        email_optional = cls._email_optional_types()
        for organization in outcome.organizations:
            missing: list[str] = []
            if not organization.phones:
                missing.append("телефон")
            if (
                organization.organization_type not in email_optional
                and not organization.email
            ):
                missing.append("электронная почта")
            if missing:
                problems.append(
                    f"{organization.organization_type.value}: "
                    + ", ".join(missing)
                )
        if problems:
            raise AliceResponseError(
                "Алиса не указала обязательные контакты — "
                + "; ".join(problems)
                + ". Повторите поиск: минимум один телефон нужен для "
                "каждой шапки."
            )
        return outcome

    @classmethod
    def validate_outcome_for_address(
        cls,
        outcome: FreeSearchOutcome,
        subject_address: Address,
    ) -> FreeSearchOutcome:
        """Reject the common failure where Alice copies the person's address."""

        normalized_addresses = [
            cls._normalized_address(organization.postal_address)
            for organization in outcome.organizations
        ]
        repeated = max(
            (normalized_addresses.count(value) for value in normalized_addresses),
            default=0,
        )
        subject_copies = sum(
            cls._looks_like_subject_address(
                organization.postal_address,
                subject_address,
            )
            for organization in outcome.organizations
        )
        if repeated >= 4 or subject_copies >= 4:
            raise AliceResponseError(
                "Алиса скопировала адрес субъекта или один и тот же адрес "
                "сразу в несколько организаций. Нужен повторный поиск "
                "собственных реквизитов каждой организации."
            )
        return outcome

    @staticmethod
    def _normalized_address(value: str) -> str:
        return " ".join(
            re.findall(
                r"[а-яёa-z0-9]+",
                value.casefold(),
            )
        )

    @classmethod
    def _looks_like_subject_address(
        cls,
        postal_address: str,
        subject_address: Address,
    ) -> bool:
        normalized = cls._normalized_address(postal_address)
        specific_words = []
        for value in (
            subject_address.city,
            subject_address.locality,
            subject_address.street,
        ):
            specific_words.extend(
                word
                for word in re.findall(r"[а-яёa-z]{4,}", value.casefold())
                if word not in {"город", "улица", "поселок", "посёлок"}
            )
        if not specific_words or not any(word in normalized for word in specific_words):
            return False
        house = re.escape(subject_address.house.strip())
        if not house:
            return False
        return bool(re.search(rf"\b(?:д|дом)\s*{house}\b", normalized))

    @staticmethod
    def _unnumbered_header_blocks(text: str) -> list[str]:
        """Split Alice's HTML-list text when CSS markers are absent."""

        first_candidates = list(_RECIPIENT_STARTS[0].finditer(text))
        for first in reversed(first_candidates):
            starts = [first.start()]
            cursor = first.end()
            for pattern in _RECIPIENT_STARTS[1:]:
                match = pattern.search(text, cursor)
                if match is None:
                    break
                starts.append(match.start())
                cursor = match.end()
            if len(starts) == 9:
                return [
                    text[
                        start:(
                            starts[index + 1]
                            if index + 1 < len(starts)
                            else len(text)
                        )
                    ]
                    for index, start in enumerate(starts)
                ]
        return []

    @staticmethod
    def _ordered_header_matches(text: str) -> list[re.Match[str]]:
        """Pick a complete 1..9 subsequence and ignore unrelated numbering."""

        selected: list[re.Match[str]] = []
        expected = 1
        for match in _SECTION_PATTERN.finditer(text):
            number = int(match.group(1))
            if number != expected:
                continue
            selected.append(match)
            expected += 1
            if expected == 10:
                return selected
        return []

    @classmethod
    def _answer_between_markers(cls, response_text: str) -> str:
        text = cls._clean_text(response_text)
        end = text.rfind(_END_MARKER)
        begin = text.rfind(_BEGIN_MARKER)
        if end < 0:
            if begin >= 0:
                raise AliceResponseError("Ответ Алисы ещё не завершён.")
            return text.strip()
        tail = text[end + len(_END_MARKER):].strip()
        if cls._unnumbered_header_blocks(tail):
            return tail
        if begin > end:
            raise AliceResponseError("Ответ Алисы ещё не завершён.")

        previous_end = text.rfind(_END_MARKER, 0, end)
        if begin >= 0 and begin > previous_end:
            start = begin + len(_BEGIN_MARKER)
        elif previous_end >= 0:
            # Alice sometimes omits the opening marker. In the browser page,
            # the previous closing marker belongs to the echoed user prompt.
            start = previous_end + len(_END_MARKER)
        else:
            start = 0
        return text[start:end].strip()

    @classmethod
    def _parse_header_block(
        cls,
        organization_type: OrganizationType,
        block: str,
    ) -> Organization:
        lines = [
            cls._clean_line(line)
            for line in cls._clean_text(block).splitlines()
        ]
        lines = [line for line in lines if line]
        lines = cls._drop_category_caption(organization_type, lines)

        address_index = next(
            (
                index
                for index, line in enumerate(lines)
                if _POSTAL_INDEX_PATTERN.search(line)
            ),
            -1,
        )
        if address_index <= 0:
            raise AliceResponseError(
                f"В шапке «{organization_type.value}» не найден полный "
                "почтовый адрес с индексом."
            )

        contact_index = next(
            (
                index
                for index in range(address_index, len(lines))
                if cls._is_phone_line(lines[index])
                or cls._is_email_line(lines[index])
            ),
            len(lines),
        )
        recipient = "\n".join(lines[:address_index]).strip()
        postal_address = " ".join(lines[address_index:contact_index]).strip(" ,")
        contact_text = "\n".join(lines[contact_index:])
        phones = cls._phones(contact_text)
        email_text = cls._normalized_email_text(contact_text)
        email_match = _EMAIL_PATTERN.search(email_text)
        email = email_match.group(0) if email_match else ""

        missing: list[str] = []
        if not recipient:
            missing.append("адресат")
        if not phones:
            missing.append("телефон")
        if (
            organization_type not in cls._email_optional_types()
            and not email
        ):
            missing.append("электронная почта")

        status = "needs_review" if missing else "auto_found"
        note = (
            "Ответ Алисы требует проверки: не найдено: "
            + ", ".join(missing)
            + "."
            if missing
            else "Шапка найдена Alice AI по адресу регистрации."
        )
        return Organization(
            id=None,
            organization_type=organization_type,
            recipient=recipient,
            postal_address=postal_address,
            phones=phones,
            email=email,
            source_url="https://alice.yandex.ru/",
            verification_status=status,
            verified_at="",
            verification_note=note,
        )

    @staticmethod
    def _clean_text(value: str) -> str:
        normalized_characters: list[str] = []
        for character in value:
            category = unicodedata.category(character)
            if category == "Cf":
                continue
            if category == "Zs":
                normalized_characters.append(" ")
            elif category == "Pd" or character == "−":
                normalized_characters.append("-")
            elif character == "＋":
                normalized_characters.append("+")
            else:
                normalized_characters.append(character)
        value = "".join(normalized_characters)
        value = (
            value.replace("\u00a0", " ")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )
        value = re.sub(
            r"\[\[\s*NEXUSDOCS\s*_\s*BEGIN\s*\]\]",
            _BEGIN_MARKER,
            value,
            flags=re.IGNORECASE,
        )
        return re.sub(
            r"\[\[\s*NEXUSDOCS\s*_\s*END\s*\]\]",
            _END_MARKER,
            value,
            flags=re.IGNORECASE,
        )

    @classmethod
    def has_completed_answer(cls, value: str) -> bool:
        """Recognize Alice's standalone end marker despite web formatting."""

        return any(
            line.strip() == _END_MARKER
            for line in cls._clean_text(value).splitlines()
        )

    @staticmethod
    def _clean_line(value: str) -> str:
        value = value.strip()
        value = re.sub(r"^\s*(?:[-*•]\s+)", "", value)
        value = value.replace("**", "").replace("__", "").replace("`", "")
        return " ".join(value.split()).strip()

    @classmethod
    def _drop_category_caption(
        cls,
        organization_type: OrganizationType,
        lines: list[str],
    ) -> list[str]:
        if not lines:
            return lines
        first = lines[0].casefold().replace("ё", "е").strip(" :.-")
        captions = {
            OrganizationType.MILITARY_COMMISSARIAT: ("военный комиссариат",),
            OrganizationType.MILITARY_COMMANDANT: ("военная комендатура",),
            OrganizationType.NARCOLOGY: ("наркология", "наркологическая служба"),
            OrganizationType.PSYCHIATRY: ("психиатрия", "психиатрическая служба"),
            OrganizationType.HOSPITAL: ("црб", "цгб", "больница"),
            OrganizationType.TFOMS: ("тфомс",),
            OrganizationType.ADMINISTRATION: ("администрация",),
            OrganizationType.CONTRACT_SERVICE_POINT: ("повск", "пункт отбора"),
            OrganizationType.ELECTION_COMMISSION: ("тик",),
        }[organization_type]
        return lines[1:] if first in captions else lines

    @staticmethod
    def _is_phone_line(value: str) -> bool:
        normalized = value.casefold().replace("ё", "е")
        return bool(re.match(r"^(?:тел\.?|телефон|факс)\s*:", normalized))

    @staticmethod
    def _is_email_line(value: str) -> bool:
        normalized = value.casefold().replace("ё", "е")
        return bool(
            re.match(r"^(?:эл\.?\s*почта|электронная\s+почта|e-?mail)\s*:", normalized)
        ) or bool(_EMAIL_PATTERN.search(value))

    @staticmethod
    def _phones(value: str) -> tuple[str, ...]:
        phones: list[str] = []
        normalized = AliceOrganizationSearchService._clean_text(value)
        matches = list(_PHONE_PATTERN.finditer(normalized))
        if not matches:
            # Alice's clipboard sometimes uses punctuation outside the usual
            # phone alphabet. Recognize the number by its digit structure.
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

    @staticmethod
    def _normalized_email_text(value: str) -> str:
        value = AliceOrganizationSearchService._clean_text(value)
        value = value.replace("\\@", "@").replace("\\.", ".")
        value = re.sub(r"\s*@\s*", "@", value)
        return re.sub(r"(?<=\w)\s*\.\s*(?=\w)", ".", value)

    @staticmethod
    def _email_optional_types() -> frozenset[OrganizationType]:
        return frozenset({
            OrganizationType.MILITARY_COMMISSARIAT,
            OrganizationType.MILITARY_COMMANDANT,
            OrganizationType.CONTRACT_SERVICE_POINT,
        })
