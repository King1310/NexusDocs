from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


_NON_WORD_CHARACTERS = re.compile(r"[^0-9a-zа-я]+")


def normalize_lookup_name(value: str) -> str:
    """Привести короткое имя адресата к форме для поиска.

    Нормализация не зависит от регистра, «ё» и знаков препинания.
    """

    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = normalized.replace("ё", "е")
    return " ".join(_NON_WORD_CHARACTERS.sub(" ", normalized).split())


@dataclass(slots=True, frozen=True)
class CustomRecipient:
    """Адресат для уникального запроса.

    Запись привязана к категории шаблона, но не к территории
    человека и не к уже созданным Word-файлам.
    """

    id: int | None
    template_slug: str
    lookup_name: str
    recipient: str
    postal_address: str
    phones: tuple[str, ...] = ()
    email: str = ""
    source_url: str = ""
    verification_status: str = "unverified"
    verified_at: str = ""
    verification_note: str = ""

    def __post_init__(self) -> None:
        template_slug = self.template_slug.strip()
        lookup_name = self.lookup_name.strip()
        recipient = self.recipient.strip()
        postal_address = self.postal_address.strip()
        phones = tuple(phone.strip() for phone in self.phones if phone.strip())

        if not template_slug:
            raise ValueError("Категория шаблона не указана.")
        if not normalize_lookup_name(lookup_name):
            raise ValueError("Короткое имя адресата не указано.")
        if not recipient:
            raise ValueError("Адресат и название организации не указаны.")
        if not postal_address:
            raise ValueError("Почтовый адрес организации не указан.")
        if len(phones) > 2:
            raise ValueError("Можно указать не более двух телефонов.")

        object.__setattr__(self, "template_slug", template_slug)
        object.__setattr__(self, "lookup_name", lookup_name)
        object.__setattr__(self, "recipient", recipient)
        object.__setattr__(self, "postal_address", postal_address)
        object.__setattr__(self, "phones", phones)
        object.__setattr__(self, "email", self.email.strip())
        object.__setattr__(self, "source_url", self.source_url.strip())
        object.__setattr__(
            self,
            "verification_status",
            self.verification_status.strip() or "unverified",
        )
        object.__setattr__(self, "verified_at", self.verified_at.strip())
        object.__setattr__(
            self,
            "verification_note",
            self.verification_note.strip(),
        )

    @property
    def normalized_lookup_name(self) -> str:
        return normalize_lookup_name(self.lookup_name)

    @property
    def header(self) -> str:
        parts = [self.recipient, self.postal_address]
        if self.phones:
            parts.append("тел.: " + ",\n".join(self.phones))
        if self.email:
            parts.append(f"эл. почта: {self.email}")
        return "\n\n".join(parts)
