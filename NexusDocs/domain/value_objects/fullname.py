from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class FullName:
    """
    Полное имя человека.
    """

    last_name: str
    first_name: str
    middle_name: str

    @property
    def full(self) -> str:
        return (
            f"{self.last_name} "
            f"{self.first_name} "
            f"{self.middle_name}"
        )

    @property
    def initials(self) -> str:
        return (
            f"{self.last_name} "
            f"{self.first_name[0]}."
            f"{self.middle_name[0]}."
        )

    def to_dict(self) -> dict:
        """
        Преобразовать ФИО в словарь.
        """

        return {
            "last_name": self.last_name,
            "first_name": self.first_name,
            "middle_name": self.middle_name,
        }