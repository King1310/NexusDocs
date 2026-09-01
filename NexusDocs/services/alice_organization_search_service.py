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
    r"\[\[\s*NEXUSDOCS_HEADER_([1-9])\s*\]\]",
    re.IGNORECASE,
)
_FIELD_MARKER_PATTERN = re.compile(
    r"\[\[\s*NEXUSDOCS_(RECIPIENT|ADDRESS|PHONE|EMAIL)\s*\]\]",
    re.IGNORECASE,
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
    """The AI response cannot be safely split into nine headers."""


@dataclass(slots=True, frozen=True)
class AliceSearchRequest:
    prompt: str
    public_address: str


class AliceOrganizationSearchService:
    """Build a strict Google AI Mode request and parse nine dry headers."""

    BEGIN_MARKER = _BEGIN_MARKER
    END_MARKER = _END_MARKER

    @classmethod
    def build_request(cls, address: Address) -> AliceSearchRequest:
        public_address = cls.public_registration_address(address)
        prompt = f'''Адрес регистрации человека: "{public_address}". Это только адрес человека, НЕ адрес организаций. Найди организации, которые территориально отвечают за этот адрес, и для каждой укажи её собственные официальные реквизиты. Проверь территориальную принадлежность и контакты по официальным источникам.

Нужно ровно 9 шапок в порядке:
1 военный комиссариат
2 военная комендатура
3 местный наркологический диспансер или кабинет
4 местная психиатрическая служба
5 центральная районная или главная больница
6 территориальный фонд обязательного медицинского страхования
7 глава администрации без ФИО
8 пункт отбора на военную службу по контракту
9 территориальная избирательная комиссия

В каждой шапке: кому и официальное компактное название; собственный полный адрес организации с индексом; один или максимум два телефона; электронная почта. В поле RECIPIENT обращение пиши первой строкой, название организации — со следующей строки, не объединяй их запятой. Электронную почту обязательно ИЩИ для всех девяти организаций и указывай всегда, когда она опубликована. Для 3, 4, 5, 6, 7 и 9 почта обязательна. Для 1, 2 и 8 пустое поле допустимо только если после отдельного поиска на официальном сайте, странице контактов и региональном портале опубликованная почта действительно не найдена; не пропускай поиск почты лишь потому, что для этих трёх шапок она необязательна. Телефон обязателен во всех девяти шапках. ФИО людей не пиши. Должности не сокращай. Используй официальные общепринятые сокращения ГБУЗ, ГАУЗ, ГКБ, ЦРБ, ЦГБ, КОБ, ОКБ, ТФОМС. Никаких пояснений, предупреждений и ссылок.

Ответ только в таком машинном формате:
[[NEXUSDOCS_BEGIN]]
[[NEXUSDOCS_HEADER_1]]
[[NEXUSDOCS_RECIPIENT]]кому и название организации
[[NEXUSDOCS_ADDRESS]]полный адрес организации с индексом
[[NEXUSDOCS_PHONE]]один или максимум два телефона
[[NEXUSDOCS_EMAIL]]найденная электронная почта; пусто только для 1, 2 и 8, если она действительно не опубликована
[[NEXUSDOCS_HEADER_2]]
[[NEXUSDOCS_RECIPIENT]]...
[[NEXUSDOCS_ADDRESS]]...
[[NEXUSDOCS_PHONE]]...
[[NEXUSDOCS_EMAIL]]...
Продолжи без пропусков до [[NEXUSDOCS_HEADER_9]], затем поставь [[NEXUSDOCS_END]]. Метки пиши буквально. Не используй Markdown-нумерацию и не добавляй текст вне протокола.'''
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
            if len(blocks) != 9:
                blocks = cls._postal_group_header_blocks(text)
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
                "Google AI должен вернуть девять отдельных шапок. "
                f"Распознаны разделители: {marker_numbers or 'нет'}, "
                f"номера: {found or 'нет'}."
            )

        organizations: list[Organization] = []
        unresolved: list[OrganizationType] = []
        types = tuple(OrganizationType)
        for index, block in enumerate(blocks):
            if _FIELD_MARKER_PATTERN.search(block):
                organization = cls._parse_tagged_header_block(types[index], block)
            else:
                organization = cls._parse_header_block(types[index], block)
            organizations.append(organization)
            if organization.verification_status == "needs_review":
                unresolved.append(organization.organization_type)

        return FreeSearchOutcome(tuple(organizations), tuple(unresolved))

    @classmethod
    def extract_complete_tagged_blocks(cls, value: str) -> dict[int, str]:
        """Collect complete real headers from a possibly virtualized page."""

        text = cls._clean_text(value)
        matches = list(_HEADER_MARKER_PATTERN.finditer(text))
        collected: dict[int, str] = {}
        for index, match in enumerate(matches):
            number = int(match.group(1))
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            closing = text.find(_END_MARKER, match.end(), end)
            if closing >= 0:
                end = closing
            block = text[match.start():end].strip()
            fields = [
                field.group(1).upper()
                for field in _FIELD_MARKER_PATTERN.finditer(block)
            ]
            if fields != ["RECIPIENT", "ADDRESS", "PHONE", "EMAIL"]:
                continue
            if not _POSTAL_INDEX_PATTERN.search(block) or not cls._phones(block):
                # This also discards the illustrative placeholders embedded in
                # the request itself.
                continue
            collected[number] = block
        return collected

    @staticmethod
    def assemble_tagged_blocks(blocks: dict[int, str]) -> str:
        if set(blocks) != set(range(1, 10)):
            raise AliceResponseError("Собраны не все девять шапок Google AI.")
        return "\n".join(
            (
                _BEGIN_MARKER,
                *(blocks[number] for number in range(1, 10)),
                _END_MARKER,
            )
        )

    @classmethod
    def _parse_tagged_header_block(
        cls,
        organization_type: OrganizationType,
        block: str,
    ) -> Organization:
        """Parse a header without relying on Alice's visual layout."""

        text = cls._clean_text(block)
        matches = list(_FIELD_MARKER_PATTERN.finditer(text))
        names = [match.group(1).upper() for match in matches]
        expected = ["RECIPIENT", "ADDRESS", "PHONE", "EMAIL"]
        if names != expected:
            raise AliceResponseError(
                f"В шапке «{organization_type.value}» нарушен машинный "
                "формат полей RECIPIENT, ADDRESS, PHONE, EMAIL."
            )

        values: dict[str, str] = {}
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            values[match.group(1).upper()] = text[match.end():end].strip()

        recipient = "\n".join(
            cls._clean_line(line)
            for line in values["RECIPIENT"].splitlines()
            if cls._clean_line(line)
        )
        recipient = cls._normalize_recipient_layout(recipient, organization_type)
        postal_address = " ".join(values["ADDRESS"].split()).strip(" ,")
        phones = cls._phones(values["PHONE"])
        email_text = cls._normalized_email_text(values["EMAIL"])
        email_match = _EMAIL_PATTERN.search(email_text)
        email = email_match.group(0) if email_match else ""

        missing: list[str] = []
        if not recipient:
            missing.append("адресат")
        if not _POSTAL_INDEX_PATTERN.search(postal_address):
            missing.append("почтовый адрес с индексом")
        if not phones:
            missing.append("телефон")
        if organization_type not in cls._email_optional_types() and not email:
            missing.append("электронная почта")

        status = "needs_review" if missing else "auto_found"
        note = (
            "Ответ Google AI требует проверки: не найдено: "
            + ", ".join(missing)
            + "."
            if missing
            else "Шапка найдена Google AI Mode по адресу регистрации."
        )
        return Organization(
            id=None,
            organization_type=organization_type,
            recipient=recipient,
            postal_address=postal_address,
            phones=phones,
            email=email,
            source_url="https://www.google.com/search?udm=50",
            verification_status=status,
            verified_at="",
            verification_note=note,
        )

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
                "Google AI не указал обязательные контакты — "
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
                "Google AI скопировал адрес субъекта или один и тот же адрес "
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

    @classmethod
    def _postal_group_header_blocks(cls, text: str) -> list[str]:
        """Recover nine headers when Alice exposes list markers only via CSS.

        Alice occasionally changes the recipient wording and removes list
        numbers from ``innerText``.  A complete answer still has one postal
        index per header, so paragraph groups around those indexes provide a
        stable boundary independent of the page's HTML structure.
        """

        lines = [
            cls._clean_line(line)
            for line in cls._clean_text(text).splitlines()
        ]
        lines = [line for line in lines if line]
        address_lines = [
            index
            for index, line in enumerate(lines)
            if _POSTAL_INDEX_PATTERN.search(line)
        ]
        if len(address_lines) != 9:
            return []

        starts = [0]
        for current_address, next_address in zip(
            address_lines,
            address_lines[1:],
        ):
            contact_lines = [
                index
                for index in range(current_address + 1, next_address)
                if cls._is_phone_line(lines[index])
                or cls._is_email_line(lines[index])
                or bool(cls._phones(lines[index]))
            ]
            if not contact_lines:
                return []
            start = max(contact_lines) + 1
            if start >= next_address:
                return []
            starts.append(start)

        blocks = []
        for index, start in enumerate(starts):
            end = starts[index + 1] if index + 1 < len(starts) else len(lines)
            block = "\n".join(lines[start:end]).strip()
            if not _POSTAL_INDEX_PATTERN.search(block):
                return []
            blocks.append(block)
        return blocks if len(blocks) == 9 else []

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
                raise AliceResponseError("Ответ Google AI ещё не завершён.")
            return text.strip()
        tail = text[end + len(_END_MARKER):].strip()
        if cls._unnumbered_header_blocks(tail):
            return tail
        if begin > end:
            raise AliceResponseError("Ответ Google AI ещё не завершён.")

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
        recipient = cls._normalize_recipient_layout(
            "\n".join(lines[:address_index]).strip(),
            organization_type,
        )
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
            "Ответ Google AI требует проверки: не найдено: "
            + ", ".join(missing)
            + "."
            if missing
            else "Шапка найдена Google AI Mode по адресу регистрации."
        )
        return Organization(
            id=None,
            organization_type=organization_type,
            recipient=recipient,
            postal_address=postal_address,
            phones=phones,
            email=email,
            source_url="https://www.google.com/search?udm=50",
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
        value = re.sub(
            r"\[\[\s*NEXUSDOCS\s*_\s*END\s*\]\]",
            _END_MARKER,
            value,
            flags=re.IGNORECASE,
        )
        # Alice's current web renderer may flatten an entire header into one
        # visual paragraph: "address tel.: ... эл. почта: ... [[END]]".
        # Restore the field boundaries expected by the parser regardless of
        # whether the browser exposes paragraph breaks.
        value = re.sub(
            r"[ \t]*(?=(?:тел\.?|телефон|факс)\s*:)",
            "\n",
            value,
            flags=re.IGNORECASE,
        )
        value = re.sub(
            r"[ \t]*(?=(?:эл\.?\s*почта|электронная\s+почта|e-?mail)\s*:)",
            "\n",
            value,
            flags=re.IGNORECASE,
        )
        value = re.sub(
            rf"[ \t]*(?={re.escape(_BEGIN_MARKER)}|{re.escape(_END_MARKER)})",
            "\n",
            value,
        )
        return value

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

    @staticmethod
    def _normalize_recipient_layout(
        value: str,
        organization_type: OrganizationType | None = None,
    ) -> str:
        """Separate and normalize Google's salutation/organization layout."""

        formatted = value
        salutations = (
            "военному комиссару",
            "военному коменданту",
            "главному врачу",
            "директору",
            "главе",
            "начальнику",
            "председателю",
        )
        if "\n" not in formatted and "," in formatted:
            first, remainder = (part.strip() for part in value.split(",", 1))
            normalized = first.casefold().replace("ё", "е")
            if remainder and normalized.startswith(salutations):
                formatted = f"{first}\n{remainder}"

        if organization_type is None:
            return formatted
        boundaries = {
            OrganizationType.MILITARY_COMMISSARIAT: r"\bВоенн(?:ый|ого)\s+комиссариат\b",
            OrganizationType.MILITARY_COMMANDANT: r"\bВоенн(?:ая|ой)\s+комендатур(?:а|ы)\b",
            OrganizationType.NARCOLOGY: r"\b(?:ГБУЗ|ГАУЗ|ФГБУ|ГБУ|Наркологическ\w*)\b",
            OrganizationType.PSYCHIATRY: r"\b(?:ГБУЗ|ГАУЗ|ФГБУ|ГБУ|Психиатрическ\w*)\b",
            OrganizationType.HOSPITAL: r"\b(?:ГБУЗ|ГАУЗ|ФГБУ|ГБУ|ГКБ|ЦРБ|ЦГБ|КОБ|ОКБ)\b",
            OrganizationType.TFOMS: r"\b(?:ТФОМС|МГФОМС|Территориальн\w*)\b",
            OrganizationType.ADMINISTRATION: r"\b(?:Администраци\w*|Управ\w*|Правительств\w*)\b",
            OrganizationType.CONTRACT_SERVICE_POINT: r"\b(?:Единый\s+)?Пункт\s+отбора\b",
            OrganizationType.ELECTION_COMMISSION: r"\b(?:Территориальн\w+|Московск\w+)\s+(?:городск\w+\s+)?избирательн\w+\s+комисси\w+\b",
        }
        if "\n" not in formatted:
            match = re.search(
                boundaries[organization_type],
                formatted,
                re.IGNORECASE,
            )
            if match and match.start() > 0:
                formatted = (
                    f"{formatted[:match.start()].strip()}\n"
                    f"{formatted[match.start():].strip()}"
                )

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
        }[organization_type]
        lines = [line.strip() for line in formatted.splitlines() if line.strip()]
        if len(lines) >= 2:
            lines[0] = required_salutation
            cls_prefixes = {
                OrganizationType.MILITARY_COMMISSARIAT: (
                    "военного комиссариата",
                    re.compile(
                        r"^военн(?:ый|ого)\s+комиссариат(?:а)?\s*",
                        re.IGNORECASE,
                    ),
                ),
                OrganizationType.MILITARY_COMMANDANT: (
                    "военной комендатуры",
                    re.compile(
                        r"^военн(?:ая|ой)\s+комендатур(?:а|ы)\s*",
                        re.IGNORECASE,
                    ),
                ),
            }
            prefix_rule = cls_prefixes.get(organization_type)
            if len(lines) >= 3 and prefix_rule is not None:
                constant_line, repeated_prefix = prefix_rule
                normalized_second = lines[1].casefold().replace("ё", "е")
                if normalized_second == constant_line:
                    remainder = repeated_prefix.sub("", lines[2]).strip(" ,")
                    if remainder:
                        lines[2] = remainder
                    else:
                        del lines[2]
            return "\n".join(lines)
        return formatted

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


# Public Google names are used by the application.  The legacy aliases remain
# available so existing saved installations and third-party imports do not
# break during the migration from Alice AI.
GoogleResponseError = AliceResponseError
GoogleSearchRequest = AliceSearchRequest
GoogleOrganizationSearchService = AliceOrganizationSearchService
