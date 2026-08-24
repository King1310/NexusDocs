from __future__ import annotations

import os
from collections.abc import Iterable

from openai import OpenAI
from pydantic import BaseModel, Field

from domain.entities.organization import Organization
from domain.enums.organization_type import OrganizationType
from domain.value_objects.address import Address


class OrganizationCandidate(BaseModel):
    organization_type: OrganizationType
    recipient: str = Field(description="Адресат и официальное название")
    postal_address: str
    phones: list[str] = Field(default_factory=list)
    email: str = ""
    fax: str = ""
    source_url: str
    verification_note: str = ""


class OrganizationSearchResponse(BaseModel):
    organizations: list[OrganizationCandidate]
    unresolved_types: list[OrganizationType] = Field(default_factory=list)


class OrganizationSearchService:
    """Ищет отсутствующие адресные шапки через OpenAI web search."""

    def __init__(
        self,
        api_key: str | None = None,
        client=None,
        model: str = "gpt-5.6-terra",
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "").strip()
        self.client = client
        self.model = model

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key or self.client is not None)

    def search(
        self,
        address: Address,
        organization_types: Iterable[OrganizationType],
    ) -> tuple[Organization, ...]:
        requested = tuple(organization_types)
        if not requested:
            return ()
        if self.client is None:
            if not self.api_key:
                raise ValueError("Не указан API-ключ для интернет-поиска.")
            self.client = OpenAI(api_key=self.api_key, timeout=180.0)

        response = self.client.responses.parse(
            model=self.model,
            tools=[{"type": "web_search"}],
            reasoning={"effort": "medium"},
            text_format=OrganizationSearchResponse,
            instructions=self._instructions(),
            input=self._prompt(address, requested),
            max_output_tokens=8000,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise ValueError("Интернет-поиск не вернул структурированный результат.")

        requested_set = set(requested)
        found: dict[OrganizationType, Organization] = {}
        for candidate in parsed.organizations:
            if candidate.organization_type not in requested_set:
                continue
            source_url = candidate.source_url.strip()
            if not source_url.startswith(("https://", "http://")):
                continue
            found[candidate.organization_type] = Organization(
                id=None,
                organization_type=candidate.organization_type,
                recipient=candidate.recipient.strip(),
                postal_address=candidate.postal_address.strip(),
                phones=tuple(phone.strip() for phone in candidate.phones if phone.strip()),
                email=candidate.email.strip(),
                fax=candidate.fax.strip(),
                source_url=source_url,
                verification_status="unverified",
                verified_at="",
                verification_note=candidate.verification_note.strip(),
            )
        return tuple(
            found[organization_type]
            for organization_type in requested
            if organization_type in found
        )

    @staticmethod
    def _instructions() -> str:
        return (
            "Ты выполняешь проверяемый поиск адресатов для официальных служебных "
            "запросов в Российской Федерации. Не придумывай реквизиты. Используй "
            "в первую очередь официальные сайты органов власти, учреждений и "
            "официальные документы. Для медицинских организаций установи именно "
            "подразделение, обслуживающее указанный адрес. Для военной комендатуры "
            "укажи полное официальное наименование с формулировкой 'Военной "
            "комендатуры'. Если надёжного подтверждения нет, не создавай кандидата, "
            "а добавь тип в unresolved_types. Для каждого кандидата обязателен "
            "прямой URL основного источника. Телефоны возвращай без подписей "
            "'приёмная' или 'регистратура'."
        )

    @staticmethod
    def _prompt(
        address: Address,
        organization_types: tuple[OrganizationType, ...],
    ) -> str:
        types = "\n".join(f"- {item.value}" for item in organization_types)
        return (
            "Найди актуальные организации, территориально отвечающие за этот адрес "
            f"регистрации:\n{address.full}\n\n"
            "Нужны только следующие типы:\n"
            f"{types}\n\n"
            "Сформируй recipient в готовом для вставки в шапку виде: должность "
            "адресата и полное официальное название организации. Postal_address "
            "должен быть почтовым адресом самой организации."
        )
