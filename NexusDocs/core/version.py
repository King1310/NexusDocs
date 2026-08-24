from dataclasses import dataclass


@dataclass(frozen=True)
class Version:
    """
    Информация о версии приложения.
    """

    major: int
    minor: int
    patch: int
    stage: str = "stable"

    @property
    def full(self) -> str:
        version = f"{self.major}.{self.minor}.{self.patch}"
        return version if self.stage == "stable" else f"{version}-{self.stage}"
