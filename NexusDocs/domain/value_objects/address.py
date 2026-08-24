from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Address:
    """
    Универсальный адрес.
    """

    region: str
    district: str
    city: str
    locality: str
    street: str
    house: str
    apartment: str = ""

    @property
    def full(self) -> str:

        parts = [
            self.region,
            self.district,
            self.city,
            self.locality,
            self.street,
        ]

        if self.house:
            parts.append(f"д. {self.house}")

        if self.apartment:
            parts.append(
                f"кв. {self.apartment}"
            )

        return ", ".join(
            part
            for part in parts
            if part
        )

    def to_dict(
        self,
        prefix: str,
    ) -> dict:
        """
        Преобразовать адрес в словарь.

        prefix:
            registration
            birth
        """

        return {
            f"{prefix}_region": self.region,
            f"{prefix}_district": self.district,
            f"{prefix}_city": self.city,
            f"{prefix}_locality": self.locality,
            f"{prefix}_street": self.street,
            f"{prefix}_house": self.house,
            f"{prefix}_apartment": self.apartment,
        }
