from __future__ import annotations

from urllib.parse import urlencode

from domain.enums.organization_type import OrganizationType
from domain.value_objects.address import Address


class BrowserOrganizationSearchService:
    """Формирует бесплатные поисковые ссылки для ручной проверки шапок."""

    _ENGINES = {
        "yandex": ("https://yandex.ru/search/", "text"),
        "google": ("https://www.google.com/search", "q"),
    }

    def query(
        self,
        address: Address,
        organization_type: OrganizationType,
    ) -> str:
        return self.queries(address, organization_type)[0]

    def queries(
        self,
        address: Address,
        organization_type: OrganizationType,
    ) -> tuple[str, ...]:
        """Build fallback queries, including combined medical departments."""

        region = self._quoted(address.region)
        district = self._quoted(address.district)
        district_name = self._district_name(address.district)
        district_quoted = self._quoted(district_name)
        locality = self._quoted(address.locality or address.city)

        queries: dict[OrganizationType, tuple[str, ...]] = {
            OrganizationType.MILITARY_COMMISSARIAT: (
                f"военный комиссариат {district} {region} официальный сайт "
                "полное наименование почтовый адрес телефон контакты",
            ),
            OrganizationType.MILITARY_COMMANDANT: (
                f"военная комендатура гарнизона {region} официальный сайт "
                "полное наименование почтовый адрес телефон контакты",
            ),
            OrganizationType.NARCOLOGY: (
                f'наркологический диспансер наркологическое отделение '
                f'{district_quoted} {region} адрес телефон email',
                f'психоневрологическое диспансерное отделение '
                f'{district_quoted} {region} нарколог контакты',
            ),
            OrganizationType.PSYCHIATRY: (
                f'психиатрическое отделение {district_quoted} '
                f'{region} адрес телефон email',
                f'психоневрологическое диспансерное отделение '
                f'{district_quoted} {region} контакты',
            ),
            OrganizationType.HOSPITAL: (
                f'центральная районная больница ЦРБ ЦГБ {district_quoted} {region} '
                "официальный сайт почтовый адрес телефон электронная почта",
            ),
            OrganizationType.TFOMS: (
                "территориальный фонд обязательного медицинского страхования ТФОМС "
                f"{region} официальный сайт почтовый адрес телефон "
                "электронная почта",
            ),
            OrganizationType.ADMINISTRATION: (
                f"{locality} администрация {district} официальный сайт "
                "почтовый адрес телефон электронная почта контакты",
            ),
            OrganizationType.CONTRACT_SERVICE_POINT: (
                "пункт отбора на военную службу по контракту "
                f"{region} официальный почтовый адрес телефон контакты",
            ),
            OrganizationType.ELECTION_COMMISSION: (
                "территориальная избирательная комиссия ТИК "
                f"{district_quoted} {region} официальный сайт почтовый адрес "
                "телефон электронная почта",
            ),
        }
        return tuple(
            " ".join(query.split())
            for query in queries[organization_type]
        )

    def url(
        self,
        address: Address,
        organization_type: OrganizationType,
        engine: str = "yandex",
    ) -> str:
        try:
            base_url, parameter = self._ENGINES[engine]
        except KeyError as error:
            raise ValueError(f"Неизвестная поисковая система: {engine}") from error
        return f"{base_url}?{urlencode({parameter: self.query(address, organization_type)})}"

    @staticmethod
    def _quoted(value: str) -> str:
        value = value.strip()
        return f'"{value}"' if value else ""

    @staticmethod
    def _district_name(value: str) -> str:
        words_to_remove = {
            "район",
            "муниципальный",
            "городской",
            "округ",
            "р-н",
        }
        words = [
            word
            for word in value.replace(",", " ").split()
            if word.casefold() not in words_to_remove
        ]
        return " ".join(words)
