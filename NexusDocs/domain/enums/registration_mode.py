from domain.enums.base_enum import BaseEnum


class RegistrationMode(BaseEnum):
    """How the outgoing details of a unique request are registered."""

    FILLED = "Указать номер и дату сейчас"
    LATER = "Зарегистрировать документ позже"
