from enum import Enum


class BaseEnum(Enum):
    """
    Базовый класс для всех перечислений проекта.
    """

    @classmethod
    def values(cls) -> list[str]:
        return [item.value for item in cls]

    @classmethod
    def names(cls) -> list[str]:
        return [item.name for item in cls]

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        return [(item.name, item.value) for item in cls]

    @classmethod
    def from_value(cls, value: str):
        for item in cls:
            if item.value == value:
                return item
        raise ValueError(f"{value} не является значением {cls.__name__}")

    def __str__(self):
        return self.value