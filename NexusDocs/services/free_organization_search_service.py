from __future__ import annotations

from dataclasses import dataclass
from email.utils import parseaddr
import html as html_module
import json
import re
from urllib.parse import urlparse

from lxml import html as lxml_html
from lxml.etree import ParserError

from domain.entities.organization import Organization
from domain.enums.organization_type import OrganizationType
from domain.value_objects.address import Address
from services.browser_organization_search_service import (
    BrowserOrganizationSearchService,
)
from services.curated_header_service import CuratedHeaderService


_TYPE_KEYWORDS = {
    OrganizationType.MILITARY_COMMISSARIAT: ("военн", "комиссариат"),
    OrganizationType.MILITARY_COMMANDANT: ("военн", "комендатур", "гарнизон"),
    OrganizationType.NARCOLOGY: (
        "нарколог",
        "психоневролог",
        "диспансер",
    ),
    OrganizationType.PSYCHIATRY: (
        "психиатр",
        "психоневролог",
        "отделен",
    ),
    OrganizationType.HOSPITAL: ("црб", "больниц"),
    OrganizationType.TFOMS: ("тфомс", "обязательного медицинского страхования"),
    OrganizationType.ADMINISTRATION: ("администрац", "поселен"),
    OrganizationType.CONTRACT_SERVICE_POINT: ("пункт", "отбор", "контракт"),
    OrganizationType.ELECTION_COMMISSION: ("тик", "избирательн", "комисси"),
}

_DIRECTORY_DOMAINS = {
    "2gis.ru",
    "yandex.ru",
    "zoon.ru",
    "rusprofile.ru",
    "checko.ru",
    "gogov.ru",
    "wikipedia.org",
    "vk.ru",
    "blizko.pro",
    "ros-spravka.ru",
    "golos-pravda.ru",
    "voenkomat-info.ru",
    "voenkomat-rf.ru",
    "list-org.com",
    "rusorgs.ru",
    "star-pro.ru",
    "spark-interfax.ru",
}

_UNUSABLE_SOURCE_DOMAINS = _DIRECTORY_DOMAINS | {
    "ok.ru",
    "vk.com",
    "pravda-klientov.ru",
    "otzovik.com",
    "yell.ru",
    "ramnews.ru",
    "instagram.com",
    "facebook.com",
}

_OFFICIAL_DOMAIN_HINTS = (
    "admin",
    "adm.",
    "oms",
    "izbir",
    "narko",
    "zdrav",
    "crb",
    "mil.ru",
)

_OFFICIAL_HINTS = (
    "официальн",
    "государствен",
    "министерств",
    "администрац",
    "избирательн",
    "тфомс",
)

_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+7|8)[\s\-(]*(?:\d[\s\-()]*?){9,10}(?!\d)"
)
_EMAIL_PATTERN = re.compile(
    r"(?<![\w.-])[\w.+-]+@[\w.-]+\.[A-Za-zА-Яа-я]{2,}(?![\w.-])"
)
_POSTAL_ADDRESS_PATTERN = re.compile(
    r"\b\d{6}\s*,?\s*.{8,240}?(?="
    r"(?:\bтел(?:ефон)?\b|\bфакс\b|\be-?mail\b|"
    r"\bэл(?:ектронн\w*)?\.?\s*почт|$))",
    re.IGNORECASE,
)
_LABELED_ADDRESS_PATTERN = re.compile(
    r"(?:адрес|наш адрес)\s*[:.]\s*(.{8,220}?)(?="
    r"(?:\bтел(?:ефон)?\b|\bфакс\b|\be-?mail\b|"
    r"\bэл(?:ектронн\w*)?\.?\s*почт|$))",
    re.IGNORECASE,
)
_ROUTE_ADDRESS_PATTERN = re.compile(
    r"схема\s+проезда\s+(.{8,220}?)(?="
    r"(?:\bтел(?:ефон)?\b|\bфакс\b|\be-?mail\b|"
    r"\bэл(?:ектронн\w*)?\.?\s*почт|$))",
    re.IGNORECASE,
)
_ADMINISTRATIVE_UNIT_PATTERN = re.compile(
    r"\b[А-ЯЁA-Z][А-Яа-яЁёA-Za-z-]{3,40}\s+"
    r"(?:(?:муниципальн|городск)\w*\s+)?(?:район|округ)\b",
    re.IGNORECASE,
)


@dataclass(slots=True, frozen=True)
class FreeSearchOutcome:
    organizations: tuple[Organization, ...]
    unresolved_types: tuple[OrganizationType, ...]


@dataclass(slots=True, frozen=True)
class _SearchHit:
    title: str
    url: str
    body: str
    score: int
    page_text: str = ""

    @property
    def text(self) -> str:
        return " ".join(part for part in (self.title, self.body, self.page_text) if part)


class FreeOrganizationSearchService:
    """Автоматически подбирает шапки через бесплатный метапоиск DDGS."""

    def __init__(self, backend=None, max_results: int = 8):
        self.backend = backend
        self.max_results = max_results
        self.query_builder = BrowserOrganizationSearchService()

    def search(
        self,
        address: Address,
        organization_types,
    ) -> FreeSearchOutcome:
        requested = tuple(organization_types)
        if not requested:
            return FreeSearchOutcome((), ())

        curated = (
            CuratedHeaderService.resolve(address, requested)
            if self.backend is None
            else {}
        )
        backend = self.backend
        found: list[Organization] = []
        unresolved: list[OrganizationType] = []
        narcology: Organization | None = None

        for organization_type in requested:
            candidate = curated.get(organization_type)
            if candidate is None:
                if backend is None:
                    backend = self._default_backend()
                candidate = self._search_one(backend, address, organization_type)
            if candidate is None and organization_type is OrganizationType.PSYCHIATRY:
                candidate = self._psychiatry_from_narcology(narcology)
            if candidate is None:
                candidate = self.build_review_placeholder(
                    address,
                    organization_type,
                )
                unresolved.append(organization_type)
            elif candidate.verification_status == "needs_review":
                unresolved.append(organization_type)
            found.append(candidate)
            if organization_type is OrganizationType.NARCOLOGY:
                narcology = candidate

        by_type = {
            organization.organization_type: organization
            for organization in found
        }
        narcology = by_type.get(OrganizationType.NARCOLOGY)
        psychiatry = by_type.get(OrganizationType.PSYCHIATRY)
        if (
            OrganizationType.NARCOLOGY in requested
            and OrganizationType.PSYCHIATRY in requested
            and psychiatry is not None
            and psychiatry.source_url
            and (narcology is None or not narcology.source_url)
            and self._is_combined_medical_unit(psychiatry)
        ):
            by_type[OrganizationType.NARCOLOGY] = (
                self._narcology_from_psychiatry(psychiatry)
            )

        ordered = tuple(by_type[organization_type] for organization_type in requested)
        unresolved = [
            organization.organization_type
            for organization in ordered
            if organization.verification_status == "needs_review"
        ]
        return FreeSearchOutcome(ordered, tuple(unresolved))

    @staticmethod
    def _default_backend():
        from ddgs import DDGS

        return DDGS(timeout=20)

    def _search_one(
        self,
        backend,
        address: Address,
        organization_type: OrganizationType,
    ) -> Organization | None:
        raw_results = []
        for backend_name in ("yandex", "google", "bing", "auto"):
            for query in self.query_builder.queries(address, organization_type):
                query_results = []
                for query_variant in dict.fromkeys(
                    (query, query.replace('"', ""))
                ):
                    try:
                        query_results = backend.text(
                            query_variant,
                            region="ru-ru",
                            safesearch="off",
                            max_results=self.max_results,
                            backend=backend_name,
                        )
                    except TypeError:
                        query_results = backend.text(
                            query_variant,
                            max_results=self.max_results,
                        )
                    except Exception:
                        query_results = []
                    if query_results:
                        break
                raw_results.extend(query_results or ())
            if raw_results:
                break

        unique_results = []
        seen_urls = set()
        for result in raw_results:
            url = str(result.get("href", result.get("url", ""))).strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            unique_results.append(result)

        hits = [
            self._hit_from_result(
                result,
                address,
                organization_type,
                position,
            )
            for position, result in enumerate(unique_results)
        ]
        hits = [hit for hit in hits if hit.url]
        hits.sort(key=lambda hit: hit.score, reverse=True)
        if not hits or hits[0].score < 3:
            return None

        best_effort: Organization | None = None
        for index, hit in enumerate(hits[:8]):
            if not self._source_is_usable(hit):
                continue
            snippet_text = " ".join((hit.title, hit.body))
            page_text = ""
            source_url = hit.url
            snippet_has_address = self._postal_address(
                address,
                [snippet_text],
            )
            snippet_has_phones = self._phones([snippet_text])
            snippet_has_emails = self._emails([snippet_text])
            if (
                index < 2
                and hasattr(backend, "extract")
                and (
                    not snippet_has_address
                    or not snippet_has_phones
                    or not snippet_has_emails
                )
            ):
                try:
                    extracted = backend.extract(hit.url, fmt="text")
                    page_text = self._page_text(extracted)
                except Exception:
                    if hit.url.startswith("https://"):
                        source_url = "http://" + hit.url.removeprefix("https://")
                        try:
                            extracted = backend.extract(source_url, fmt="text")
                            page_text = self._page_text(extracted)
                        except Exception:
                            page_text = ""
            hit = _SearchHit(
                hit.title,
                source_url,
                hit.body,
                hit.score,
                page_text,
            )
            texts = [snippet_text, hit.page_text]
            recipient = self._recipient(
                address,
                organization_type,
                hit,
                texts,
            )
            postal_address = self._postal_address(address, texts)
            if not recipient:
                continue
            phones = self._phones(texts)
            emails = self._emails(texts)
            if not postal_address:
                postal_address = self._relaxed_postal_address(address, texts)
                if postal_address and not self._candidate_is_consistent(
                    address,
                    organization_type,
                    recipient,
                    postal_address,
                    hit.text,
                ):
                    # Do not offer a territorially foreign organization merely
                    # because its address happens to contain the target locality.
                    continue
                if best_effort is None:
                    best_effort = self._review_candidate(
                        organization_type=organization_type,
                        recipient=recipient,
                        postal_address=postal_address,
                        phones=phones,
                        email=emails[0] if emails else "",
                        source_url=hit.url,
                        note=(
                            "Организация найдена автоматически. "
                            + (
                                "Адрес извлечён, но в источнике не указан "
                                "почтовый индекс."
                                if postal_address
                                else "Почтовый адрес не удалось извлечь из источника."
                            )
                        ),
                    )
                continue
            if not self._candidate_is_consistent(
                address,
                organization_type,
                recipient,
                postal_address,
                hit.text,
            ):
                if (
                    best_effort is None
                    and organization_type
                    not in self._strict_territory_types()
                ):
                    best_effort = self._review_candidate(
                        organization_type=organization_type,
                        recipient=recipient,
                        postal_address=postal_address,
                        phones=phones,
                        email=emails[0] if emails else "",
                        source_url=hit.url,
                        note=(
                            "Лучший найденный вариант не прошёл проверку "
                            "территории или типа организации."
                        ),
                    )
                continue

            missing_contacts = self._missing_required_contacts(
                organization_type,
                phones,
                emails,
            )
            if missing_contacts:
                candidate = self._review_candidate(
                    organization_type=organization_type,
                    recipient=recipient,
                    postal_address=postal_address,
                    phones=phones,
                    email=emails[0] if emails else "",
                    source_url=hit.url,
                    note=(
                        "Организация и адрес найдены, но не удалось получить: "
                        + ", ".join(missing_contacts)
                        + "."
                    ),
                )
                if best_effort is None or self._contact_score(candidate) > self._contact_score(best_effort):
                    best_effort = candidate
                continue

            return Organization(
                id=None,
                organization_type=organization_type,
                recipient=recipient,
                postal_address=postal_address,
                phones=phones,
                email=emails[0] if emails else "",
                source_url=hit.url,
                verification_status="auto_found",
                verified_at="",
                verification_note=(
                    "Найдено автоматически бесплатным поиском по территории; "
                    "все реквизиты взяты из одного источника."
                ),
            )
        return best_effort

    @staticmethod
    def _email_optional_types() -> frozenset[OrganizationType]:
        return frozenset({
            OrganizationType.MILITARY_COMMISSARIAT,
            OrganizationType.MILITARY_COMMANDANT,
            OrganizationType.CONTRACT_SERVICE_POINT,
        })

    @classmethod
    def _missing_required_contacts(
        cls,
        organization_type: OrganizationType,
        phones: tuple[str, ...],
        emails: tuple[str, ...],
    ) -> tuple[str, ...]:
        missing: list[str] = []
        if not phones:
            missing.append("телефон")
        if organization_type not in cls._email_optional_types() and not emails:
            missing.append("электронную почту")
        return tuple(missing)

    @staticmethod
    def _contact_score(organization: Organization) -> int:
        return (
            bool(organization.postal_address) * 4
            + min(len(organization.phones), 2) * 2
            + bool(organization.email) * 2
            + bool(organization.source_url)
        )

    @staticmethod
    def _review_candidate(
        organization_type: OrganizationType,
        recipient: str,
        postal_address: str,
        phones: tuple[str, ...],
        email: str,
        source_url: str,
        note: str,
    ) -> Organization:
        return Organization(
            id=None,
            organization_type=organization_type,
            recipient=recipient,
            postal_address=postal_address,
            phones=phones,
            email=email,
            source_url=source_url,
            verification_status="needs_review",
            verified_at="",
            verification_note=note,
        )

    def build_review_placeholder(
        self,
        address: Address,
        organization_type: OrganizationType,
    ) -> Organization:
        """Return a visible, review-marked header instead of blocking Word."""

        district = self._district_recipient(address.district)
        region = self._region_recipient(address.region)
        territory = district or address.locality or address.city or region
        recipients = {
            OrganizationType.MILITARY_COMMISSARIAT: (
                "Военному комиссару\nВоенного комиссариата\n"
                + "\n".join(part for part in (district, region) if part)
            ),
            OrganizationType.MILITARY_COMMANDANT: (
                "Военному коменданту\nВоенной комендатуры\n"
                + (region or address.region)
            ),
            OrganizationType.NARCOLOGY: (
                "Главному врачу\nмедицинской организации\n"
                f"{territory}"
            ),
            OrganizationType.PSYCHIATRY: (
                "Главному врачу\nмедицинской организации\n"
                f"{territory}"
            ),
            OrganizationType.HOSPITAL: (
                "Главному врачу\nцентральной районной больницы\n"
                + territory
            ),
            OrganizationType.TFOMS: (
                "Директору\nТерриториального фонда\n"
                "обязательного медицинского страхования\n"
                + (region or address.region)
            ),
            OrganizationType.ADMINISTRATION: (
                "Главе\n"
                + (district or address.locality or address.city)
            ),
            OrganizationType.CONTRACT_SERVICE_POINT: (
                "Начальнику\nПункта отбора\n"
                "на военную службу по контракту\n"
                + (region or address.region)
            ),
            OrganizationType.ELECTION_COMMISSION: (
                "Председателю\nТерриториальной избирательной комиссии\n"
                + (district or address.locality or address.city)
            ),
        }
        return self._review_candidate(
            organization_type=organization_type,
            recipient=recipients[organization_type].strip(),
            postal_address="",
            phones=(),
            email="",
            source_url="",
            note=(
                "Автоматический поиск не вернул подходящий результат; "
                "в Word вставлена шапка для обязательной ручной проверки."
            ),
        )

    def _hit_from_result(
        self,
        result,
        address: Address,
        organization_type: OrganizationType,
        position: int,
    ) -> _SearchHit:
        title = str(result.get("title", "")).strip()
        url = str(result.get("href", result.get("url", ""))).strip()
        body = str(result.get("body", "")).strip()
        text = f"{title} {body}".casefold().replace("ё", "е")
        score = max(0, self.max_results - position)
        for keyword in _TYPE_KEYWORDS[organization_type]:
            if keyword in text:
                score += 2

        for location in (address.region, address.district, address.locality, address.city):
            location_words = self._meaningful_words(location)
            if location_words and any(word in text for word in location_words):
                score += 2

        hostname = urlparse(url).hostname or ""
        hostname = hostname.removeprefix("www.").casefold()
        if any(hostname == domain or hostname.endswith("." + domain) for domain in _DIRECTORY_DOMAINS):
            score -= 6
        if hostname.endswith((".gov.ru", ".mil.ru", ".gosuslugi.ru")):
            score += 6
        if any(hint in hostname for hint in _OFFICIAL_DOMAIN_HINTS):
            score += 4
        email_domains = {
            email.rsplit("@", 1)[-1]
            for email in _EMAIL_PATTERN.findall(body)
            if "@" in email
        }
        if any(hostname == domain or hostname.endswith("." + domain) for domain in email_domains):
            score += 5
        if any(hint in text for hint in _OFFICIAL_HINTS):
            score += 3
        if re.search(r"\b\d{6}\b", body) or re.search(
            r"\b(?:адрес|телефон|тел\.)\b",
            body,
            re.IGNORECASE,
        ):
            score += 3
        return _SearchHit(title, url, body, score)

    @staticmethod
    def _source_is_usable(hit: _SearchHit) -> bool:
        hostname = (urlparse(hit.url).hostname or "").casefold()
        hostname = hostname.removeprefix("www.")
        if any(
            hostname == domain or hostname.endswith("." + domain)
            for domain in _UNUSABLE_SOURCE_DOMAINS
        ):
            return False
        source = " ".join((hit.title, hit.body, hit.url)).casefold()
        rejected_markers = (
            "отзывы",
            "отзыв о",
            "правда клиентов",
            "новости раменского",
            "вакансии",
        )
        return not any(marker in source for marker in rejected_markers)

    @staticmethod
    def _meaningful_words(value: str) -> tuple[str, ...]:
        ignored = {"край", "область", "район", "округ", "город", "поселок"}
        return tuple(
            word
            for word in re.findall(r"[а-яa-z]{5,}", value.casefold().replace("ё", "е"))
            if word not in ignored
        )

    def _recipient(
        self,
        address: Address,
        organization_type: OrganizationType,
        primary: _SearchHit,
        texts: list[str],
    ) -> str:
        district = self._district_recipient(address.district)
        region = self._region_recipient(address.region)
        joined = " ".join(texts)
        title = self._clean_title(primary.title)

        if organization_type is OrganizationType.MILITARY_COMMISSARIAT:
            parts = ["Военному комиссару", "Военного комиссариата"]
            designation = self._commissariat_territory(title, joined)
            if designation:
                region_words = self._meaningful_words(address.region)
                normalized_designation = designation.casefold().replace("ё", "е")
                if region and region_words and not any(
                    word in normalized_designation for word in region_words
                ):
                    designation += " " + region
                parts.append(designation)
            else:
                if district:
                    parts.append(district)
                if region:
                    parts.append(region)
            return "\n".join(parts)

        if organization_type is OrganizationType.MILITARY_COMMANDANT:
            match = re.search(
                r"военная комендатура\s+([А-ЯЁA-Z][^|—.]{3,80}?гарнизона)",
                joined,
                re.IGNORECASE,
            )
            name = match.group(1).strip() if match else title
            name = re.sub(r"^военная комендатура\s+", "", name, flags=re.I)
            name = self._normal_case(name)
            if not re.search(r"гарнизон", name, re.IGNORECASE):
                name = region or address.region
            return f"Военному коменданту\nВоенной комендатуры\n{name}"

        if organization_type is OrganizationType.TFOMS:
            return (
                "Директору\nТерриториального фонда\n"
                "обязательного медицинского страхования\n"
                + (region or address.region)
            )

        if organization_type is OrganizationType.ELECTION_COMMISSION:
            commission = self._commission_territory(title, joined)
            return (
                "Председателю\nТерриториальной избирательной комиссии\n"
                + (commission or district or address.locality or address.city)
            )

        if organization_type is OrganizationType.ADMINISTRATION:
            name = self._organization_name(organization_type, title, joined)
            if not name:
                return ""
            jurisdiction = re.sub(
                r"(?i)^администраци[яи]\s+",
                "",
                name,
            ).strip()
            return "\n".join(part for part in ("Главе", jurisdiction) if part)

        if organization_type is OrganizationType.CONTRACT_SERVICE_POINT:
            return (
                "Начальнику\nПункта отбора\n"
                "на военную службу по контракту\n"
                + (region or address.region)
            )

        name = self._organization_name(organization_type, title, joined)
        if not name:
            return ""
        prefix = {
            OrganizationType.NARCOLOGY: "Главному врачу",
            OrganizationType.PSYCHIATRY: "Главному врачу",
            OrganizationType.HOSPITAL: "Главному врачу",
            OrganizationType.TFOMS: "Директору",
            OrganizationType.ADMINISTRATION: "Главе",
            OrganizationType.CONTRACT_SERVICE_POINT: "Начальнику",
            OrganizationType.ELECTION_COMMISSION: "Председателю",
        }[organization_type]
        return f"{prefix}\n{name}"

    @classmethod
    def _commissariat_territory(cls, title: str, joined: str) -> str:
        match = re.search(
            r"военн(?:ый|ого)\s+комиссариат(?:а)?\s+([^|—.!?]{3,200})",
            joined,
            re.IGNORECASE,
        )
        if not match:
            return ""
        value = re.split(
            r"(?i)\s+(?:почтовый\s+адрес|адрес|телефон|тел\.|контакты|"
            r"официальный\s+сайт)\s*:?",
            match.group(1),
            maxsplit=1,
        )[0]
        return cls._clean_title(value)

    @classmethod
    def _commission_territory(cls, title: str, joined: str) -> str:
        match = re.search(
            r"(?:территориальная\s+избирательная\s+комиссия|ТИК)\s+"
            r"([^|—.!?]{2,120})",
            joined,
            re.IGNORECASE,
        )
        if not match:
            return ""
        value = re.split(
            r"(?i)\s+(?:адрес|телефон|тел\.|контакты|официальный\s+сайт)\s*:?",
            match.group(1),
            maxsplit=1,
        )[0]
        return cls._clean_title(value)

    def _organization_name(
        self,
        organization_type: OrganizationType,
        title: str,
        joined: str,
    ) -> str:
        if organization_type in {
            OrganizationType.NARCOLOGY,
            OrganizationType.PSYCHIATRY,
            OrganizationType.HOSPITAL,
        }:
            legal_name = re.search(
                r"((?:ГБУЗ|государственное\s+бюджетное\s+учреждение)"
                r"[^«»\".!?]{0,100}[«\"][^»\"]{2,160}"
                r"(?:больниц|диспансер)[^»\"]*[»\"])",
                joined,
                re.IGNORECASE,
            )
            if legal_name:
                return self._clean_title(legal_name.group(1))

        patterns = {
            OrganizationType.NARCOLOGY: (
                r"((?:ГБУЗ|государственное бюджетное учреждение)[^.!?]{5,180}?"
                r"(?:наркологическ|психоневрологическ)[^.!?]{0,120})"
            ),
            OrganizationType.PSYCHIATRY: (
                r"((?:ГБУЗ|государственное бюджетное учреждение)[^.!?]{5,180}?"
                r"(?:психиатр|психоневрологическ|наркологическ)"
                r"[^.!?]{0,120})"
            ),
            OrganizationType.HOSPITAL: (
                r"((?:ГБУЗ|государственное бюджетное учреждение)[^.!?]{0,160}?"
                r"(?:ЦРБ|ЦГБ|больниц)[^.!?]{0,100})"
            ),
            OrganizationType.TFOMS: (
                r"(Территориальный фонд обязательного медицинского страхования"
                r"[^.!?]{0,100})"
            ),
            OrganizationType.ADMINISTRATION: (
                r"(Администрация[^.!?]{3,160}?(?:поселения|района|округа))"
            ),
            OrganizationType.CONTRACT_SERVICE_POINT: (
                r"(Пункт отбора на военную службу по контракту[^|—.!?]{0,120})"
            ),
            OrganizationType.ELECTION_COMMISSION: (
                r"((?:Территориальная избирательная комиссия|ТИК)"
                r"[^|—.!?]{2,100})"
            ),
        }
        match = re.search(patterns[organization_type], joined, re.IGNORECASE)
        name = match.group(1).strip(" ,.-") if match else title
        name = re.split(
            r"\s+(?:\(далее\b|создан\b|адрес\s*:|"
            r"электронн\w*\s+почт\w*\s*:|головн\w*\s+организац\w*\s*:|"
            r"\bИНН\b)",
            name,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        name = self._clean_title(name)
        if organization_type is OrganizationType.NARCOLOGY:
            branch = re.search(
                r"([А-ЯЁ][А-Яа-яЁё-]+(?:ский|ской|ским)\s+филиал[а-я]*)",
                joined,
            )
            if branch and branch.group(1).casefold() not in name.casefold():
                name = branch.group(1) + "\n" + name

        required = {
            OrganizationType.NARCOLOGY: ("нарколог", "психоневролог"),
            OrganizationType.PSYCHIATRY: ("психиатр", "психоневролог"),
            OrganizationType.HOSPITAL: ("больниц", "црб", "цгб"),
            OrganizationType.ADMINISTRATION: ("администрац",),
            OrganizationType.CONTRACT_SERVICE_POINT: (
                "пункт отбора",
                "военную службу по контракту",
            ),
        }.get(organization_type, ())
        normalized = name.casefold().replace("ё", "е")
        if required and not any(item in normalized for item in required):
            return ""
        return name

    @staticmethod
    def _clean_title(value: str) -> str:
        value = html_module.unescape(value).strip()
        value = re.sub(
            r"^(?:контакты|главная|официальный сайт)\s*[-,|:]\s*",
            "",
            value,
            flags=re.IGNORECASE,
        )
        value = re.sub(
            r"\s*[-|]\s*(?:контакт(?:ы|ная информация)?|главная|официальный сайт).*$",
            "",
            value,
            flags=re.IGNORECASE,
        )
        value = re.split(
            r"\s+(?:напоминает|сообщает|рассказывает|режим работы|"
            r"правила гигиены|адрес и телефон|адрес\s*:|"
            r"электронн\w*\s+почт\w*\s*:|"
            r"головн\w*\s+организац\w*\s*:)\b",
            value,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        return " ".join(value.split()).strip(" ,.-")

    @staticmethod
    def _normal_case(value: str) -> str:
        value = " ".join(value.split()).strip(" ,.-")
        if value and value == value.upper():
            return value[:1].upper() + value[1:].lower()
        return value

    def _postal_address(self, address: Address, texts: list[str]) -> str:
        return self._best_address_candidate(address, texts, require_index=True)

    def _relaxed_postal_address(self, address: Address, texts: list[str]) -> str:
        """Return a complete street/building address even when its index is absent."""
        return self._best_address_candidate(address, texts, require_index=False)

    def _best_address_candidate(
        self,
        address: Address,
        texts: list[str],
        *,
        require_index: bool,
    ) -> str:
        candidates: list[tuple[int, str]] = []
        for source_priority, text in enumerate(texts[::-1]):
            normalized = " ".join(html_module.unescape(text).split())
            candidates.extend(
                (source_priority, match.group(0))
                for match in _POSTAL_ADDRESS_PATTERN.finditer(normalized)
            )
            candidates.extend(
                (source_priority, match.group(1))
                for match in _LABELED_ADDRESS_PATTERN.finditer(normalized)
            )
            candidates.extend(
                (source_priority, match.group(1))
                for match in _ROUTE_ADDRESS_PATTERN.finditer(normalized)
            )

        cleaned = [
            (priority, self._clean_address(candidate))
            for priority, candidate in candidates
        ]
        cleaned = [
            (priority, candidate)
            for priority, candidate in cleaned
            if len(candidate) >= 12
            and re.search(
                r"(?:край|область|республик|район|округ|\bг\.|город|"
                r"станиц|пос[её]лок|\bп\.|\bул\.|улиц)",
                candidate,
                re.IGNORECASE,
            )
            and (
                re.search(r"\b\d{6}\b", candidate)
                if require_index
                else self._looks_like_delivery_address(candidate)
            )
        ]
        if not cleaned:
            return ""

        location_words = set(
            self._meaningful_words(
                " ".join((address.region, address.district, address.locality, address.city))
            )
        )
        return max(
            cleaned,
            key=lambda item: (
                sum(word in item[1].casefold().replace("ё", "е") for word in location_words),
                item[1][:6].isdigit(),
                item[0],
                -len(item[1]),
            ),
        )[1]

    @staticmethod
    def _looks_like_delivery_address(value: str) -> bool:
        has_route = re.search(
            r"(?:\bул\.|\bулиц|\bшосс|\bпросп|\bплощад|\bпереул|"
            r"\bпроезд|\bнабереж|\bбульвар)",
            value,
            re.IGNORECASE,
        )
        has_building = re.search(
            r"(?:\bд\.|\bдом\b|\bвладени|\bстроени|\bкорпус\b)\s*\d",
            value,
            re.IGNORECASE,
        )
        return bool(has_route and has_building)

    @staticmethod
    def _clean_address(value: str) -> str:
        value = re.sub(r"\s+", " ", value).strip(" ,.;:-")
        value = re.split(
            r"\s+(?:Наименование|ОГРН|ИНН|ОКТМО|Контакт-центр|"
            r"Контакты|На карте|Электронн\w*\s+почт\w*|"
            r"Головн\w*\s+организац\w*)\s*[:.]?",
            value,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        value = re.sub(r"\.{2,}.*$", "", value)
        return value[:260].strip(" ,.;:-")

    def _candidate_is_consistent(
        self,
        address: Address,
        organization_type: OrganizationType,
        recipient: str,
        postal_address: str,
        source_text: str,
    ) -> bool:
        critical = {
            OrganizationType.MILITARY_COMMISSARIAT: ("комиссар",),
            OrganizationType.MILITARY_COMMANDANT: ("комендант", "гарнизон"),
            OrganizationType.NARCOLOGY: (
                "нарколог",
                "психоневролог",
            ),
            OrganizationType.PSYCHIATRY: (
                "психиатр",
                "психоневролог",
            ),
            OrganizationType.HOSPITAL: ("црб", "больниц"),
            OrganizationType.TFOMS: ("тфомс", "обязательного медицинского страхования"),
            OrganizationType.ADMINISTRATION: ("администрац",),
            OrganizationType.CONTRACT_SERVICE_POINT: ("пункт отбора", "контракт"),
            OrganizationType.ELECTION_COMMISSION: ("тик", "избирательн"),
        }[organization_type]
        recipient_text = recipient.casefold().replace("ё", "е")
        source = source_text.casefold().replace("ё", "е")
        source_only_types = {
            OrganizationType.NARCOLOGY,
            OrganizationType.PSYCHIATRY,
            OrganizationType.ADMINISTRATION,
        }
        if (
            organization_type not in source_only_types
            and not any(item in recipient_text for item in critical)
        ):
            return False
        if not any(item in source for item in critical):
            return False

        region_stems = [
            word[:7]
            for word in self._meaningful_words(address.region)
            if len(word) >= 7
        ]
        normalized_address = postal_address.casefold().replace("ё", "е")
        if region_stems and not any(stem in normalized_address for stem in region_stems):
            return False

        district_bound = self._strict_territory_types()
        if organization_type not in district_bound or not address.district:
            return True
        stems = [
            word[:7]
            for word in self._meaningful_words(address.district)
            if len(word) >= 7
        ]
        explicit_units = [
            match.group(0).casefold().replace("ё", "е")
            for match in _ADMINISTRATIVE_UNIT_PATTERN.finditer(postal_address)
        ]
        if explicit_units and stems:
            return any(
                stem in unit
                for unit in explicit_units
                for stem in stems
            )
        return not stems or any(stem in normalized_address for stem in stems)

    @staticmethod
    def _strict_territory_types() -> frozenset[OrganizationType]:
        return frozenset({
            OrganizationType.MILITARY_COMMISSARIAT,
            OrganizationType.NARCOLOGY,
            OrganizationType.PSYCHIATRY,
            OrganizationType.HOSPITAL,
            OrganizationType.ADMINISTRATION,
            OrganizationType.ELECTION_COMMISSION,
        })

    @staticmethod
    def _phones(texts: list[str]) -> tuple[str, ...]:
        found: list[str] = []
        for text in texts:
            for match in _PHONE_PATTERN.finditer(text):
                phone = re.sub(r"\s+", " ", match.group(0)).strip(" ,.;")
                digits = re.sub(r"\D", "", phone)
                if len(digits) not in {10, 11}:
                    continue
                if phone not in found:
                    found.append(phone)
        return tuple(found[:2])

    @staticmethod
    def _emails(texts: list[str]) -> tuple[str, ...]:
        found: list[str] = []
        for text in texts:
            for match in _EMAIL_PATTERN.finditer(text):
                email = parseaddr(match.group(0))[1].casefold()
                if email and email not in found:
                    found.append(email)
        return tuple(found[:3])

    @staticmethod
    def _page_text(extracted) -> str:
        if isinstance(extracted, dict):
            content = str(extracted.get("content", ""))
        else:
            content = str(extracted or "")
        if not content:
            return ""
        decoded = html_module.unescape(content)
        try:
            document = lxml_html.fromstring(decoded)
        except (ValueError, ParserError):
            return " ".join(decoded.split())[:20000]

        for node in document.xpath("//script|//style|//noscript|//svg"):
            node.drop_tree()
        parts = [document.text_content()]
        parts.extend(document.xpath("//meta/@content"))
        for packed in document.xpath("//*[@data-page]/@data-page"):
            try:
                parts.append(json.dumps(json.loads(packed), ensure_ascii=False))
            except (json.JSONDecodeError, TypeError):
                parts.append(packed)
        return " ".join(" ".join(parts).split())[:60000]

    @staticmethod
    def _district_recipient(value: str) -> str:
        words = [word for word in value.replace(",", " ").split() if word]
        if not words:
            return ""
        declined: list[str] = []
        nouns = {
            "район": "района",
            "округ": "округа",
            "р-н": "района",
        }
        replacements = (("ский", "ского"), ("цкий", "цкого"), ("ый", "ого"), ("ий", "его"))
        for word in words:
            lowered = word.casefold()
            if lowered in nouns:
                declined.append(nouns[lowered])
                continue
            for ending, replacement in replacements:
                if lowered.endswith(ending):
                    word = word[: -len(ending)] + replacement
                    break
            declined.append(word)
        return " ".join(declined)

    @staticmethod
    def _region_recipient(value: str) -> str:
        words = value.replace(",", " ").split()
        if not words:
            return ""
        declined: list[str] = []
        nouns = {"край": "края", "область": "области", "республика": "республики"}
        for word in words:
            lowered = word.casefold()
            if lowered in nouns:
                declined.append(nouns[lowered])
            elif lowered.endswith("ский"):
                declined.append(word[:-4] + "ского")
            elif lowered.endswith("ая"):
                declined.append(word[:-2] + "ой")
            else:
                declined.append(word)
        return " ".join(declined)

    @staticmethod
    def _is_combined_medical_unit(organization: Organization) -> bool:
        text = " ".join(
            (
                organization.recipient,
                organization.verification_note,
            )
        ).casefold().replace("ё", "е")
        return "психоневролог" in text or (
            "психиатр" in text and "нарколог" in text
        )

    @staticmethod
    def _narcology_from_psychiatry(
        psychiatry: Organization,
    ) -> Organization:
        name = psychiatry.recipient.split("\n", 1)[-1]
        return Organization(
            id=None,
            organization_type=OrganizationType.NARCOLOGY,
            recipient="Главному врачу\n" + name,
            postal_address=psychiatry.postal_address,
            phones=psychiatry.phones,
            email=psychiatry.email,
            source_url=psychiatry.source_url,
            verification_status="needs_review",
            verified_at="",
            verification_note=(
                "Наркологическая служба определена по найденному "
                "психоневрологическому диспансерному отделению; "
                "требуется проверка в Word."
            ),
        )

    @staticmethod
    def _psychiatry_from_narcology(
        narcology: Organization | None,
    ) -> Organization | None:
        if narcology is None:
            return None
        return Organization(
            id=None,
            organization_type=OrganizationType.PSYCHIATRY,
            recipient=("Главному врачу\n" + narcology.recipient.split("\n", 1)[-1]),
            postal_address=narcology.postal_address,
            phones=narcology.phones,
            email=narcology.email,
            source_url=narcology.source_url,
            verification_status="needs_review",
            verified_at="",
            verification_note=(
                "Психиатрическое отделение определено по найденному филиалу "
                "наркологического диспансера; требуется проверка в Word."
            ),
        )
